#!/usr/bin/env python3
"""주간 청약 일정 글 재료 — 레이더(청약홈 API) 데이터 + 각 공고 상세 페이지 원문 인용을 한 번에 만든다.

사용: python3 automation/scripts/applyhome_week.py <월요일 YYYY-MM-DD> [--radar /tmp/radar.json] [--out /tmp/week.json]
출력 JSON:
  complexes: 단지별 {name, kind(분양/무순위/임대), region, address, households, special, rank1, rank2, receipt, winners, url, quote}
  claims:    automation/claims/<slug>.yml 에 붙여 넣을 claim 목록 (quote 는 상세 페이지 '청약일정' 부분 원문)
본문에 쓰는 날짜·세대수는 반드시 이 claims 의 value 문구와 같은 표기로 쓴다("10월 19일", "1,289세대").
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_claims import page_text  # noqa: E402


def kday(s):
    if not s:
        return ""
    d = date.fromisoformat(s)
    return f"{d.month}월 {d.day}일"


def schedule_quote(text, name):
    """상세 페이지에서 '청약일정' 표 부분만 잘라 인용문으로 쓴다 (공백 정리)."""
    t = re.sub(r"\s+", " ", text)
    i = t.find("청약접수")
    if i == -1:
        return ""
    seg = t[i:i + 400]
    j = seg.find("당첨자 발표일")
    if j != -1:
        seg = seg[: j + len("당첨자 발표일") + 12]
    return seg.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("monday")
    ap.add_argument("--radar", default="/tmp/radar.json")
    ap.add_argument("--out", default="/tmp/week.json")
    a = ap.parse_args()
    mon = date.fromisoformat(a.monday)
    sun = mon + timedelta(days=6)
    data = json.loads(Path(a.radar).read_text(encoding="utf-8"))
    rows = [c for c in data["candidates"] if c["source"] == "applyhome"]
    out, claims = [], []
    for c in rows:
        r = c.get("raw", {})
        begin, end = r.get("RCEPT_BGNDE") or r.get("SUBSCRPT_RCEPT_BGNDE"), r.get("RCEPT_ENDDE") or r.get("SUBSCRPT_RCEPT_ENDDE")
        if not begin:
            continue
        if not (mon <= date.fromisoformat(begin) <= sun):
            continue
        kind = "무순위" if "무순위" in c["keyword"] else ("임대" if "임대" in (r.get("RENT_SECD_NM") or "") or "임대" in c["keyword"] else "분양")
        url = r.get("PBLANC_URL", "")
        try:
            quote = schedule_quote(page_text(url), r.get("HOUSE_NM", "")) if url else ""
        except Exception as e:  # noqa: BLE001
            quote = ""
            print(f"  상세 페이지 열기 실패 {r.get('HOUSE_NM')}: {e}", file=sys.stderr)
        item = {
            "name": r.get("HOUSE_NM"), "kind": kind, "region": r.get("SUBSCRPT_AREA_CODE_NM"),
            "address": r.get("HSSPLY_ADRES"), "households": r.get("TOT_SUPLY_HSHLDCO"),
            "special": kday(r.get("SPSPLY_RCEPT_BGNDE")), "rank1": kday(r.get("GNRL_RNK1_CRSPAREA_RCPTDE")),
            "rank2": kday(r.get("GNRL_RNK2_CRSPAREA_RCPTDE")), "receipt": f"{kday(begin)} ~ {kday(end)}" if end and end != begin else kday(begin),
            "winners": kday(r.get("PRZWNER_PRESNATN_DE")), "url": url, "quote": quote,
        }
        out.append(item)
        parts = [f"{k} {v}" for k, v in (("특별공급", item["special"]), ("1순위", item["rank1"]), ("2순위", item["rank2"]),
                                          ("접수", item["receipt"]), ("당첨자 발표", item["winners"])) if v]
        if item["households"]:
            parts.append(f"{int(item['households']):,}세대")
        claim = {"claim": f"{item['name']} 청약 일정", "value": ", ".join(parts),
                 "value_note": "청약홈 공고의 YYYY-MM-DD 날짜를 'M월 D일'로 옮겨 적음, 세대수는 청약홈 분양정보 API(TOT_SUPLY_HSHLDCO)",
                 "quote": quote, "source": url}
        if not quote:
            claim["manual"] = "상세 페이지에서 청약일정 문구를 자동으로 못 뽑음 — 청약홈 공고에서 직접 확인"
        claims.append(claim)
    out.sort(key=lambda x: (x["kind"] != "분양", x["receipt"]))
    Path(a.out).write_text(json.dumps({"week": f"{mon}~{sun}", "complexes": out, "claims": claims}, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in out:
        print(f"[{x['kind']}] {x['name']} ({x['region']}) 접수 {x['receipt']} · 특공 {x['special']} · 1순위 {x['rank1']} · 발표 {x['winners']} · {x['households']}세대 · 인용 {'O' if x['quote'] else 'X'}")


if __name__ == "__main__":
    main()
