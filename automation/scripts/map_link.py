#!/usr/bin/env python3
"""가게 위치 지도 링크 — 클릭하면 지도 앱(웹)에서 바로 검색 결과가 열린다.

  python3 automation/scripts/map_link.py "강서구 방화동쭈꾸미마을1997"
  → 네이버 지도 / 카카오맵 / 구글 지도 검색 주소

글에는 플랫폼에 맞는 링크를 넣는다: 네이버판=네이버 지도, 티스토리판=카카오맵, Blogger=구글 지도.
지도 화면 캡처(타일 이미지)는 저작권 때문에 넣지 않고 링크만 쓴다.
검색어: 가게 이름이 기사에 있으면 "지역 + 가게 이름", 없으면 "지역 + 대표 메뉴".
"""
import sys
from urllib.parse import quote


def links(q):
    return {
        "naver": f"https://map.naver.com/p/search/{quote(q)}",
        "kakao": f"https://map.kakao.com/?q={quote(q)}",
        "google": f"https://www.google.com/maps/search/?api=1&query={quote(q)}",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for k, v in links(" ".join(sys.argv[1:])).items():
        print(f"{k:7} {v}")
