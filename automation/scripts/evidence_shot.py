#!/usr/bin/env python3
"""근거 캡처 — 공식 공고·정책 페이지를 열어, claims 의 원문 인용 부분을 형광펜으로 칠해 캡처한다.

독자에게는 '공식 문서에 정말 이렇게 적혀 있다'는 증거가 되고, 글에는 저작권 걱정 없는 이미지가 된다.
- 캡처 대상: claims 에서 `capture: true` 로 표시한 항목만
- 허용 도메인: 국가·지자체 누리집(.go.kr) 등 공공저작물 (저작권법 제24조의2·공공누리) — 뉴스·블로그는 캡처하지 않는다
- 출력: assets/cards/<slug>-evidence-<번호>.png + 캡션용 정보(stdout JSON)

사용: python3 automation/scripts/evidence_shot.py <slug>
본문에는  ![국세청 공지 원문 캡처](/assets/cards/<slug>-evidence-1.png)  처럼 넣고,
바로 아래 줄에 "출처: 기관명 누리집, 캡처일" 캡션을 적는다.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
# 캡처를 허용하는 공공 누리집. 공공기관(.or.kr 등)은 공공누리 표시를 확인한 곳만 추가한다.
CAPTURE_OK = re.compile(r"(\.go\.kr|applyhome\.co\.kr)$")

JS_MARK = r"""
(quote) => {
  const norm = s => s.replace(/[\s,·ㆍ\-–—~∼()\[\]"'“”‘’.:;\/]/g, '').toLowerCase();
  const q = norm(quote);
  // 1) 인용문을 통째로 담은 가장 작은 요소 찾기
  let best = null;
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT','STYLE','NOSCRIPT'].includes(el.tagName)) continue;
    const t = norm(el.innerText || '');
    if (t.includes(q) && (!best || (el.innerText || '').length < (best.innerText || '').length)) best = el;
  }
  if (!best) return null;
  // 2) 그 안의 텍스트 노드에서 정확히 일치하면 그 부분만 형광펜, 아니면 요소 전체에 형광펜
  const walker = document.createTreeWalker(best, NodeFilter.SHOW_TEXT);
  let hit = false;
  while (walker.nextNode()) {
    const n = walker.currentNode;
    const i = n.data.indexOf(quote);
    if (i >= 0) {
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + quote.length);
      const m = document.createElement('mark');
      m.style.cssText = 'background:linear-gradient(transparent 35%, #ffe14d 35%);color:inherit;padding:0 2px;';
      r.surroundContents(m); hit = true; break;
    }
  }
  if (!hit) best.style.cssText += ';background:#fff3a3 !important;outline:3px solid #ffd400;';
  // 3) 캡처 영역: 너무 작으면 부모로 넓힘 (문맥이 보이도록)
  let box = best;
  while (box.parentElement && box.getBoundingClientRect().height < 120 && box.parentElement !== document.body) box = box.parentElement;
  box.setAttribute('data-semter-box', '1');
  box.style.cssText += ';padding:14px !important;background-color:#fff;max-height:900px;overflow:hidden;';
  box.scrollIntoView({block: 'center'});
  return {exact: hit};
}
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    slug = sys.argv[1]
    claims = yaml.safe_load((ROOT / "automation" / "claims" / f"{slug}.yml").read_text(encoding="utf-8")) or []
    targets = [c for c in claims if c.get("capture") and c.get("source") and c.get("quote")]
    if not targets:
        print("[]")
        return
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("CHROMIUM_PATH") or next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)
    out_dir = ROOT / "assets" / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    results, n = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=str(exe)) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1000, "height": 1200}, device_scale_factor=2, locale="ko-KR")
        for c in targets:
            host = urlparse(c["source"]).hostname or ""
            if not CAPTURE_OK.search(host):
                results.append({"claim": c.get("claim"), "skipped": f"캡처 허용 도메인 아님: {host}"})
                continue
            try:
                pg.goto(c["source"], wait_until="networkidle", timeout=30000)
                found = None
                for fr in pg.frames:  # 본문이 iframe 안에 있는 누리집(국가법령정보센터 등)도 찾는다
                    try:
                        box = fr.evaluate(JS_MARK, c["quote"])
                    except Exception:
                        continue
                    if box:
                        found = (fr, box)
                        break
            except Exception as e:
                results.append({"claim": c.get("claim"), "skipped": f"열기 실패: {e}"[:200]})
                continue
            if not found:
                results.append({"claim": c.get("claim"), "skipped": "페이지에서 인용문을 찾지 못함"})
                continue
            fr, box = found
            n += 1
            out = out_dir / f"{slug}-evidence-{n}.png"
            fr.locator('[data-semter-box="1"]').first.screenshot(path=str(out))
            results.append({"claim": c.get("claim"), "image": f"/assets/cards/{out.name}", "source": c["source"],
                            "caption": f"출처: {host} 원문 캡처 ({datetime.now(KST):%Y-%m-%d}), 형광펜 표시는 셈터",
                            "exact_highlight": box["exact"]})
        b.close()
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
