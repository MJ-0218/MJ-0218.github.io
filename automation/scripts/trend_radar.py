#!/usr/bin/env python3
"""트렌드 레이더: 지금 검색이 뛰는 주제 + 정부 공식 발표를 모아 점수순 후보 목록을 만든다.

GitHub Actions(인터넷 개방)에서 30분마다 실행된다. 결과는 radar-data 브랜치의
trends/latest.json 에 쌓이고, 글쓰기 세션은 그 파일을 읽어 주제를 고른다.

수집원 (실패해도 다른 수집원은 계속 진행):
  google_trends : Google 트렌드 한국 실시간 인기 검색어 RSS (검색량 추정치 포함)
  korea_kr      : 대한민국 정책브리핑 정책뉴스·보도자료 RSS (정부 공식)
  google_news   : 감시 키워드별 Google 뉴스 RSS (최근 기사 수 = 화제성)
  applyhome     : 청약홈 분양정보 공공데이터 API (DATA_GO_KR_KEY 환경변수가 있을 때만)
  calendar      : automation/calendar.yml — 매년·매달·매주 반복되는 검색 수요 (네트워크 불필요)

사용: python3 automation/scripts/trend_radar.py --out trends/latest.json [--history trends/history]
"""
import argparse
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; semter-radar/1.0; +https://mj-0218.github.io)"
ROOT = Path(__file__).resolve().parents[2]

# 카테고리 분류 키워드 — config.yml 의 radar.categories 로 덮어쓸 수 있음
DEFAULT_CATEGORIES = {
    "정부혜택": ["지원금", "지급", "바우처", "환급", "장려금", "수당", "보조금", "쿠폰", "민생", "신청 기간",
               "청년도약", "청년월세", "근로장려금", "자녀장려금", "에너지바우처", "기초연금", "부모급여", "아동수당"],
    "청약": ["청약", "분양", "특별공급", "무순위", "줍줍", "행복주택", "공공임대", "신혼희망타운", "LH", "SH",
           "입주자모집", "사전청약", "뉴홈"],
    "선거": ["선거", "투표", "사전투표", "투표소", "선관위", "후보", "재보궐"],
    "세금": ["연말정산", "종합소득세", "종부세", "재산세", "부가세", "자동차세", "홈택스", "세액공제"],
    "노동·급여": ["최저임금", "퇴직금", "실업급여", "연차", "육아휴직", "출산휴가", "4대보험"],
    "방송정보": ["생생정보", "생방송 투데이", "생방송 오늘저녁", "생활의 달인", "6시 내고향", "백반기행"],
}
CATEGORY_WEIGHT = {"정부혜택": 1.6, "청약": 1.5, "세금": 1.4, "노동·급여": 1.3, "선거": 1.3, "방송정보": 1.1, "기타": 0.6}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def parse_date(s):
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(KST)
    except Exception:
        return None


def classify(text, categories):
    hits = {c: sum(1 for k in kws if k.lower() in text.lower()) for c, kws in categories.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else "기타"


def parse_traffic(s):
    """'20,000+' / '2만+' → 정수"""
    if not s:
        return 0
    s = s.replace(",", "").replace("+", "").strip()
    m = re.match(r"([\d.]+)\s*(만|천|K|M)?", s, flags=re.I)
    if not m:
        return 0
    n = float(m.group(1))
    mult = {"만": 10000, "천": 1000, "k": 1000, "m": 1000000}.get((m.group(2) or "").lower(), 1)
    return int(n * mult)


def items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        yield it


def child_text(el, local):
    for c in el:
        if c.tag == local or c.tag.endswith("}" + local):
            return (c.text or "").strip()
    return ""


def children(el, local):
    return [c for c in el if c.tag == local or c.tag.endswith("}" + local)]


def src_google_trends(cfg, cats):
    out = []
    for it in items(fetch("https://trends.google.com/trending/rss?geo=KR")):
        title = child_text(it, "title")
        news = []
        for n in children(it, "news_item"):
            news.append({"title": strip_tags(child_text(n, "news_item_title")), "url": child_text(n, "news_item_url"),
                         "source": child_text(n, "news_item_source")})
        text = title + " " + " ".join(n["title"] for n in news)
        out.append({
            "source": "google_trends", "keyword": title, "traffic": parse_traffic(child_text(it, "approx_traffic")),
            "published": (parse_date(child_text(it, "pubDate")) or datetime.now(KST)).isoformat(),
            "category": classify(text, cats), "news": news[:5], "official": False,
        })
    return out


def src_korea_kr(cfg, cats):
    out = []
    for feed in cfg.get("korea_kr_feeds", ["https://www.korea.kr/rss/policy.xml", "https://www.korea.kr/rss/pressrelease.xml"]):
        try:
            data = fetch(feed)
        except Exception as e:
            print(f"  korea.kr {feed}: {e}", file=sys.stderr)
            continue
        for it in items(data):
            title = strip_tags(child_text(it, "title"))
            desc = strip_tags(child_text(it, "description"))[:300]
            out.append({
                "source": "korea_kr", "keyword": title, "traffic": 0,
                "published": (parse_date(child_text(it, "pubDate")) or datetime.now(KST)).isoformat(),
                "category": classify(title + " " + desc, cats), "summary": desc,
                "news": [{"title": title, "url": child_text(it, "link"), "source": "정책브리핑"}], "official": True,
            })
    return out


def src_google_news(cfg, cats):
    out = []
    for kw in cfg.get("watch_keywords", []):
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"{kw} when:1d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        try:
            its = list(items(fetch(url)))
        except Exception as e:
            print(f"  google_news {kw}: {e}", file=sys.stderr)
            continue
        if not its:
            continue
        news = [{"title": strip_tags(child_text(i, "title")), "url": child_text(i, "link"), "source": child_text(i, "source")} for i in its[:5]]
        out.append({
            "source": "google_news", "keyword": kw, "traffic": 0, "article_count_24h": len(its),
            "published": (parse_date(child_text(its[0], "pubDate")) or datetime.now(KST)).isoformat(),
            "category": classify(kw + " " + " ".join(n["title"] for n in news), cats), "news": news, "official": False,
        })
    return out


def src_applyhome(cfg, cats):
    """청약홈 분양정보 (공공데이터포털 '한국부동산원_청약홈 분양정보 조회 서비스').
    엔드포인트·필드명은 data.go.kr 활용가이드 기준으로 config 에서 바꿀 수 있게 둔다."""
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        print("  applyhome: DATA_GO_KR_KEY 없음 — 건너뜀", file=sys.stderr)
        return []
    ah = cfg.get("applyhome", {})
    endpoint = ah.get("endpoint", "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail")
    today = datetime.now(KST).date()
    q = {"page": 1, "perPage": 100, "serviceKey": key,
         "cond[RCRIT_PBLANC_DE::GTE]": (today - timedelta(days=14)).isoformat()}
    data = json.loads(fetch(endpoint + "?" + urllib.parse.urlencode(q)))
    out = []
    for row in data.get("data", []):
        name = row.get("HOUSE_NM") or row.get("houseNm") or ""
        begin = row.get("RCEPT_BGNDE") or row.get("SUBSCRPT_RCEPT_BGNDE") or ""
        end = row.get("RCEPT_ENDDE") or row.get("SUBSCRPT_RCEPT_ENDDE") or ""
        out.append({
            "source": "applyhome", "keyword": f"{name} 청약", "traffic": 0, "category": "청약", "official": True,
            "published": row.get("RCRIT_PBLANC_DE", ""), "receipt_begin": begin, "receipt_end": end,
            "region": row.get("SUBSCRPT_AREA_CODE_NM", ""), "address": row.get("HSSPLY_ADRES", ""),
            "households": row.get("TOT_SUPLY_HSHLDCO", ""),
            "news": [{"title": f"{name} 입주자모집공고", "url": row.get("PBLANC_URL", ""), "source": "청약홈"}],
            "raw": row,
        })
    return out


def src_calendar(cfg, cats):
    """반복 수요 캘린더 (네트워크 불필요)"""
    sys.path.insert(0, str(Path(__file__).parent))
    from calendar_due import due
    return due()


SOURCES = {"calendar": src_calendar, "google_trends": src_google_trends, "korea_kr": src_korea_kr, "google_news": src_google_news, "applyhome": src_applyhome}


def score(item, now):
    w = CATEGORY_WEIGHT.get(item["category"], 0.6)
    traffic = item.get("traffic", 0)
    base = min(100, (traffic / 2000) * 10) if traffic else 0
    base += min(30, item.get("article_count_24h", 0) * 3)
    if item.get("official"):
        base += 25
    if item["source"] == "applyhome" and item.get("receipt_begin"):
        try:
            days = (datetime.fromisoformat(item["receipt_begin"]).date() - now.date()).days
            base += 40 if 0 <= days <= 7 else (15 if days > 7 else 0)
        except ValueError:
            pass
    try:
        age_h = (now - datetime.fromisoformat(item["published"])).total_seconds() / 3600
        fresh = 1.0 if age_h < 6 else (0.7 if age_h < 24 else 0.4)
    except Exception:
        fresh = 0.7
    return round(base * w * fresh, 1)


def covered_titles():
    titles = []
    for d in ("_posts", "_drafts"):
        for p in (ROOT / d).glob("*.md"):
            m = re.search(r"^title:\s*(.+)$", p.read_text(encoding="utf-8"), flags=re.M)
            if m:
                titles.append(m.group(1).strip().strip('"\''))
    return titles


def load_cfg():
    p = ROOT / "automation" / "config.yml"
    try:
        import yaml  # PyYAML (Actions 에서 설치)
        return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("radar", {})
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="trends/latest.json")
    ap.add_argument("--history", default="")
    ap.add_argument("--only", default="", help="쉼표로 구분한 수집원만 실행")
    a = ap.parse_args()

    cfg = load_cfg()
    cats = cfg.get("categories") or DEFAULT_CATEGORIES
    now = datetime.now(KST)
    collected, status = [], {}
    for name, fn in SOURCES.items():
        if a.only and name not in a.only.split(","):
            continue
        try:
            got = fn(cfg, cats)
            collected += got
            status[name] = f"ok ({len(got)})"
        except Exception as e:
            status[name] = f"error: {e}"
        print(f"[{name}] {status[name]}", file=sys.stderr)

    covered = covered_titles()
    seen, ranked = set(), []
    for it in collected:
        k = re.sub(r"\s+", "", it["keyword"].lower())
        if k in seen:
            continue
        seen.add(k)
        if it["source"] != "calendar":  # 캘린더 후보는 자체 점수 사용
            it["score"] = score(it, now)
        it["already_covered"] = any(it["keyword"].replace(" ", "") in t.replace(" ", "") for t in covered)
        ranked.append(it)
    ranked.sort(key=lambda x: x["score"], reverse=True)

    result = {"generated_at": now.isoformat(), "sources": status, "candidates": ranked}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.history:
        h = Path(a.history) / f"{now:%Y-%m-%d}.jsonl"
        h.parent.mkdir(parents=True, exist_ok=True)
        with h.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": now.isoformat(), "top": [{k: c[k] for k in ("keyword", "category", "score", "source")} for c in ranked[:30]]}, ensure_ascii=False) + "\n")
    print(f"후보 {len(ranked)}개 → {out}")
    for c in ranked[:15]:
        print(f"  {c['score']:6.1f}  [{c['category']}] {c['keyword']}  ({c['source']})")


if __name__ == "__main__":
    main()
