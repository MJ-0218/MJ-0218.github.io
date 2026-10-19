#!/usr/bin/env python3
"""정보 카드 이미지 생성기 — 글 front matter 의 `cards:` 를 PNG 로 그린다.

저작권 걱정 없는 '직접 만든 이미지'를 글 중간에 넣기 위한 도구다.
카드 안의 숫자도 사실 주장이므로 verify_claims 가 claims 와 대조한다.

front matter 예시
  cards:
    summary:                      # 본문에 ![설명](/assets/cards/<slug>-summary.png) 로 넣는다
      type: summary               # summary | table | steps
      kicker: "부동산 · 면적 환산"
      title: "84㎡는 몇 평일까요?"
      big: "약 25.4평"
      lines: ["34평형은 공급면적 기준 이름이에요", "비교는 전용면적끼리 하세요"]
    areas:
      type: table
      title: "자주 찾는 면적 환산"
      head: ["전용면적", "평 환산"]
      rows: [["59㎡", "17.8평"], ["84㎡", "25.4평"]]
    howto:
      type: steps
      title: "신청은 이렇게 해요"
      steps: ["홈택스 접속", "본인 인증", "신청서 제출"]

사용: python3 automation/scripts/make_cards.py _drafts/<slug>.md [automation/variants/<slug>.tistory.md ...]
출력: assets/cards/<slug>-<id>.png  (필요: pip install playwright pyyaml)
"""
import html
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "cards"
SITE_NAME = "셈터"
SITE_NAME_EN = "Semter"  # 미국 Blogger 카드 꼬리표


def front_matter(p):
    t = Path(p).read_text(encoding="utf-8")
    if not t.startswith("---"):
        return {}
    return yaml.safe_load(t.split("---", 2)[1]) or {}


def slug_of(p):
    s = Path(p).stem
    s = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", s)
    return re.sub(r"\.(tistory|naver)$", "", s)


def e(s):
    return html.escape(str(s))


def body_for(card):
    t = card.get("type", "summary")
    kicker = f'<p class="kicker">{e(card["kicker"])}</p>' if card.get("kicker") else ""
    title = f'<h1>{e(card.get("title", ""))}</h1>'
    if t == "summary":
        big = f'<p class="big">{e(card["big"])}</p>' if card.get("big") else ""
        lines = "".join(f"<li>{e(x)}</li>" for x in card.get("lines", []))
        return f'{kicker}{title}{big}<ul class="lines">{lines}</ul>'
    if t == "table":
        head = "".join(f"<th>{e(h)}</th>" for h in card.get("head", []))
        rows = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in card.get("rows", []))
        note = f'<p class="note">{e(card["note"])}</p>' if card.get("note") else ""
        return f'{kicker}{title}<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>{note}'
    if t == "steps":
        steps = "".join(f'<li><span class="n">{i}</span><span>{e(s)}</span></li>' for i, s in enumerate(card.get("steps", []), 1))
        return f'{kicker}{title}<ol class="steps">{steps}</ol>'
    raise ValueError(f"알 수 없는 카드 type: {t}")


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
/* 안내 표지판 — 흰 바탕, 먹색 글자, 하늘색은 면(面)으로만 */
:root{--paper:#fff;--ink:#0b0b0c;--ink2:rgba(11,11,12,.66);--hair:rgba(11,11,12,.14);--sky:#7cc8ff}
*{box-sizing:border-box;margin:0}
body{width:540px;background:var(--paper);font-family:"IBM Plex Sans KR","WenQuanYi Zen Hei",sans-serif;color:var(--ink);word-break:keep-all}
.card{padding:34px 34px 26px;border-top:10px solid var(--sky)}
.kicker{display:flex;align-items:center;gap:8px;font:500 13px/1.4 "IBM Plex Sans KR",sans-serif;color:var(--ink2);letter-spacing:-.01em;margin-bottom:14px}
.kicker::before{content:"";width:9px;height:9px;background:var(--ink)}
h1{font:700 27px/1.3 "IBM Plex Sans KR",sans-serif;letter-spacing:-.035em;margin-bottom:18px}
.big{display:inline-block;font:700 50px/1.05 "IBM Plex Sans KR",sans-serif;letter-spacing:-.045em;margin:2px 0 22px;padding:6px 12px 8px;background:var(--sky)}
.lines{list-style:none;padding:0;border-top:1px solid var(--ink)}
.lines li{padding:12px 0;border-bottom:1px solid var(--hair);font-size:16px;line-height:1.55}
table{width:100%;border-collapse:collapse;font-size:15.5px}
th{text-align:left;font:500 11px "IBM Plex Mono","IBM Plex Sans KR",monospace;letter-spacing:.08em;color:var(--ink2);border-bottom:1px solid var(--ink);padding:8px 8px 8px 0}
td{padding:11px 8px 11px 0;border-bottom:1px solid var(--hair)}
td:not(:first-child){font-weight:700;font-family:"IBM Plex Sans KR",sans-serif}
tbody tr:first-child td{border-top:0}
.note{font-size:12.5px;color:var(--ink2);margin-top:14px;padding-left:10px;border-left:3px solid var(--sky)}
.steps{list-style:none;padding:0;border-top:1px solid var(--ink)}
.steps li{display:flex;gap:14px;align-items:center;font-size:16.5px;line-height:1.45;padding:12px 0;border-bottom:1px solid var(--hair)}
.n{flex:none;width:30px;height:30px;display:grid;place-items:center;background:var(--sky);color:var(--ink);font:600 14px "IBM Plex Mono","IBM Plex Sans KR",monospace}
.foot{display:flex;justify-content:space-between;align-items:center;padding:0 34px 26px;font:500 12px "IBM Plex Sans KR",sans-serif;color:var(--ink2)}
.mark{display:inline-flex;align-items:center;gap:7px;font:700 13px "IBM Plex Sans KR",sans-serif;color:var(--ink);letter-spacing:-.02em}
.seal{display:inline-block;width:10px;height:10px;background:var(--sky)}
</style></head><body><div class="card">__BODY__</div>
<div class="foot"><span class="mark"><span class="seal"></span>__SITE__</span><span>__ASOF__</span></div></body></html>"""


def render(files):
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    exe = os.environ.get("CHROMIUM_PATH") or next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)
    made = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=str(exe)) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 540, "height": 400}, device_scale_factor=2)
        for f in files:
            fm, slug = front_matter(f), slug_of(f)
            en = fm.get("lang") == "en"
            asof = (f'Last checked {fm["info_as_of"]}' if en else f'정보 기준일 {fm["info_as_of"]}') if fm.get("info_as_of") else ""
            site = SITE_NAME_EN if en else SITE_NAME
            for cid, card in (fm.get("cards") or {}).items():
                page = PAGE.replace("__BODY__", body_for(card)).replace("__SITE__", site).replace("__ASOF__", e(asof))
                pg.set_content(page, wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                out = OUT / f"{slug}-{cid}.png"
                pg.screenshot(path=str(out), full_page=True)
                made.append(out.relative_to(ROOT))
        b.close()
    return made


def card_text(fm):
    """verify_claims 용: 카드에 들어간 모든 글자"""
    out = []
    for card in (fm.get("cards") or {}).values():
        for k in ("title", "big", "note"):
            if card.get(k):
                out.append(str(card[k]))
        out += [str(x) for x in card.get("lines", []) + card.get("steps", [])]
        for r in card.get("rows", []):
            out.append(" ".join(str(c) for c in r))
    return " ·\n".join(out)  # 줄 사이 구분점: 앞 줄 끝 숫자와 다음 줄 첫 글자가 한 토큰("3190 세")으로 붙지 않게


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for m in render(sys.argv[1:]):
        print(m)
