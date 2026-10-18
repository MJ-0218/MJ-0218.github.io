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
<link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Mono:wght@600&family=IBM+Plex+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{--paper:#f3eee2;--ink:#16130f;--ink2:#4a443b;--seal:#cf3a1f;--field:#fffdf7;--grid:rgba(22,19,15,.06)}
*{box-sizing:border-box;margin:0}
body{width:540px;background:var(--paper);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:18px 18px;font-family:"IBM Plex Sans KR","WenQuanYi Zen Hei",sans-serif;color:var(--ink);word-break:keep-all}
.card{margin:22px;background:var(--field);border:2px solid var(--ink);box-shadow:5px 5px 0 var(--ink);padding:26px 26px 22px;position:relative}
.kicker{font:600 12px/1.4 "IBM Plex Mono",monospace;color:var(--seal);letter-spacing:.06em;margin-bottom:8px}
h1{font:700 26px/1.3 "Gowun Batang",serif;letter-spacing:-.01em;margin-bottom:14px}
.big{font:700 44px/1.1 "IBM Plex Sans KR",sans-serif;color:var(--seal);margin:4px 0 16px;letter-spacing:-.02em}
.lines{list-style:none;padding:0;border-top:2px solid var(--ink)}
.lines li{padding:10px 0;border-bottom:1px solid var(--ink);font-size:17px;line-height:1.5}
table{width:100%;border-collapse:collapse;font-size:16px}
th{text-align:left;font:600 12px "IBM Plex Mono",monospace;letter-spacing:.05em;color:var(--ink2);border-bottom:2px solid var(--ink);padding:8px 6px}
td{padding:9px 6px;border-bottom:1px solid var(--ink)}
td:not(:first-child){font-weight:700}
.note{font-size:13px;color:var(--ink2);margin-top:10px}
.steps{list-style:none;padding:0;display:grid;gap:10px}
.steps li{display:flex;gap:12px;align-items:center;font-size:17px;line-height:1.45}
.n{flex:none;width:30px;height:30px;display:grid;place-items:center;background:var(--ink);color:var(--paper);font:700 15px "IBM Plex Mono",monospace}
.foot{display:flex;justify-content:space-between;align-items:center;margin:0 22px 18px;font:600 11px "IBM Plex Mono",monospace;color:var(--ink2)}
.seal{display:inline-grid;place-items:center;width:26px;height:26px;background:var(--seal);color:#fff;font:700 14px "Gowun Batang",serif;transform:rotate(-4deg);margin-right:6px}
</style></head><body><div class="card">__BODY__</div>
<div class="foot"><span><span class="seal">셈</span>__SITE__</span><span>__ASOF__</span></div></body></html>"""


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
            asof = f'정보 기준일 {fm["info_as_of"]}' if fm.get("info_as_of") else ""
            for cid, card in (fm.get("cards") or {}).items():
                page = PAGE.replace("__BODY__", body_for(card)).replace("__SITE__", SITE_NAME).replace("__ASOF__", e(asof))
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
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for m in render(sys.argv[1:]):
        print(m)
