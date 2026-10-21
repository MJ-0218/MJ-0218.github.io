#!/usr/bin/env python3
"""반복 수요 캘린더에서 '지금 준비해야 할 글'을 뽑는다. 네트워크 없이 동작한다.

사용: python3 automation/scripts/calendar_due.py [--date 2026-10-17] [--json]
출력 후보는 trend_radar.py 결과와 같은 모양(keyword, category, score, cycle …)이라 글쓰기 세션이 함께 다룬다.
"""
import argparse
import calendar as cal
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))


def covered_cycles():
    """_drafts, _posts, variants 의 front matter cycle 값 = 이미 쓴 주기"""
    out = set()
    dirs = ["_drafts", "_posts", "automation/variants", "automation/global/drafts"] + \
        [str(p.relative_to(ROOT)) for p in (ROOT / "automation" / "blogs").glob("*/drafts")]
    for d in dirs:
        for p in (ROOT / d).glob("*.md"):
            m = re.search(r"^cycle:\s*(\S+)", p.read_text(encoding="utf-8"), flags=re.M)
            if m:
                out.add(m.group(1).strip("\"'"))
    # 확인 결과 이미 지났거나 쓸 수 없어 건너뛴 주기 (한 줄에 cycle 하나, # 뒤는 사유)
    skip = ROOT / "automation" / "state" / "skipped_cycles.txt"
    if skip.exists():
        for line in skip.read_text(encoding="utf-8").splitlines():
            c = line.split("#")[0].strip()
            if c:
                out.add(c)
    return out


def yearly_due(entry, today):
    for ph in entry.get("phases", []):
        months = ph["months"]
        lead = ph.get("lead_days", 7)
        # 12월→1월처럼 해를 넘는 구간과, 올해·내년 주기를 모두 본다
        for year in (today.year - 1, today.year, today.year + 1):
            spans, y = [], year
            prev = None
            for mo in months:
                if prev is not None and mo < prev:
                    y += 1
                spans.append((y, mo))
                prev = mo
            start = date(spans[0][0], spans[0][1], 1)
            ey, em = spans[-1]
            end = date(ey, em, cal.monthrange(ey, em)[1])
            if start - timedelta(days=lead) <= today <= end:
                days_to = (start - today).days
                yield {
                    "cycle": f"{entry['id']}-{ph['key']}-{spans[0][0]}",
                    "phase": ph["key"], "queries": ph.get("queries", []),
                    "window": f"{start:%Y-%m} ~ {end:%Y-%m} (보통)", "days_to_start": days_to,
                    "in_window": days_to <= 0,
                }


def monthly_due(entry, today):
    day = entry.get("day", 1)
    lead = entry.get("lead_days", 5)
    for base in (today.replace(day=1), (today.replace(day=1) + timedelta(days=32)).replace(day=1)):
        target = base.replace(day=min(day, cal.monthrange(base.year, base.month)[1]))
        if target - timedelta(days=lead) <= today <= target + timedelta(days=3):
            phase = f"{base:%B %Y}" if entry.get("lang") == "en" else f"{base.month}월"
            yield {"cycle": f"{entry['id']}-{base:%Y-%m}", "phase": phase, "queries": entry.get("queries", []),
                   "window": f"{target:%Y-%m-%d} 전후", "days_to_start": (target - today).days, "in_window": today >= target}


def weekly_due(entry, today):
    """금·토·일에는 다음 주, 월요일에는 이번 주 일정을 준비한다."""
    wd = today.weekday()
    if wd == 0:
        monday = today
    elif wd >= entry.get("weekday", 4):
        monday = today + timedelta(days=7 - wd)
    else:
        return
    iso = monday.isocalendar()
    yield {"cycle": f"{entry['id']}-{iso[0]}W{iso[1]:02d}", "phase": f"{monday:%m월 %d일} 주",
           "queries": entry.get("queries", []), "window": f"{monday:%Y-%m-%d} ~ {monday + timedelta(days=6):%m-%d}",
           "days_to_start": (monday - today).days, "in_window": True}


CALENDARS = {"kr": ROOT / "automation" / "calendar.yml", "us": ROOT / "automation" / "global" / "calendar_us.yml",
             "in": ROOT / "automation" / "blogs" / "in" / "calendar.yml"}
MARKET_UTC = {"us": -5, "in": 5.5}  # 그 나라 날짜 기준으로 본다


def due(today=None, market="kr"):
    if market in MARKET_UTC:  # 미국·인도 글은 그 나라 시간 기준 날짜로 본다
        today = today or datetime.now(timezone(timedelta(hours=MARKET_UTC[market]))).date()
    today = today or datetime.now(KST).date()
    entries = yaml.safe_load(CALENDARS[market].read_text(encoding="utf-8"))
    done = covered_cycles()
    out = []
    for e in entries:
        kind = e.get("recurrence", "yearly")
        gen = {"yearly": yearly_due, "monthly": monthly_due, "weekly": weekly_due}[kind](e, today)
        for d in gen:
            if d["cycle"] in done:
                continue
            urgency = 30 if d["in_window"] else max(0, 20 - d["days_to_start"])
            out.append({
                "source": "calendar", "keyword": f"{e['name']} {d['phase']}".strip(), "category": e["category"],
                "official_sources": e.get("official", []), "official": True, "traffic": 0,
                "published": datetime.now(KST).isoformat(), "score": 55 + urgency,
                "already_covered": False, **d,
            })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--market", default="kr", choices=list(CALENDARS))
    a = ap.parse_args()
    today = date.fromisoformat(a.date) if a.date else None
    items = due(today, a.market)
    if a.json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return
    for i in items:
        state = "진행 중" if i["in_window"] else f"{i['days_to_start']}일 뒤 시작"
        print(f"{i['score']:5.0f}  [{i['category']}] {i['keyword']:<34} {i['window']:<26} {state:<10} cycle={i['cycle']}")
        print(f"        검색어: {', '.join(i['queries'])}")


if __name__ == "__main__":
    main()
