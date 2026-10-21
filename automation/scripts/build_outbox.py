#!/usr/bin/env python3
"""발행 대기함 — 검증을 통과한 초안을 플랫폼별로 바로 복사·붙여넣기 할 수 있게 한 페이지로 모은다.

  네이버판  : _drafts/<slug>.md
  티스토리판: automation/variants/<slug>.tistory.md  (없으면 네이버판을 같이 씀 — 비권장)

카드마다: 검증 결과, 사람 확인 항목, 추천 발행 시각, [제목][본문][태그] 복사 버튼,
티스토리는 HTML 모드용 원본 복사, '발행함' 체크(브라우저에 저장).

사용: python3 automation/scripts/build_outbox.py [--out exports/outbox.html]
"""
import argparse
import base64
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from export_paste import STYLE, fm_sources, fm_value, inline_styles, readable_paragraphs  # noqa: E402
from similarity_check import compare  # noqa: E402
from style_check import check as style_check, split_front_matter  # noqa: E402
from verify_claims import verify  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))


def fm_list(fm, key):
    try:
        v = (yaml.safe_load(fm) or {}).get(key)
    except yaml.YAMLError:
        return []
    return v if isinstance(v, list) else ([v] if v else [])


def render(md_path, site):
    fm, body = split_front_matter(md_path.read_text(encoding="utf-8"))
    body = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "", body, flags=re.S)
    body = re.sub(r'<div class="callout"[^>]*>', '<div style="border:2px solid #222;padding:14px 16px;margin:16px 0;">', body)
    lang = fm_value(fm, "lang") or "ko"
    if lang == "ko":
        body = readable_paragraphs(body)  # 문장마다 줄바꿈, 2문장씩 문단
    h = inline_styles(markdown.markdown(body, extensions=["tables", "sane_lists", "md_in_html"]))
    tool = fm_value(fm, "related_tool")
    if tool:
        h += f'<p style="{STYLE["p"]}"><b>바로 계산해 보기 →</b> <a href="{site}/tools/{tool}/">{site.replace("https://", "")}/tools/{tool}/</a></p>'
    src = fm_sources(fm)
    if src:
        h += f'<p style="{STYLE["p"]}margin-top:28px;"><b>출처</b></p><ol>' + "".join(
            f'<li style="{STYLE["li"]}"><a href="{html.escape(u)}">{html.escape(t)}</a></li>' for t, u in src) + "</ol>"
    asof = fm_value(fm, "info_as_of")
    if asof:
        h += f'<p style="{STYLE["p"]}color:#777;font-size:14px;">정보 기준일: {html.escape(asof)}</p>'
    en = lang != "ko"  # 영어·베트남어·태국어 … — Blogger 글 (라벨, 영문 꼬리말)
    if asof and en:
        h = h.replace(f"정보 기준일: {html.escape(asof)}", f"Last checked: {html.escape(asof)}")
    if src and en:
        h = h.replace("<b>출처</b>", "<b>Sources</b>")
    # 블로그 태그는 띄어쓰기 없이 (Blogger 라벨은 띄어쓰기 허용)
    tags = [str(t).strip() for t in fm_list(fm, "labels")] if en else [re.sub(r"\s+", "", str(t)) for t in fm_list(fm, "tags")]
    # 이미지: 복사용 본문은 사이트 절대주소, 대기함 미리보기·이미지 복사 버튼은 data URI (아티팩트는 외부 이미지를 못 불러옴)
    images, preview = [], h
    for m in re.finditer(r'<img([^>]*?)src="(/assets/[^"]+)"([^>]*)>', h):
        local = ROOT / m.group(2).lstrip("/")
        alt = (re.search(r'alt="([^"]*)"', m.group(0)) or [None, ""])[1]
        if local.exists():
            mime = "image/png" if local.suffix == ".png" else "image/jpeg"
            data = f"data:{mime};base64," + base64.b64encode(local.read_bytes()).decode()
            # 미리보기는 같은 data URI 를 다시 넣지 않고 번호로 가리킨다 (아티팩트 16MB 한도 — 브라우저에서 채움)
            preview = preview.replace(f'src="{m.group(2)}"', f'src="#img{len(images)}"', 1)
            images.append({"alt": alt, "data": data})
    h = re.sub(r'src="(/assets/[^"]+)"', lambda m: f'src="{site}{m.group(1)}"', h)
    # 쇼핑·제휴 링크는 rel="sponsored" (구글 링크 표시 지침), 새 창
    h = re.sub(r'<a href="(https?://(?:[\w-]+\.)*(?:shopee\.[\w.]+|shp\.ee|amazon\.[\w.]+|amzn\.to|lazada\.[\w.]+|invol\.co)[^"]*)"',
               r'<a href="\1" rel="sponsored nofollow noopener" target="_blank"', h)
    h = re.sub(r"<img ", '<img style="max-width:100%;height:auto;display:block;margin:16px auto;" ', h)
    preview = re.sub(r"<img ", '<img style="max-width:100%;height:auto;display:block;margin:16px auto;" ', preview)
    return {"title": fm_value(fm, "title"), "html": h, "preview": preview, "images": images, "tags": tags, "fm": fm,
            "description": fm_value(fm, "description"), "permalink": fm_value(fm, "permalink")}


URGENT_CATS = {"방송정보", "이슈", "Recalls"}


def is_urgent(fm, md_text):
    """그때그때 올려야 하는 글(방송 맛집·급상승 이슈·리콜, front matter publish: now) — 예약 말고 즉시 발행."""
    return fm_value(fm, "publish") == "now" or fm_value(fm, "category") in URGENT_CATS


def place_todos(md_text):
    """본문 지도 링크의 가게 → 에디터 [장소] 첨부 안내 (장소 카드에 지도·대표사진·리뷰가 함께 나온다)."""
    from urllib.parse import unquote
    names = []
    for q in re.findall(r"map\.naver\.com/p/search/([^)\s]+)", md_text):
        n = unquote(q)
        if n not in names:
            names.append(n)
    return [f"네이버 에디터 [장소] 버튼 → '{n}' 검색해 첨부 (티스토리는 [지도])" for n in names]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="exports/outbox.html")
    ap.add_argument("--fetch", action="store_true", help="출처 원문을 실제로 내려받아 대조 (네트워크 필요)")
    ap.add_argument("--artifact", help="Claude 아티팩트용 사본 경로 (문서 골격 태그 제거)")
    a = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "automation" / "config.yml").read_text(encoding="utf-8"))
    site = cfg.get("site_url", "").rstrip("/")
    pub = cfg.get("publish", {})
    spacing = int(pub.get("spacing_minutes", 90))
    hours = pub.get("hours", [7, 23])

    now = datetime.now(KST)
    slot = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    cards = []
    keep_days = int(pub.get("outbox_days", 21))
    for md in sorted((ROOT / "_drafts").glob("*.md")):
        asof = fm_value(split_front_matter(md.read_text(encoding="utf-8"))[0], "info_as_of")
        try:
            if asof and (now.date() - datetime.fromisoformat(asof).date()).days > keep_days:
                continue  # 오래된 초안은 대기함에서 내림 (파일은 그대로)
        except ValueError:
            pass
        slug = md.stem
        naver = render(md, site)
        var = ROOT / "automation" / "variants" / f"{slug}.tistory.md"
        tistory = render(var, site) if var.exists() else None
        v = verify(md, fetch=a.fetch)
        s = style_check(md)
        sim = compare(md, var) if var.exists() else None
        problems = list(v["fail"]) + [f"문체: {f}" for f in s["fail"]]
        if var.exists():
            problems += [f"티스토리판: {f}" for f in verify(var, fetch=a.fetch)["fail"]]
            if sim and (sim[0] > 0.35 or len(sim[1]) > 2):
                problems.append(f"두 버전이 너무 비슷함 (유사도 {sim[0]:.2f})")
        fm = naver["fm"]
        text = md.read_text(encoding="utf-8")
        urgent = is_urgent(fm, text)
        if not urgent:
            while not (hours[0] <= slot.hour < hours[1]):
                slot = (slot + timedelta(hours=1)).replace(minute=0)
        cards.append({
            "slug": slug, "category": fm_value(fm, "category"), "deadline": fm_value(fm, "deadline"),
            "trend": fm_value(fm, "trend") or fm_value(fm, "cycle"), "urgent": urgent,
            "slot": "지금 바로" if urgent else slot.strftime("%m/%d %H:%M"), "todo": place_todos(text),
            "ok": not problems, "problems": problems, "manual": v["manual"], "style": s["score"],
            "similarity": round(sim[0], 2) if sim else None,
            "naver": {k: naver[k] for k in ("title", "html", "preview", "images", "tags")},
            "tistory": {k: tistory[k] for k in ("title", "html", "preview", "images", "tags")} if tistory else None,
        })
        if not urgent:
            slot += timedelta(minutes=spacing)

    # ── 해외(미국 · Google Blogger) ── 영어 글 한 판, 추천 발행 시각은 미국 동부 시간
    us_cards = []
    upub = cfg.get("us_publish", {})
    et = ZoneInfo("America/New_York")  # 서머타임 반영 (Blogger 예약 시각과 같은 기준)
    uh = upub.get("hours", [6, 22])
    uslot = (datetime.now(et) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    # Blogger 자동 예약 발행 기록 (blogger-publish.yml) — 예약된 글은 그 시각을 보여 주고 '발행함'으로 친다
    sched_p = ROOT / "automation" / "state" / "blogger_scheduled.json"
    sched = json.loads(sched_p.read_text(encoding="utf-8")) if sched_p.exists() else {}
    for md in sorted((ROOT / "automation" / "global" / "drafts").glob("*.md")):
        asof = fm_value(split_front_matter(md.read_text(encoding="utf-8"))[0], "info_as_of")
        try:
            if asof and (now.date() - datetime.fromisoformat(asof).date()).days > keep_days:
                continue
        except ValueError:
            pass
        r = render(md, site)
        v = verify(md, fetch=a.fetch)
        s = style_check(md)
        problems = list(v["fail"]) + [f"style: {f}" for f in s["fail"]]
        fm = r["fm"]
        text = md.read_text(encoding="utf-8")
        urgent = is_urgent(fm, text)
        bs = sched.get(md.stem)
        if not urgent and not bs:
            while not (uh[0] <= uslot.hour < uh[1]):
                uslot = (uslot + timedelta(hours=1)).replace(minute=0)
        if bs:
            pa = datetime.fromisoformat(bs["publish_at"])
            slot_txt = pa.astimezone(et).strftime("%m/%d %H:%M") + " ET"
            slot2_txt = pa.astimezone(KST).strftime("%m/%d %H:%M KST") + " · Blogger 자동"
        else:
            slot_txt = "지금 바로" if urgent else uslot.strftime("%m/%d %H:%M") + " ET"
            slot2_txt = "" if urgent else uslot.astimezone(KST).strftime("%m/%d %H:%M KST")
        us_cards.append({
            "slug": md.stem, "category": fm_value(fm, "category"), "deadline": fm_value(fm, "deadline"),
            "trend": fm_value(fm, "trend") or fm_value(fm, "cycle"), "urgent": urgent, "todo": [],
            "slot": slot_txt, "slot2": slot2_txt, "auto": bool(bs), "auto_url": (bs or {}).get("url", ""),
            "ok": not problems, "problems": problems, "manual": v["manual"], "style": s["score"], "similarity": None,
            "blogger": {k: r[k] for k in ("title", "html", "preview", "images", "tags", "description", "permalink")},
        })
        if not urgent and not bs:
            uslot += timedelta(minutes=int(upub.get("spacing_minutes", 120)))

    # ── 인도·쇼피 국가별 Blogger — 전부 자동 예약 발행이라 복사용 본문 없이 상태만 (대기함 16MB 한도)
    from blogger_publish import blogs_config
    names = json.loads((ROOT / "automation" / "state" / "blogs.json").read_text(encoding="utf-8")) \
        if (ROOT / "automation" / "state" / "blogs.json").exists() else {}
    extra = {"in": [], "shop": []}
    for key, bc in blogs_config(cfg).items():
        if key == "us":
            continue
        bst_p = ROOT / bc["state"]
        bst = json.loads(bst_p.read_text(encoding="utf-8")) if bst_p.exists() else {}
        btz = ZoneInfo(bc.get("tz", "UTC"))
        for md in sorted((ROOT / bc["drafts"]).glob("*.md")):
            fm, _ = split_front_matter(md.read_text(encoding="utf-8"))
            asof = fm_value(fm, "info_as_of")
            try:
                if asof and (now.date() - datetime.fromisoformat(asof).date()).days > 7:
                    continue  # 자동 발행 블로그는 최근 7일만 보여 준다
            except ValueError:
                pass
            v, s_ = verify(md, fetch=a.fetch), style_check(md)
            problems = list(v["fail"]) + [f"style: {f}" for f in s_["fail"]]
            bs = bst.get(md.stem)
            if bs and bs.get("publish_at"):
                pa = datetime.fromisoformat(bs["publish_at"])
                slot_txt, slot2 = pa.astimezone(btz).strftime("%m/%d %H:%M"), pa.astimezone(KST).strftime("%m/%d %H:%M KST")
            else:
                slot_txt, slot2 = ("발행 불가" if problems else "다음 실행"), ""
            extra["shop" if bc.get("kind") == "shop" else "in"].append({
                "slug": md.stem, "compact": True, "blog": (names.get(key) or {}).get("name") or bc.get("label", key),
                "blog_label": bc.get("label", key), "category": fm_value(fm, "category"), "deadline": fm_value(fm, "deadline"),
                "trend": fm_value(fm, "trend"), "urgent": is_urgent(fm, ""), "todo": [], "slot": slot_txt, "slot2": slot2,
                "auto": bool(bs and bs.get("status") not in (None, "", "DRAFT")), "auto_url": (bs or {}).get("url", ""),
                "ok": not problems, "problems": problems, "manual": v["manual"], "style": s_["score"], "similarity": None,
                "blogger": {"title": fm_value(fm, "title"), "tags": fm_list(fm, "labels")},
            })

    # 즉시 발행 글을 맨 위로 (나머지는 추천 시각 순서 그대로)
    cards.sort(key=lambda c: not c["urgent"])
    us_cards.sort(key=lambda c: not c["urgent"])
    data = {"kr": cards, "us": us_cards, "in": extra["in"], "shop": extra["shop"]}
    page = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")) \
                   .replace("__GENERATED__", now.strftime("%Y-%m-%d %H:%M")) \
                   .replace("__COUNT__", f"국내 {len(cards)} · 미국 {len(us_cards)} · 인도 {len(extra['in'])} · 쇼피 {len(extra['shop'])}")
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    if a.artifact:
        frag = re.sub(r"^<!doctype html>\s*<html[^>]*><head><meta charset=\"utf-8\"><meta name=\"viewport\"[^>]*>\n", "", page)
        frag = frag.replace("</head><body>", "").replace("</body></html>", "")
        Path(a.artifact).write_text(frag, encoding="utf-8")
    print(f"{out.relative_to(ROOT)} — 국내 {len(cards)}편 ({sum(c['ok'] for c in cards)}편 발행 가능), "
          f"해외 {len(us_cards)}편 ({sum(c['ok'] for c in us_cards)}편 발행 가능)")


TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>발행 대기함</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
/* 안내 표지판 — 흰 바탕, 먹색 글자, 하늘색은 '여기 보세요' 면(面)에만. 셈터 사이트·카드와 같은 계열 */
:root{--paper:#fff;--ink:#0b0b0c;--ink2:rgba(11,11,12,.7);--muted:rgba(11,11,12,.5);--hair:rgba(11,11,12,.14);--sky:#7cc8ff;--sky-soft:rgba(124,200,255,.22);--on-sky:#0b0b0c}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0b0b0c;--ink:#fff;--ink2:rgba(255,255,255,.75);--muted:rgba(255,255,255,.5);--hair:rgba(255,255,255,.16);--sky-soft:rgba(124,200,255,.18);color-scheme:dark}}
:root[data-theme="dark"]{--paper:#0b0b0c;--ink:#fff;--ink2:rgba(255,255,255,.75);--muted:rgba(255,255,255,.5);--hair:rgba(255,255,255,.16);--sky-soft:rgba(124,200,255,.18);color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);background:var(--paper);font:15px/1.6 "IBM Plex Sans KR",sans-serif;word-break:keep-all;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:960px;margin:0 auto}
header{padding:28px 0 18px;border-bottom:1px solid var(--ink);display:flex;flex-wrap:wrap;gap:6px 20px;align-items:flex-end;justify-content:space-between}
h1{margin:0;font:700 clamp(1.7rem,5vw,2.4rem)/1.05 "IBM Plex Sans KR",sans-serif;letter-spacing:-.04em;display:flex;align-items:center;gap:10px}
h1::before{content:"";width:14px;height:14px;background:var(--sky)}
.meta{font:500 12px/1.4 "IBM Plex Mono","IBM Plex Sans KR",monospace;color:var(--muted)}
.region{display:flex;margin-top:18px;border:1px solid var(--ink)}
.region button{flex:1;font:700 15px "IBM Plex Sans KR";padding:12px 10px;border:0;background:transparent;color:var(--ink);cursor:pointer}
.region button+button{border-left:1px solid var(--ink)}
.region button[aria-selected=true]{background:var(--sky);color:var(--on-sky)}
.region small{display:block;font:500 11px "IBM Plex Mono","IBM Plex Sans KR",monospace;opacity:.7;margin-top:2px}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 0}
.filters button{font:500 13px "IBM Plex Sans KR";padding:6px 12px;border:1px solid var(--hair);background:transparent;color:var(--ink);cursor:pointer}
.filters button[aria-pressed=true]{border-color:var(--ink);background:var(--ink);color:var(--paper)}
main{padding:8px 0 80px}
.card{border-top:2px solid var(--ink);margin:28px 0 0;padding-top:14px}
.card.done{opacity:.45}
.card.blocked{border-top-color:var(--sky)}
.top{display:grid;grid-template-columns:1fr auto;gap:4px 16px}
.top>div{min-width:0}
.kick{font:500 12px/1.4 "IBM Plex Mono","IBM Plex Sans KR",monospace;color:var(--ink2);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.badge{font:700 11px "IBM Plex Sans KR";padding:2px 7px;background:var(--ink);color:var(--paper)}
.badge.warn{background:var(--sky);color:var(--on-sky)}
.title{font:700 1.15rem/1.4 "IBM Plex Sans KR",sans-serif;letter-spacing:-.02em;margin:6px 0 0;text-wrap:balance}
.slot{text-align:right;font:500 12px/1.3 "IBM Plex Mono",monospace;color:var(--ink2)}
.slot b{display:block;font-size:18px;color:var(--ink)}
.slot.now{color:var(--ink)}.slot.now b{background:#7cc8ff;color:#0b0b0c;padding:2px 8px;margin-top:2px}
.checks{margin:12px 0 0;padding:10px 12px;font-size:13px;background:var(--sky-soft)}
.checks ul{margin:4px 0 0;padding-left:18px}
.checks .bad{font-weight:700}
.tabs{display:flex;margin-top:12px;border-bottom:1px solid var(--ink)}
.tabs button{font:700 13px "IBM Plex Sans KR";padding:9px 14px;border:0;border-bottom:3px solid transparent;margin-bottom:-1px;background:transparent;color:var(--ink2);cursor:pointer}
.tabs button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--sky)}
.pane{padding:12px 0 4px}
.actions{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;align-items:center}
.actions button{font:700 13px "IBM Plex Sans KR";padding:8px 12px;border:1px solid var(--ink);background:var(--ink);color:var(--paper);cursor:pointer}
.actions button.sec{background:transparent;color:var(--ink)}
.actions button:active{background:var(--sky);color:var(--on-sky);border-color:var(--sky)}
.actions label{margin-left:auto;font-weight:700;font-size:13px;display:flex;gap:6px;align-items:center;cursor:pointer}
.actions input{width:18px;height:18px;accent-color:var(--sky)}
.tags{font:12px/1.6 "IBM Plex Mono","IBM Plex Sans KR",monospace;color:var(--ink2);margin:0 0 8px}
details summary{cursor:pointer;font:500 12px "IBM Plex Mono","IBM Plex Sans KR",monospace;color:var(--muted)}
.preview{background:#fff;color:#111;padding:16px;margin-top:8px;max-height:440px;overflow:auto;border:1px solid var(--hair)}
.toast{position:fixed;left:50%;bottom:calc(20px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);background:var(--ink);color:var(--paper);padding:10px 16px;font-weight:700;display:none;border-left:6px solid var(--sky)}
.empty{padding:40px 0;color:var(--muted)}
.howto{font-size:13px;color:var(--ink2);margin:14px 0 0;padding-left:12px;border-left:3px solid var(--sky)}
</style></head><body><div class="wrap">
<header><h1>발행 대기함</h1><p class="meta">__COUNT__ · 생성 __GENERATED__ KST</p></header>
<div class="region" role="tablist" aria-label="지역">
  <button data-r="kr" aria-selected="true">국내<small>네이버 · 티스토리</small></button><button data-r="us" aria-selected="false">미국<small>Blogger · 자동</small></button><button data-r="in" aria-selected="false">인도<small>Blogger · 자동</small></button><button data-r="shop" aria-selected="false">쇼피<small>국가별 · 자동</small></button>
</div>
<p class="howto" id="howto"></p>
<div class="filters" role="group" aria-label="보기">
  <button data-f="todo" aria-pressed="true">발행 전</button><button data-f="all" aria-pressed="false">전체</button><button data-f="blocked" aria-pressed="false">검증 실패</button>
</div>
<main id="list"></main></div><div class="toast" id="toast"></div>
<script>
var ALL=__DATA__;
function store(k,v){try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v)}catch(e){return null}}
function toast(m){var t=document.getElementById('toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(function(){t.style.display='none'},1600)}
function copyRich(h){var plain=h.replace(/<[^>]+>/g,' ');if(navigator.clipboard&&window.ClipboardItem){return navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([h],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]).then(function(){toast('본문 복사됨 — 에디터에 붙여넣기')},function(){fallback(h,true)})}fallback(h,true)}
function copyImage(dataUrl){try{var b=atob(dataUrl.split(',')[1]),u=new Uint8Array(b.length);for(var i=0;i<b.length;i++)u[i]=b.charCodeAt(i);var type=dataUrl.slice(5,dataUrl.indexOf(';'));var blob=new Blob([u],{type:type});
 var go=function(bl){navigator.clipboard.write([new ClipboardItem({'image/png':bl})]).then(function(){toast('이미지 복사됨 — 에디터에 붙여넣기')},function(){toast('이미지 복사가 막혔어요 — 미리보기에서 길게 눌러 저장해 주세요')})};
 if(type==='image/png')go(blob);else{var img=new Image();img.onload=function(){var c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;c.getContext('2d').drawImage(img,0,0);c.toBlob(go,'image/png')};img.src=dataUrl}}catch(e){toast('이미지 복사가 막혔어요 — 미리보기에서 길게 눌러 저장해 주세요')}}
function copyText(s,m){if(navigator.clipboard){navigator.clipboard.writeText(s).then(function(){toast(m)},function(){fallback(s,false,m)})}else fallback(s,false,m)}
function fallback(s,rich,m){var d=document.createElement('div');d.contentEditable=true;d.style.position='fixed';d.style.left='-9999px';if(rich)d.innerHTML=s;else d.textContent=s;document.body.appendChild(d);var r=document.createRange();r.selectNodeContents(d);var sel=getSelection();sel.removeAllRanges();sel.addRange(r);document.execCommand('copy');sel.removeAllRanges();d.remove();toast(m||'복사됨')}
var region=['us','in','shop'].indexOf(store('region'))>=0?store('region'):'kr',filter='todo';
var PLAT={kr:[['naver','네이버 블로그'],['tistory','티스토리 (다음·구글)']],us:[['blogger','Google Blogger']],in:[['blogger','Google Blogger']],shop:[['blogger','Google Blogger']]};
var HOWTO={kr:'네이버는 [본문 복사] 후 에디터에 붙여넣기, 티스토리는 기본모드 붙여넣기 또는 HTML모드에 [HTML 복사]. 이미지는 버튼으로 하나씩 복사해 넣어 주세요.',
 us:'Blogger 새 글 → 연필 아이콘을 [HTML 보기]로 바꾸고 [HTML 복사] 붙여넣기 (또는 작성 보기에 [본문 복사]). 오른쪽 설정에서 라벨·검색 설명·맞춤 퍼머링크를 버튼으로 복사해 넣으면 돼요. 이미지는 Blogger에 직접 올려 주세요.',
 in:'인도 블로그는 검증을 통과한 글을 Actions 가 인도 시간 7~23시에 하루 5편까지 자동 예약해요. 여기서는 상태만 확인하면 돼요.',
 shop:'쇼피 국가별 블로그는 나라마다 하루 4편까지 그 나라 시간으로 자동 예약해요. 여기서는 상태만 확인하면 돼요.'};
// 발행 상태: 아티팩트 db(published/<slug>)에 저장 — 새로고침·재발행·다른 기기에서도 유지. db 를 못 쓰는 보기에서는 브라우저 저장소로만.
var PUB={},DB=null;
var AUTO={};['us','in','shop'].forEach(function(r){(ALL[r]||[]).forEach(function(c){if(c.auto)AUTO[c.slug]=1})});
function isPub(slug,p){if(p==='blogger'&&AUTO[slug])return true;var d=PUB[slug];if(d&&Object.prototype.hasOwnProperty.call(d,p))return !!d[p];return store('pub:'+slug+':'+p)==='1'}
var writing={};
function setPub(slug,p,v){store('pub:'+slug+':'+p,v?'1':'0');var d=Object.assign({},PUB[slug]||{});d[p]=v;d.updated=new Date().toISOString();PUB[slug]=d;render();
 if(!DB){toast('이 보기에선 이 기기에만 저장돼요');return}
 var run=function(){writing[slug]=(writing[slug]||Promise.resolve()).then(function(){return DB.collection('published').doc(slug).set(PUB[slug])}).then(function(){toast(v?'발행함으로 저장됐어요':'발행 전으로 되돌렸어요')},function(e){toast('저장 실패 — 다시 눌러 주세요'+(e&&e.code?' ('+e.code+')':''))})};run()}
function done(c){return PLAT[region].every(function(p){return !c[p[0]]&&p[0]!=='naver'||isPub(c.slug,p[0])})}
function el(t,a,h){var e=document.createElement(t);for(var k in a)e.setAttribute(k,a[k]);if(h!=null)e.innerHTML=h;return e}
function esc(s){return String(s||'').replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function render(){var L=document.getElementById('list');L.innerHTML='';var shown=0;document.getElementById('howto').textContent=HOWTO[region];
var DATA=ALL[region]||[];var first=PLAT[region][0][0];
DATA.forEach(function(c){var isDone=done(c);if(filter==='todo'&&(isDone||!c.ok))return;if(filter==='blocked'&&c.ok)return;shown++;
 var card=el('article',{class:'card'+(isDone?' done':'')+(c.ok?'':' blocked')});
 if(c.compact){var kb=c.ok?'<span class="badge">'+(c.auto?'예약됨':'검증통과')+'</span>':'<span class="badge warn">발행불가</span>';
  var tp=el('div',{class:'top'});tp.appendChild(el('div',{},'<div class="kick">'+kb+'<span>'+esc(c.blog)+(c.blog!==c.blog_label?' · '+esc(c.blog_label):'')+' · '+esc(c.category)+(c.trend?' · '+esc(c.trend):'')+'</span></div><p class="title">'+esc(c.blogger.title)+'</p>'));
  tp.appendChild(el('div',{class:'slot'},(c.auto?'Blogger 예약':'상태')+'<b>'+esc(c.slot)+'</b>'+esc(c.slot2||'')));card.appendChild(tp);
  var ck2='문체 '+c.style+'점'+(c.auto_url?' · <a href="'+esc(c.auto_url)+'" target="_blank" rel="noopener">글 주소</a>':'');
  if(c.problems.length)ck2+='<ul>'+c.problems.map(function(p){return'<li class="bad">'+esc(p)+'</li>'}).join('')+'</ul>';
  card.appendChild(el('div',{class:'checks'},ck2));L.appendChild(card);return}
 var badge=c.ok?(c.manual.length?'<span class="badge warn">사람확인 '+c.manual.length+'</span>':'<span class="badge">검증통과</span>'):'<span class="badge warn">발행불가</span>';
 var top=el('div',{class:'top'});
 top.appendChild(el('div',{},'<div class="kick">'+badge+'<span>'+esc(c.category)+(c.deadline?' · 마감 '+esc(c.deadline):'')+(c.trend?' · '+esc(c.trend):'')+'</span></div><p class="title">'+esc(c[first].title)+'</p>'));
 top.appendChild(el('div',{class:'slot'+(c.urgent?' now':'')},(c.urgent?'즉시 발행':(c.auto?'Blogger 예약':'추천 발행'))+'<b>'+esc(c.slot)+'</b>'+(c.slot2?esc(c.slot2):'')));card.appendChild(top);
 var ck='문체 '+c.style+'점'+(region==='kr'?(c.similarity!=null?' · 두 버전 유사도 '+c.similarity:' · 티스토리판 없음'):'');
 if(c.problems.length)ck+='<ul>'+c.problems.map(function(p){return'<li class="bad">'+esc(p)+'</li>'}).join('')+'</ul>';
 if(c.manual.length)ck+='<ul>'+c.manual.map(function(p){return'<li>원문 직접 확인: '+esc(p)+'</li>'}).join('')+'</ul>';
 if(c.todo&&c.todo.length)ck+='<ul>'+c.todo.map(function(p){return'<li>📍 '+esc(p)+'</li>'}).join('')+'</ul>';
 card.appendChild(el('div',{class:'checks'},ck));
 var tabs=el('div',{class:'tabs',role:'tablist'}),pane=el('div',{class:'pane'});
 PLAT[region].forEach(function(pp,i){var b=el('button',{role:'tab','aria-selected':i?'false':'true'},pp[1]);b.onclick=function(){tabs.querySelectorAll('button').forEach(function(x){x.setAttribute('aria-selected',x===b)});show(pp[0])};tabs.appendChild(b)});
 function show(p){var v=c[p]||c[first];pane.innerHTML='';var act=el('div',{class:'actions'});
  var b1=el('button',{},'제목 복사');b1.onclick=function(){copyText(v.title,'제목 복사됨')};act.appendChild(b1);
  if(p==='blogger'){var bh=el('button',{},'HTML 복사');bh.onclick=function(){copyText(v.html,'HTML 복사됨 — HTML 보기에 붙여넣기')};act.appendChild(bh)}
  var b2=el('button',{class:p==='blogger'?'sec':''},p==='naver'?'본문 복사':(p==='blogger'?'본문 복사 (작성 보기)':'본문 복사 (기본모드)'));b2.onclick=function(){copyRich(v.html)};act.appendChild(b2);
  if(p==='tistory'){var b3=el('button',{class:'sec'},'HTML 복사 (HTML모드)');b3.onclick=function(){copyText(v.html,'HTML 복사됨')};act.appendChild(b3)}
  if(p==='blogger'&&v.description){var bd=el('button',{class:'sec'},'검색 설명');bd.onclick=function(){copyText(v.description,'검색 설명 복사됨')};act.appendChild(bd)}
  if(p==='blogger'&&v.permalink){var bp=el('button',{class:'sec'},'퍼머링크');bp.onclick=function(){copyText(v.permalink,'맞춤 퍼머링크 복사됨')};act.appendChild(bp)}
  (v.images||[]).forEach(function(im,i){var bi=el('button',{class:'sec'},'이미지 '+(i+1));bi.onclick=function(){copyImage(im.data)};act.appendChild(bi)});
  if(v.tags&&v.tags.length){var b4=el('button',{class:'sec'},p==='blogger'?'라벨':'태그');b4.onclick=function(){copyText(v.tags.join(p==='naver'?' ':','),(p==='blogger'?'라벨':'태그')+' 복사됨')};act.appendChild(b4)}
  var lab=el('label',{});var cb=el('input',{type:'checkbox'});cb.checked=isPub(c.slug,p);cb.onchange=function(){setPub(c.slug,p,cb.checked)};lab.appendChild(cb);lab.appendChild(document.createTextNode('발행함'));act.appendChild(lab);
  pane.appendChild(act);if(!c[p])pane.appendChild(el('p',{class:'tags'},'⚠ 티스토리 전용판이 없어 네이버판을 보여 줍니다. 그대로 올리면 유사문서가 될 수 있습니다.'));
  if(v.tags&&v.tags.length)pane.appendChild(el('p',{class:'tags'},v.tags.map(function(t){return(p==='blogger'?'':'#')+esc(t)}).join(p==='blogger'?' · ':' ')));
  if(p==='blogger'&&v.description)pane.appendChild(el('p',{class:'tags'},'검색 설명: '+esc(v.description)+(v.permalink?'<br>퍼머링크: '+esc(v.permalink):'')));
  var d=el('details',{});d.appendChild(el('summary',{},'미리보기'));d.appendChild(el('div',{class:'preview'},'<h2 style="margin-top:0">'+esc(v.title)+'</h2>'+(v.preview||v.html).replace(/src="#img(\d+)"/g,function(_,i){return 'src="'+((v.images||[])[+i]||{}).data+'"'})));pane.appendChild(d)}
 if(!c.ok){pane.appendChild(el('p',{class:'tags'},'검증을 통과하지 못한 글은 복사 버튼을 숨깁니다. 위 문제를 먼저 고치세요.'))}else show(first);
 card.appendChild(tabs);card.appendChild(pane);L.appendChild(card)});
 if(!shown)L.appendChild(el('p',{class:'empty'},filter==='todo'?'지금 발행할 글이 없습니다.':'해당하는 글이 없습니다.'))}
document.querySelectorAll('.region button').forEach(function(b){b.setAttribute('aria-selected',b.dataset.r===region);b.onclick=function(){region=b.dataset.r;store('region',region);document.querySelectorAll('.region button').forEach(function(x){x.setAttribute('aria-selected',x===b)});render()}});
document.querySelectorAll('.filters button').forEach(function(b){b.onclick=function(){filter=b.dataset.f;document.querySelectorAll('.filters button').forEach(function(x){x.setAttribute('aria-pressed',x===b)});render()}});
render();
if(window.claude&&window.claude.use){window.claude.use('db').then(function(db){if(!db)return;DB=db;
 db.collection('published').onSnapshot(function(qs){qs.docs.forEach(function(d){if(d.exists)PUB[d.id]=d.data()||{}});render()},function(){DB=null})},function(){})}
</script></body></html>"""

if __name__ == "__main__":
    main()
