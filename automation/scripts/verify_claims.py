#!/usr/bin/env python3
"""사실 검증기 — 글에 나온 숫자·날짜가 전부 '출처 원문에 실제로 적힌 문장'으로 뒷받침되는지 기계적으로 확인한다.

규칙
 1. 글마다 automation/claims/<slug>.yml 이 있어야 한다.
 2. 본문의 사실 토큰(날짜, 금액, %, 나이, 인원, 기간, 면적 …)은 전부 어떤 claim 의 value/quote 에 있어야 한다.
    → 출처 없는 숫자가 하나라도 있으면 FAIL.
 3. --fetch: 각 claim 의 source 를 실제로 내려받아 quote 가 원문에 그대로 있는지 확인한다.
    (공백·문장부호 차이는 무시). 원문에 없으면 FAIL.
 4. 공식 출처 필수 카테고리(정부혜택·청약·선거·세금·노동·급여)는 출처가 공식 도메인이어야 한다.
 5. 마감일(deadline)이 지난 글은 FAIL.

claims 파일 형식
  - claim: "청년 특별공급 신청 가능 나이"
    value: "만 19세 이상 39세 이하"
    quote: "만19세 이상 만39세 이하"     # 출처 원문에 그대로 있는 문장 조각 (복붙)
    source: https://www.applyhome.co.kr/...
  - claim: "84㎡의 평 환산"
    value: "25.4평"
    derived: "84 ÷ 3.3058"              # 계산값은 source 대신 계산식
  - claim: "..."
    value: "..."
    quote: "..."
    source: https://...
    manual: "PDF 스캔본이라 자동 확인 불가"   # 자동 확인이 불가능할 때만. 사람 확인 목록으로 넘어감

사용: python3 automation/scripts/verify_claims.py _drafts/slug.md [--fetch] [--summary 파일]
"""
import argparse
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from style_check import split_front_matter, parse_fm, plain  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; semter-factcheck/1.0)"

OFFICIAL_REQUIRED = {"정부혜택", "청약", "선거", "세금", "노동·급여",
                     # 미국(Blogger) 글
                     "Benefits", "Taxes", "Health Insurance", "Student Aid", "Housing", "Elections", "Recalls"}
# 방송 맛집·이슈 글은 공식 출처가 없는 경우가 많아, 서로 다른 매체 2곳 이상이 같은 사실을 적었는지로 본다
CROSS_CHECK_REQUIRED = {"방송정보", "이슈", "Trending"}
OFFICIAL_DOMAINS = re.compile(
    r"(\.go\.kr|\.korea\.kr|^korea\.kr|applyhome\.co\.kr|lh\.or\.kr|i-sh\.co\.kr|gh\.or\.kr|nhuf\.molit\.go\.kr|"
    r"khug\.or\.kr|nps\.or\.kr|nhis\.or\.kr|kinfa\.or\.kr|kbs\.co\.kr|imbc\.com|sbs\.co\.kr|ebs\.co\.kr|"
    r"\.gov|\.mil)$")  # 미국 연방·주 정부

# 사실 토큰: 단위가 붙은 숫자, 날짜, 금액, 비율
TOKEN_RES = [
    r"\d{4}\s*[년.\-/]\s*\d{1,2}\s*[월.\-/]\s*\d{1,2}\s*일?",
    r"\d{1,2}\s*월\s*\d{1,2}\s*일",
    r"\d{4}\s*년(?:\s*\d{1,2}\s*월)?",
    r"\d[\d,]*(?:\.\d+)?\s*(?:만|억|천만|천|백만)?\s*원",
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|퍼센트|%p|%포인트|포인트)",
    r"(?:만\s*)?\d[\d,]*(?:\.\d+)?\s*(?:세|살|명|세대|가구|호|개월|주|일|시간|시|분|㎡|평|배|회|건|곳|개)",
]
TOKEN_RE = re.compile("|".join(f"(?:{r})" for r in TOKEN_RES))
# 영어(미국) 글: 달러, 날짜, 연도, 비율, 기간
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
TOKEN_RES_EN = [
    _MON + r"\.?\s+\d{1,2}(?!\d)(?:st|nd|rd|th)?(?:,?\s+\d{4})?",
    r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|trillion|k)\b)?",
    r"\d[\d,]*(?:\.\d+)?\s?(?:%|percent)",
    r"\b\d[\d,]*(?:\.\d+)?\s?(?:days?|weeks?|months?|years?|hours?|minutes?|people|households|million|billion)\b",
    r"\b(?:19|20)\d{2}\b",
]
TOKEN_RE_EN = re.compile("|".join(f"(?:{r})" for r in TOKEN_RES_EN), re.I)


def norm(s):
    s = str(s).lower()
    s = s.replace("만 ", "만").replace("퍼센트", "%")
    return re.sub(r"[\s,·ㆍ\-–—~∼〜()\[\]\"'“”‘’.:;/]", "", s)


def fact_tokens(body, lang="ko"):
    text = plain(body)
    text = re.sub(r"^#+.*$", "", text, flags=re.M)  # 소제목은 본문에서 다시 나온다고 보고 제외
    toks = []
    for m in (TOKEN_RE_EN if lang == "en" else TOKEN_RE).finditer(text):
        t = m.group(0).strip()
        if re.fullmatch(r"\d\s*(개|곳|회|건|가지)", t):  # '1곳', '3개' 같은 사소한 개수는 제외
            continue
        toks.append(t)
    return sorted(set(toks), key=toks.index)


def load_claims(path):
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(data, dict):
        data = data.get("claims", [])
    return data


def page_text(url, cache={}):
    if url in cache:
        return cache[url]
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw, ctype = r.read(), r.headers.get("Content-Type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(raw)
            f.flush()
            txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    else:
        enc = re.search(r"charset=([\w-]+)", ctype)
        try:
            txt = raw.decode(enc.group(1) if enc else "utf-8")
        except (LookupError, UnicodeDecodeError):
            txt = raw.decode("euc-kr", errors="ignore")
        txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        import html as _h
        txt = _h.unescape(txt)
    cache[url] = txt
    return txt


def verify(draft, fetch=False, today=None):
    today = today or datetime.now(KST).date()
    draft = Path(draft)
    fm_raw, body = split_front_matter(draft.read_text(encoding="utf-8"))
    fm = parse_fm(fm_raw)
    slug = re.sub(r"\.(tistory|naver)$", "", re.sub(r"^\d{4}-\d{2}-\d{2}-", "", draft.stem))
    cpath = ROOT / "automation" / "claims" / f"{slug}.yml"
    fails, warns, manual, rows = [], [], [], []

    if not cpath.exists():
        return {"file": str(draft), "fail": [f"claims 파일 없음: {cpath.relative_to(ROOT)}"], "warn": [], "manual": [], "rows": []}
    claims = load_claims(cpath)
    category = fm.get("category", "")

    dl = fm.get("deadline")
    if dl:
        try:
            if datetime.strptime(dl, "%Y-%m-%d").date() < today:
                fails.append(f"마감일 {dl} 이 이미 지남 — 발행하면 안 되는 글")
        except ValueError:
            fails.append(f"deadline 형식 오류: {dl}")

    # 교차 확인: 방송 맛집·이슈 글은 공식 출처가 아닌 사실마다 다른 매체 1곳(source2/quote2)을 더 댄다
    # secondary_ok: 공식 원문을 열 수 없어 언론 보도로 대신한 claim 도 같은 교차 확인을 받는다
    if category in CROSS_CHECK_REQUIRED or any(c.get("secondary_ok") for c in claims):
        extra = []
        for c in claims:
            if c.get("derived") or not c.get("source"):
                continue
            if category not in CROSS_CHECK_REQUIRED and not c.get("secondary_ok"):
                continue
            h1 = urlparse(c["source"]).hostname or ""
            if OFFICIAL_DOMAINS.search(h1):
                continue
            if not (c.get("source2") and c.get("quote2")):
                fails.append(f"{c.get('claim', '')}: '{category}' 글은 공식 출처가 아니면 다른 매체 source2/quote2 로 교차 확인 필요")
            elif (urlparse(c["source2"]).hostname or "") == h1:
                fails.append(f"{c.get('claim', '')}: source2 가 source 와 같은 매체 — 다른 매체여야 함")
            else:
                extra.append({"claim": f"{c.get('claim', '')} (교차)", "value": c["value"], "quote": c["quote2"],
                              "source": c["source2"], "value_note": "교차 확인", "secondary_ok": c.get("secondary_ok")})
        claims = claims + extra

    support = ""
    for i, c in enumerate(claims, 1):
        label = f"#{i} {c.get('claim', '')}"
        if not c.get("value"):
            fails.append(f"{label}: value 없음")
            continue
        support += norm(c.get("value", "")) + "|" + norm(c.get("quote", "")) + "|"
        if c.get("derived"):
            rows.append((label, c["value"], "계산", c["derived"], "✓ 계산값"))
            continue
        src, quote = c.get("source"), c.get("quote")
        if not src or not quote:
            fails.append(f"{label}: source 와 quote 가 모두 있어야 함 (계산값이면 derived)")
            continue
        host = urlparse(src).hostname or ""
        if category in OFFICIAL_REQUIRED and not OFFICIAL_DOMAINS.search(host) and not c.get("secondary_ok"):
            fails.append(f"{label}: '{category}' 글은 공식 출처 필요 — {host}")
        if norm(c["value"]) not in norm(quote) and not c.get("value_note"):
            warns.append(f"{label}: value '{c['value']}' 가 quote 안에 그대로 없음 (표현이 다르면 value_note 로 설명)")
        if c.get("manual") and not fetch:
            manual.append(f"{label} — {src} ({c['manual']})")
            rows.append((label, c["value"], host, quote, "△ 사람 확인"))
            continue
        if fetch:
            try:
                ok = norm(quote) in norm(page_text(src))
                if c.get("manual"):
                    # 작성 세션이 원문을 못 읽은 claim: 원문에서 찾으면 자동 해결, 못 찾으면 사람 확인
                    if not ok:
                        manual.append(f"{label} — {src} ({c['manual']}; 원문에서 인용문을 찾지 못함)")
                    rows.append((label, c["value"], host, quote, "✓ 원문 일치" if ok else "△ 사람 확인"))
                    continue
            except Exception as e:
                import evidence
                # 봇 차단(403)이면 브라우저로 한 번 더 열어 본다 (ssa.gov 처럼 브라우저로는 열리는 곳)
                if "403" in str(e):
                    try:
                        txt = evidence.browser_text(src)
                        ok = norm(quote) in norm(txt)
                        if not ok:
                            fails.append(f"{label}: quote 가 출처 원문에 없음 — {src}")
                        rows.append((label, c["value"], host, quote, "✓ 원문 일치 (브라우저)" if ok else "✗ 원문 불일치"))
                        continue
                    except Exception:
                        pass
                # 작성 세션에서 막힌 사이트는 레이더(Actions)가 받아 둔 원문 수집본으로 대조한다
                rec = evidence.load(src)
                if rec:
                    ok = norm(quote) in norm(rec["text"])
                    if not ok:
                        fails.append(f"{label}: quote 가 원문 수집본({rec['fetched_at']})에 없음 — {src}")
                    rows.append((label, c["value"], host, quote,
                                 f"✓ 원문 일치 (수집본 {rec['fetched_at'][:16]})" if ok else "✗ 수집본 불일치"))
                    continue
                # 수집본도 없으면 통과가 아니라 '사람 확인 필수'로 넘긴다
                manual.append(f"{label} — {src} (자동 열기 실패: {e})")
                rows.append((label, c["value"], host, quote, "△ 열기 실패·사람 확인"))
                continue
            if not ok:
                fails.append(f"{label}: quote 가 출처 원문에 없음 — {src}")
            rows.append((label, c["value"], host, quote, "✓ 원문 일치" if ok else "✗ 원문 불일치"))
        else:
            rows.append((label, c["value"], host, quote, "· 미확인(오프라인)"))

    # 카드 이미지 속 글자도 사실 주장 — 본문과 똑같이 claims 로 뒷받침돼야 한다
    try:
        import yaml
        from make_cards import card_text
        fm_full = yaml.safe_load(fm_raw) or {}
        body_and_cards = body + "\n" + card_text(fm_full)
        licensed = {str(i.get("src")) for i in (fm_full.get("images") or []) if i.get("license") and i.get("credit")}
    except Exception:
        body_and_cards, licensed = body, set()
    # 직접 만든 카드(/assets/cards/) 말고 외부 이미지는 라이선스·출처가 front matter images 에 있어야 한다
    for src in re.findall(r"!\[[^\]]*\]\(([^)\s]+)", body) + re.findall(r'<img[^>]+src="([^"]+)"', body):
        if "/assets/cards/" not in src and src not in licensed:
            fails.append(f"라이선스 확인 안 된 이미지: {src} — front matter images 에 license·credit 를 적거나 빼기")
    for t in fact_tokens(body_and_cards, fm.get("lang", "ko")):
        if norm(t) not in support:
            fails.append(f"출처 없는 사실 토큰: '{t}' — claims 에 추가하거나 본문에서 빼기")

    return {"file": str(draft), "fail": fails, "warn": warns, "manual": manual, "rows": rows}


def render(results):
    out = []
    for r in results:
        verdict = "✗ FAIL" if r["fail"] else ("△ 사람 확인 필요" if r["manual"] else "✓ PASS")
        out.append(f"### {verdict} — `{r['file']}`\n")
        if r["rows"]:
            out.append("| claim | 값 | 출처 | 원문 인용 | 결과 |\n|---|---|---|---|---|")
            for row in r["rows"]:
                out.append("| " + " | ".join(str(x).replace("|", "/")[:80] for x in row) + " |")
            out.append("")
        for f in r["fail"]:
            out.append(f"- ✗ {f}")
        for w in r["warn"]:
            out.append(f"- △ {w}")
        for m in r["manual"]:
            out.append(f"- [ ] 사람 확인: {m}")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fetch", action="store_true", help="출처를 실제로 내려받아 인용문 대조")
    ap.add_argument("--summary", help="결과 마크다운을 이 파일에 덧붙임 (GITHUB_STEP_SUMMARY)")
    a = ap.parse_args()
    results = [verify(f, fetch=a.fetch) for f in a.files]
    md = render(results)
    print(md)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write("## 사실 검증\n\n" + md)
    sys.exit(1 if any(r["fail"] for r in results) else 0)


if __name__ == "__main__":
    main()
