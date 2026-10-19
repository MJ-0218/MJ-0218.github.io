#!/usr/bin/env python3
"""트렌드 레이더: 지금 검색이 뛰는 주제 + 정부 공식 발표를 모아 점수순 후보 목록을 만든다.

GitHub Actions(인터넷 개방)에서 30분마다 실행된다. 결과는 radar-data 브랜치의
trends/latest.json 에 쌓이고, 글쓰기 세션은 그 파일을 읽어 주제를 고른다.

수집원 (실패해도 다른 수집원은 계속 진행):
  google_trends : Google 트렌드 한국 실시간 인기 검색어 RSS (검색량 추정치 포함)
  korea_kr      : 정책브리핑 첫 화면 실시간 인기뉴스 (RSS 는 2026-07-01 중단)
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
import urllib.error
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
    "방송정보": ["생생정보", "생방송 투데이", "생방송 오늘저녁", "생활의 달인", "6시 내고향", "백반기행", "맛집",
               "동네 한 바퀴", "맛있는 녀석들", "토요일은 밥이 좋아", "줄서는 식당", "놀라운 토요일"],
}
CATEGORY_WEIGHT = {"정부혜택": 1.6, "청약": 1.5, "세금": 1.4, "노동·급여": 1.3, "선거": 1.3, "방송정보": 1.3, "기타": 0.6}
DEFAULT_TV_PROGRAMS = ["생생정보", "생방송 투데이", "생방송 오늘저녁", "6시 내고향", "생활의 달인", "백반기행",
                       "동네 한 바퀴", "맛있는 녀석들", "토요일은 밥이 좋아", "줄서는 식당"]


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
    """정책브리핑 첫 화면의 '실시간 인기뉴스' (제목·링크만).
    정책브리핑 RSS 는 2026-07-01 제공 중단(저작권 등 권리 보호) — 본문은 가져오지 않는다."""
    page = fetch(cfg.get("korea_kr_home", "https://www.korea.kr/")).decode("utf-8", "ignore")
    a, b = page.find("실시간 인기뉴스 S"), page.find("실시간 인기뉴스 E")
    block = page[a:b] if a != -1 and b != -1 else page
    out = []
    for m in re.finditer(r'href="(https://www\.korea\.kr/news/[^"]+)".*?<span class="text">\s*(.*?)\s*</span>', block, flags=re.S):
        url = re.sub(r"&pWise.*", "", m.group(1))
        title = strip_tags(m.group(2))
        out.append({
            "source": "korea_kr", "keyword": title, "traffic": 0, "rank": len(out) + 1,
            "published": datetime.now(KST).isoformat(), "category": classify(title, cats),
            "news": [{"title": title, "url": url, "source": "정책브리핑 실시간 인기뉴스"}], "official": True,
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
        # 최근 1시간 기사 수 — 직전 실행들과 비교해 '갑자기 늘었는지' 보는 데 쓴다
        n1h = 0
        try:
            u1 = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"{kw} when:1h", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
            n1h = len(list(items(fetch(u1))))
        except Exception as e:
            print(f"  google_news 1h {kw}: {e}", file=sys.stderr)
        out.append({
            "source": "google_news", "keyword": kw, "traffic": 0, "article_count_24h": len(its), "article_count_1h": n1h,
            "published": (parse_date(child_text(its[0], "pubDate")) or datetime.now(KST)).isoformat(),
            "category": classify(kw + " " + " ".join(n["title"] for n in news), cats), "news": news, "official": False,
        })
    return out


def src_tv_food(cfg, cats):
    """방송 맛집 — 방송사 프로그램별로 최근 3일 가게 정보 기사를 모은다. 방송 당일 저녁~다음 날 검색이 몰린다.
    프로그램·날짜 하나가 후보 하나(그날 방송에 나온 가게들을 한 글로 정리)."""
    out = []
    for prog in cfg.get("tv_programs") or DEFAULT_TV_PROGRAMS:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": f"{prog} when:3d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        try:
            its = list(items(fetch(url)))
        except Exception as e:
            print(f"  tv_food {prog}: {e}", file=sys.stderr)
            continue
        news = []
        for i in its:
            title = strip_tags(child_text(i, "title"))
            if prog.replace(" ", "") not in title.replace(" ", ""):
                continue  # 프로그램 이름이 제목에 없는 기사(광고성 페이지 등)는 버린다
            if not any(w in title for w in ("맛집", "위치", "식당", "가게", "메뉴")):
                continue  # 출연자 근황 같은 기사는 빼고 가게 정보 기사만
            news.append({"title": title, "url": child_text(i, "link"), "source": child_text(i, "source"),
                         "published": (parse_date(child_text(i, "pubDate")) or datetime.now(KST)).isoformat()})
        if not news:
            continue
        day = max(n["published"] for n in news)[:10]
        out.append({
            "source": "tv_food", "keyword": f"{prog} 맛집 {day}", "program": prog, "traffic": 0,
            "article_count_24h": len(news), "published": max(n["published"] for n in news),
            "category": "방송정보", "news": news[:12], "official": False,
        })
    return out


def resolve_gnews(url, title=""):
    """Google 뉴스 RSS 링크를 실제 기사 주소로 바꾼다 (Actions 에서만 쓰임).
    1) googlenewsdecoder  2) 안 되면 같은 제목을 Bing 뉴스 RSS 에서 찾아 원래 주소를 쓴다."""
    if "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder  # pip install googlenewsdecoder
        r = gnewsdecoder(url, interval=1)
        if r.get("status"):
            return r["decoded_url"]
        print(f"  gnews decode 실패: {r.get('message', r)}"[:200], file=sys.stderr)
    except Exception as e:
        print(f"  gnews decode: {e}"[:200], file=sys.stderr)
    if title:
        head = re.sub(r"\s+-\s+[^-]+$", "", title).strip()  # 끝의 ' - 매체명' 떼기
        try:
            q = urllib.parse.urlencode({"q": head, "format": "rss", "setlang": "ko"})
            for it in items(fetch("https://www.bing.com/news/search?" + q)):
                link = child_text(it, "link")
                m = re.search(r"[?&]url=([^&]+)", link)
                real = urllib.parse.unquote(m.group(1)) if m else link
                t2 = strip_tags(child_text(it, "title"))
                if real.startswith("http") and (head[:15] in t2 or t2[:15] in head):
                    return real
        except Exception as e:
            print(f"  bing 대체 실패: {e}"[:200], file=sys.stderr)
    return None


def collect_evidence(ranked, out_dir, cfg):
    """작성 세션에서 막힌 원문을 Actions 가 대신 받아 둔다: 방송 맛집·급상승 후보의 기사 + 요청 URL."""
    import evidence as ev
    saved, failed = 0, 0
    targets = []
    for c in ranked:
        if c["source"] == "tv_food" or (c.get("spike") and c["source"] in ("google_trends", "google_news")) or \
                (c["source"] == "google_news" and c.get("score", 0) >= 35):
            targets.append(c)
    for c in targets[: int(cfg.get("evidence_topics", 25))]:
        c["evidence"] = []
        for n in c.get("news", [])[: int(cfg.get("evidence_per_topic", 4))]:
            real = resolve_gnews(n["url"], n.get("title", ""))
            if not real:
                failed += 1
                continue
            try:
                final, raw, ctype = ev.fetch(real)
                rec = ev.save(out_dir, final, n["title"], ev.html_to_text(raw, ctype),
                              {"requested_url": real, "topic": c["keyword"], "outlet": n.get("source", "")})
                c["evidence"].append({"url": rec["url"], "title": n["title"], "outlet": n.get("source", "")})
                saved += 1
            except Exception as e:
                failed += 1
                print(f"  evidence {real}: {e}", file=sys.stderr)
    req = ROOT / "automation" / "state" / "fetch_requests.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8").splitlines():
            u = line.split("#")[0].strip()
            if not u.startswith("http"):
                continue
            try:
                final, raw, ctype = ev.fetch(u)
                text = ev.html_to_text(raw, ctype) if "pdf" not in ctype else ""
                ev.save(out_dir, u, line.split("#", 1)[1].strip() if "#" in line else u, text,
                        {"requested_url": u, "final_url": final, "topic": "요청"})
                saved += 1
            except Exception as e:
                failed += 1
                print(f"  request {u}: {e}", file=sys.stderr)
    return f"ok (저장 {saved}, 실패 {failed})"


def src_applyhome(cfg, cats):
    """청약홈 분양정보 (공공데이터포털 '한국부동산원_청약홈 분양정보 조회 서비스').
    엔드포인트·필드명은 data.go.kr 활용가이드 기준으로 config 에서 바꿀 수 있게 둔다."""
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        print("  applyhome: DATA_GO_KR_KEY 없음 — 건너뜀", file=sys.stderr)
        return []
    ah = cfg.get("applyhome", {})
    base = ah.get("base", "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/")
    # APT 일반 분양 + 무순위·잔여세대(줍줍)
    endpoints = ah.get("endpoints", {"getAPTLttotPblancDetail": "", "getRemndrLttotPblancDetail": "무순위 "})
    today = datetime.now(KST).date()
    q = {"page": 1, "perPage": 100, "serviceKey": key,
         "cond[RCRIT_PBLANC_DE::GTE]": (today - timedelta(days=14)).isoformat()}
    # Encoding 키(%2B 등 포함)를 넣어도 동작하도록 한 번 디코딩해 둔다
    key = urllib.parse.unquote(key.strip())
    q["serviceKey"] = key
    rows, errors = [], []
    for ep, label in endpoints.items():
        try:
            try:
                data = json.loads(fetch(base + ep + "?" + urllib.parse.urlencode(q)))
            except urllib.error.HTTPError as e:
                if e.code != 401:
                    raise
                # 쿼리 인증이 거절되면 헤더 인증(Authorization: Infuser <키>)으로 한 번 더
                q2 = {k: v for k, v in q.items() if k != "serviceKey"}
                req = urllib.request.Request(base + ep + "?" + urllib.parse.urlencode(q2),
                                             headers={"User-Agent": UA, "Authorization": f"Infuser {key}"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.loads(r.read())
            rows += [(label, r) for r in data.get("data", [])]
        except Exception as e:
            errors.append(f"{ep}: {e}")
            print(f"  applyhome {ep}: {e}", file=sys.stderr)
    if errors and not rows:
        raise RuntimeError("; ".join(errors) + " — 키 활성화 대기(발급 후 최대 1~2시간), Decoding 키 여부, '분양정보 조회 서비스' 활용신청 여부 확인")
    out = []
    for label, row in rows:
        name = row.get("HOUSE_NM") or row.get("houseNm") or ""
        begin = row.get("RCEPT_BGNDE") or row.get("SUBSCRPT_RCEPT_BGNDE") or ""
        end = row.get("RCEPT_ENDDE") or row.get("SUBSCRPT_RCEPT_ENDDE") or ""
        out.append({
            "source": "applyhome", "keyword": f"{name} {label}청약", "traffic": 0, "category": "청약", "official": True,
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


SOURCES = {"calendar": src_calendar, "google_trends": src_google_trends, "korea_kr": src_korea_kr,
           "google_news": src_google_news, "tv_food": src_tv_food, "applyhome": src_applyhome}


def score(item, now):
    w = CATEGORY_WEIGHT.get(item["category"], 0.6)
    traffic = item.get("traffic", 0)
    base = min(100, (traffic / 2000) * 10) if traffic else 0
    base += min(30, item.get("article_count_24h", 0) * 3)
    base += min(20, item.get("article_count_1h", 0) * 4)
    base += item.get("spike_bonus", 0)
    if item.get("official"):
        base += 25
    if item["source"] == "tv_food":
        base += 20 + min(30, len({n.get("source") for n in item.get("news", [])}) * 6)  # 여러 매체가 다룰수록 검색도 많다
    if item["source"] == "korea_kr" and item.get("rank"):
        base += max(0, 6 - item["rank"]) * 6  # 정책브리핑 실시간 인기 순위
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


def norm_kw(s):
    return re.sub(r"\s+", "", s.lower())


def load_prev(prev_dir, now, hours=3):
    """직전 실행 기록(최근 hours 시간)을 키워드별로 모은다. {키워드: [기록, ...]}"""
    runs = []
    if not prev_dir:
        return runs
    for f in sorted(Path(prev_dir).glob("*.jsonl"))[-2:]:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                at = datetime.fromisoformat(r["at"])
            except Exception:
                continue
            if timedelta(0) < now - at <= timedelta(hours=hours):
                runs.append({norm_kw(x["keyword"]): x for x in (r.get("items") or r.get("top") or [])})
    return runs


def mark_spike(it, runs):
    """직전 실행들보다 갑자기 늘어난 주제에 spike 표시와 가산점을 단다."""
    if not runs or it["source"] in ("calendar", "applyhome", "tv_food"):
        return
    k = norm_kw(it["keyword"])
    past = [r[k] for r in runs if k in r]
    if it["source"] == "google_news":
        prev = [x["article_count_1h"] for x in past if "article_count_1h" in x]
        cur = it.get("article_count_1h", 0)
        if prev and cur >= 3:
            base = sum(prev) / len(prev)
            ratio = (cur + 1) / (base + 1)
            if ratio >= 2:
                it["spike"] = f"최근 1시간 기사 {base:.1f}→{cur}건 ({ratio:.1f}배)"
                it["spike_bonus"] = round(min(40, 10 * ratio), 1)
    elif it["source"] == "google_trends":
        prev = [x.get("traffic", 0) for x in past]
        if not past:
            it["spike"] = "급상승 검색어에 새로 등장"
            it["spike_bonus"] = 15
        elif it.get("traffic", 0) >= 2 * max(prev) > 0:
            it["spike"] = f"검색량 {max(prev):,}→{it['traffic']:,}"
            it["spike_bonus"] = 20
    elif it["source"] == "korea_kr" and not past:
        it["spike"] = "정책브리핑 실시간 인기뉴스에 새로 진입"
        it["spike_bonus"] = 10


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
    ap.add_argument("--prev", default="", help="직전 실행 기록(jsonl) 폴더 — 급상승 비교용")
    ap.add_argument("--only", default="", help="쉼표로 구분한 수집원만 실행")
    ap.add_argument("--evidence", default="", help="원문 수집본 저장 폴더 (Actions 에서만)")
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
    runs = load_prev(a.prev, now)
    seen, ranked = set(), []
    for it in collected:
        k = re.sub(r"\s+", "", it["keyword"].lower())
        if k in seen:
            continue
        seen.add(k)
        if it["source"] != "calendar":  # 캘린더 후보는 자체 점수 사용
            mark_spike(it, runs)
            it["score"] = score(it, now)
        it["already_covered"] = any(it["keyword"].replace(" ", "") in t.replace(" ", "") for t in covered)
        ranked.append(it)
    ranked.sort(key=lambda x: x["score"], reverse=True)

    if a.evidence:
        status["evidence"] = collect_evidence(ranked, a.evidence, cfg)
        print(f"[evidence] {status['evidence']}", file=sys.stderr)
    result = {"generated_at": now.isoformat(), "sources": status, "compared_runs": len(runs),
              "spikes": [c["keyword"] for c in ranked if c.get("spike")], "candidates": ranked}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.history:
        h = Path(a.history) / f"{now:%Y-%m-%d}.jsonl"
        h.parent.mkdir(parents=True, exist_ok=True)
        with h.open("a", encoding="utf-8") as f:
            keep = ("keyword", "category", "score", "source", "traffic", "article_count_24h", "article_count_1h", "spike")
            rows = [{k: c[k] for k in keep if k in c} for c in ranked if c["source"] != "calendar"]
            f.write(json.dumps({"at": now.isoformat(), "items": rows}, ensure_ascii=False) + "\n")
    print(f"후보 {len(ranked)}개 → {out}")
    for c in ranked[:15]:
        print(f"  {c['score']:6.1f}  [{c['category']}] {c['keyword']}  ({c['source']})" + (f"  ↑ {c['spike']}" if c.get("spike") else ""))


if __name__ == "__main__":
    main()
