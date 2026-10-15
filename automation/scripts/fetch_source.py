#!/usr/bin/env python3
"""출처 원문 읽기 — claims 의 quote 를 '원문 그대로' 복사하기 위한 도구.

사용: python3 automation/scripts/fetch_source.py <URL> [찾을말 ...]
  찾을말을 주면 그 말이 나오는 부분 앞뒤 120자를 보여 준다. 없으면 본문 앞 3000자.
PDF 는 pdftotext 가 있으면 텍스트로 바꿔 읽는다.
네트워크가 막혀 있으면 실패 메시지를 내고 exit 2 — 그때는 claims 에 manual 사유를 적는다.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_claims import page_text  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url, words = sys.argv[1], sys.argv[2:]
    try:
        text = re.sub(r"[ \t\r\f\v]+", " ", page_text(url))
        text = re.sub(r"\n\s*\n+", "\n", text)
    except Exception as e:
        print(f"원문 열기 실패: {e}", file=sys.stderr)
        sys.exit(2)
    if not words:
        print(text[:3000])
        return
    for w in words:
        hits = [m.start() for m in re.finditer(re.escape(w), text)]
        print(f"\n=== '{w}' {len(hits)}곳 ===")
        for h in hits[:8]:
            print("…" + text[max(0, h - 120): h + 120].replace("\n", " ") + "…\n")


if __name__ == "__main__":
    main()
