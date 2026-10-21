#!/usr/bin/env python3
"""인도·쇼피 국가별 Blogger 글 재검토 (기계 검사). 작성 세션은 커밋 전에, Actions 는 발행 전에 돌린다.

글마다:
  1. verify_claims · style_check 통과 (사실 근거, 체험 날조, 관계 공개, 이모지)
  2. 링크 허용 목록: 쇼핑 링크는 우리 스토어(products/stores.yml·<key>.yml)와 config affiliates 에 있는 것만
  3. 효능·의약 표현 금지 (치료·완치·미백 보장 등 — 화장품 광고 규제 위험)
  4. 확정 아닌 일정·금액('expected', 'likely' …)은 제목이나 첫 문단에서 밝혔는지
  5. 같은 블로그·같은 언어의 최근 글과 너무 비슷하지 않은지 (4-gram 0.35, 같은 문장 2개 이하)
블로그마다:
  6. 하루 편수(그 나라 날짜): per_day 이하, 언어별 할당(langs) 이하
  7. 우리 스토어 상품 글: 블로그당 하루 1편 이하

  python3 automation/scripts/blog_audit.py [파일 …]   # 파일을 주면 그 글과 그 블로그의 하루 규칙만
종료 코드: 문제가 있으면 1
"""
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from similarity_check import compare  # noqa: E402
from style_check import check as style_check, parse_fm, plain, split_front_matter  # noqa: E402
from verify_claims import verify  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHOP_HOST = re.compile(r"https?://(?:[\w-]+\.)*(shopee\.[\w.]+|shp\.ee|amazon\.[\w.]+|amzn\.to|lazada\.[\w.]+|invol\.co)(/[^)\s\"]*)?", re.I)
# 화장품·생활용품을 의약품처럼 말하는 표현 (나라별 화장품 광고 규제에서 공통으로 문제 되는 것)
MEDICAL = {
    "en": [r"\bcures?\b", r"\btreats? (?:acne|eczema|melasma|psoriasis)", r"\bheals?\b", r"\bguarantee[sd]? (?:results|whitening)", r"\bpermanent(?:ly)? whiten", r"\bmedical[- ]grade\b", r"\bclinically proven\b"],
    "vi": [r"chữa (?:khỏi|trị)", r"điều trị (?:mụn|nám)", r"trắng da vĩnh viễn", r"cam kết trắng"],
    "id": [r"menyembuhkan", r"mengobati (?:jerawat|flek)", r"memutihkan permanen", r"dijamin putih"],
    "th": [r"รักษา(?:สิว|ฝ้า)หาย", r"หายขาด", r"ขาวถาวร", r"การันตีขาว"],
    "zh-Hant": [r"治療(?:痘痘|青春痘|黑斑)", r"根治", r"永久美白", r"保證美白"],
    "hi": [r"इलाज", r"पूरी तरह ठीक"],
}
TENTATIVE = re.compile(r"\b(expected|likely|reportedly|tentative|proposed)\b|संभावित|अनुमानित", re.I)


def load(p):
    return yaml.safe_load((ROOT / p).read_text(encoding="utf-8")) if (ROOT / p).exists() else {}


def allowed_links(key, cfg):
    """우리 스토어 주소·상품 주소 + 설정된 제휴 접두사"""
    out = []
    st = (load("automation/blogs/shop/products/stores.yml") or {}).get(key) or {}
    if st.get("url") and not st.get("hold"):
        out.append(st["url"].rstrip("/"))
    prod = load(f"automation/blogs/shop/products/{key}.yml") or {}
    out += [p["url"] for p in prod.get("products", []) if p.get("url")]
    aff = cfg.get("affiliates", {}) or {}
    if aff.get("amazon_sg_tag") and key == "sg":
        out.append("https://www.amazon.sg/")
    for k, v in (aff.get("lazada") or {}).items():
        if k == key and v:
            out.append(v)
    return out


def store_urls(key):
    st = (load("automation/blogs/shop/products/stores.yml") or {}).get(key) or {}
    prod = load(f"automation/blogs/shop/products/{key}.yml") or {}
    urls = [st["url"].rstrip("/")] if st.get("url") else []
    return urls + [p["url"] for p in prod.get("products", []) if p.get("url")]


def post_issues(md, key, bc, cfg, siblings):
    text = md.read_text(encoding="utf-8")
    fm_raw, body = split_front_matter(text)
    fm = parse_fm(fm_raw)
    lang = fm.get("lang", "en")
    issues = []
    v, s = verify(md, fetch=False), style_check(md)
    issues += [f"사실: {x}" for x in v["fail"]] + [f"문체: {x}" for x in s["fail"]]
    if fm.get("blog") and fm["blog"] != key:
        issues.append(f"front matter blog: {fm['blog']} 인데 {key} 폴더에 있음")
    if lang not in (bc.get("langs") or {bc.get("lang", "en"): 1}):
        issues.append(f"이 블로그에서 쓰지 않는 언어: {lang}")
    ok = allowed_links(key, cfg)
    for m in SHOP_HOST.finditer(body):
        u = m.group(0)
        if not any(u.startswith(a) for a in ok):
            issues.append(f"허용 목록에 없는 쇼핑·제휴 링크: {u[:80]}")
    flat = plain(body)
    for rx in MEDICAL.get(lang, []):
        if re.search(rx, flat, re.I):
            issues.append(f"효능·의약 표현: /{rx}/ — 라벨·상세페이지에 있는 표현으로 바꾸기")
    if TENTATIVE.search(flat):
        head = (fm.get("title", "") + " " + flat[:400])
        if not TENTATIVE.search(head):
            issues.append("본문에 'expected/likely' 같은 미확정 정보가 있는데 제목·첫 문단에서 밝히지 않음")
    for o in siblings:
        if o == md:
            continue
        jac, same = compare(md, o)
        if jac > 0.35 or len(same) > 2:
            issues.append(f"{o.name} 와 너무 비슷함 (유사도 {jac:.2f}, 같은 문장 {len(same)}개)")
    return issues, fm


def main():
    cfg = load("automation/config.yml")
    only = {Path(a).resolve() for a in sys.argv[1:]}
    blogs = {k: b for k, b in cfg.get("blogs", {}).items() if k != "us"}
    bad = 0
    for key, bc in blogs.items():
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(bc.get("tz", "UTC"))
        today = datetime.now(tz).date()
        drafts = sorted((ROOT / bc["drafts"]).glob("*.md"))
        recent = [p for p in drafts if (lambda a: a and (today - datetime.fromisoformat(a).date()) <= timedelta(days=14))(
            parse_fm(split_front_matter(p.read_text(encoding="utf-8"))[0]).get("info_as_of"))]
        targets = [p for p in recent if not only or p.resolve() in only]
        if not targets:
            continue
        per_day, langs = defaultdict(int), defaultdict(int)
        stores = defaultdict(int)
        st_urls = store_urls(key)
        by_lang = defaultdict(list)
        for p in recent:
            fm = parse_fm(split_front_matter(p.read_text(encoding="utf-8"))[0])
            by_lang[fm.get("lang", "en")].append(p)
        for p in recent:
            t = p.read_text(encoding="utf-8")
            fm = parse_fm(split_front_matter(t)[0])
            d = fm.get("info_as_of")
            per_day[d] += 1
            langs[(d, fm.get("lang", "en"))] += 1
            if fm.get("store", "").lower() == "true" or any(u in t for u in st_urls):
                stores[d] += 1
        print(f"── {key} ({bc.get('label', '')})")
        for p in targets:
            fm = parse_fm(split_front_matter(p.read_text(encoding="utf-8"))[0])
            issues, _ = post_issues(p, key, bc, cfg, by_lang[fm.get("lang", "en")])
            mark = "✗" if issues else "✓"
            print(f"  {mark} {p.name}")
            for i in issues:
                print(f"      - {i}")
            bad += bool(issues)
        for d, n in sorted(per_day.items()):
            if bc.get("per_day") and n > int(bc["per_day"]):
                print(f"  ✗ {d}: {n}편 — 하루 {bc['per_day']}편 넘음")
                bad += 1
            if stores.get(d, 0) > 1:
                print(f"  ✗ {d}: 우리 스토어 상품 글 {stores[d]}편 — 하루 1편까지")
                bad += 1
        for (d, lg), n in sorted(langs.items()):
            cap = (bc.get("langs") or {}).get(lg)
            if cap and n > int(cap):
                print(f"  ✗ {d}: {lg} {n}편 — {lg} 하루 {cap}편까지")
                bad += 1
    print("재검토 통과" if not bad else f"문제 {bad}건")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
