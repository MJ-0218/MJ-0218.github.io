#!/usr/bin/env python3
"""플랫폼별 버전끼리 문장이 너무 겹치지 않는지 검사한다.

네이버는 비슷한 문서를 '유사문서'로 묶어 한쪽만 노출하는 것으로 알려져 있어,
네이버판과 티스토리판은 같은 사실을 다른 구성·문장으로 써야 한다.
글자 4-gram 자카드 유사도 + 같은 문장(20자 이상) 개수로 판단한다.

사용: python3 automation/scripts/similarity_check.py A.md B.md [--max 0.35]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from style_check import split_front_matter, plain  # noqa: E402


def body_text(p):
    _, body = split_front_matter(Path(p).read_text(encoding="utf-8"))
    t = plain(body)
    t = re.sub(r"^\s*\|.*$", "", t, flags=re.M)  # 표는 같은 사실이라 겹쳐도 됨
    return re.sub(r"\s+", " ", t)


def grams(t, n=4):
    t = re.sub(r"\s", "", t)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def sentences(t):
    return {s.strip() for s in re.split(r"(?<=[.!?다요])\s", t) if len(s.strip()) >= 20}


def compare(a, b):
    ta, tb = body_text(a), body_text(b)
    ga, gb = grams(ta), grams(tb)
    jac = len(ga & gb) / max(1, len(ga | gb))
    same = sorted(sentences(ta) & sentences(tb))
    return jac, same


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--max", type=float, default=0.35)
    x = ap.parse_args()
    jac, same = compare(x.a, x.b)
    print(f"4-gram 유사도 {jac:.2f} (기준 {x.max:.2f} 이하) · 똑같은 문장 {len(same)}개")
    for s in same[:10]:
        print("  =", s[:80])
    sys.exit(1 if jac > x.max or len(same) > 2 else 0)


if __name__ == "__main__":
    main()
