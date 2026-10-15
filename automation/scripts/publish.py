#!/usr/bin/env python3
"""검수 끝난 초안을 셈터(Jekyll)에 발행: _drafts/slug.md → _posts/YYYY-MM-DD-slug.md

사용: python3 automation/scripts/publish.py _drafts/slug.md [slug2.md ...]
- 발행 전에 style_check 를 다시 돌려 FAIL 이 있으면 멈춘다.
- front matter 의 date 를 지금 시각(KST)으로 넣는다.
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from style_check import check  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    now = datetime.now(KST)
    for arg in sys.argv[1:]:
        src = Path(arg)
        r = check(src)
        if r["fail"]:
            print(f"✗ {src}: FAIL {len(r['fail'])}건 — 먼저 고치세요")
            for f in r["fail"]:
                print("   -", f)
            sys.exit(1)
        text = src.read_text(encoding="utf-8")
        stamp = now.strftime("%Y-%m-%d %H:%M:%S +0900")
        if re.search(r"^date:", text, flags=re.M):
            text = re.sub(r"^date:.*$", f"date: {stamp}", text, count=1, flags=re.M)
        else:
            text = text.replace("---\n", f"---\ndate: {stamp}\n", 1)
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", src.stem)
        dest = ROOT / "_posts" / f"{now:%Y-%m-%d}-{slug}.md"
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        src.unlink()
        print(f"✓ {src} → {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
