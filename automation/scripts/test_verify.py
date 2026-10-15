"""verify_claims 단위 테스트: python3 automation/scripts/test_verify.py"""
import sys, tempfile, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import verify_claims as V

ROOT = V.ROOT
draft = ROOT / "_drafts" / "zz-test-verify.md"
claims = ROOT / "automation" / "claims" / "zz-test-verify.yml"
SRC = "https://www.example.go.kr/notice"
try:
    draft.write_text(textwrap.dedent("""\
        ---
        title: t
        category: 정부혜택
        deadline: 2026-10-31
        ---
        신청은 2026년 10월 20일부터 받고, 1인당 30만 원을 줍니다. 대상은 만 19세 이상입니다.
        """), encoding="utf-8")
    claims.write_text(textwrap.dedent(f"""\
        - claim: 신청 시작일
          value: 2026년 10월 20일
          quote: "신청기간 : 2026. 10. 20.(월) ~"
          value_note: 원문 날짜 표기 다름
          source: {SRC}
        - claim: 지원 금액
          value: 30만 원
          quote: "1인당 30만원"
          source: {SRC}
        """), encoding="utf-8")
    from datetime import date
    # 1) 오프라인: '만 19세' 는 claims 에 없으므로 FAIL
    r = V.verify(draft, today=date(2026, 10, 15))
    assert any("19세" in f for f in r["fail"]), r
    # 2) 원문 대조: 인용문이 있으면 통과, 없으면 FAIL
    claims.write_text(claims.read_text(encoding="utf-8") + f"""- claim: 나이
  value: 만 19세
  quote: "만 19세 이상"
  source: {SRC}
""", encoding="utf-8")
    V.page_text.__defaults__[0][SRC] = "<p>신청기간 : 2026. 10. 20.(월) ~ 11. 7.</p><p>1인당 30만원 지급, 만19세 이상</p>"
    r = V.verify(draft, fetch=True, today=date(2026, 10, 15))
    assert not r["fail"], r
    V.page_text.__defaults__[0][SRC] = "<p>1인당 20만원</p>"
    r = V.verify(draft, fetch=True, today=date(2026, 10, 15))
    assert any("원문에 없음" in f for f in r["fail"]), r
    # 3) 마감일 지난 글은 FAIL
    r = V.verify(draft, today=date(2026, 11, 1))
    assert any("마감일" in f for f in r["fail"]), r
    # 4) 정부혜택 글에 비공식 출처 → FAIL
    claims.write_text(claims.read_text(encoding="utf-8").replace("www.example.go.kr", "blog.example.com"), encoding="utf-8")
    r = V.verify(draft, today=date(2026, 10, 15))
    assert any("공식 출처" in f for f in r["fail"]), r
    print("verify_claims: 모든 테스트 통과")
finally:
    draft.unlink(missing_ok=True); claims.unlink(missing_ok=True)
