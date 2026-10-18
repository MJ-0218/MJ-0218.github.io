#!/usr/bin/env python3
"""글에 넣을 사진·삽화 가져오기 — 라이선스가 분명한 것만.

  photo : Pexels 무료 사진 검색 (PEXELS_API_KEY 필요). Pexels 라이선스: 상업적 이용 가능, 출처 표시 의무 없음(그래도 남김)
  ai    : OpenAI 이미지 생성 (OPENAI_API_KEY 필요). 분위기용 삽화 전용 — 글자·숫자·로고·실존 인물 금지

결과 이미지는 assets/photos/ 에 저장되고, front matter `images:` 에 붙여 넣을 YAML 이 출력된다.
verify_claims 는 /assets/cards/ 가 아닌 이미지가 images(license·credit) 에 없으면 FAIL 로 막는다.

사용:
  python3 automation/scripts/get_image.py photo <slug> "autumn leaves mountain korea"
  python3 automation/scripts/get_image.py ai <slug> "가을 단풍이 든 산길을 걷는 사람들의 뒷모습, 따뜻한 수채화 느낌"
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "photos"
UA = "semter-blog/1.0 (+https://mj-0218.github.io)"


def cfg():
    c = yaml.safe_load((ROOT / "automation" / "config.yml").read_text(encoding="utf-8")) or {}
    return c.get("images", {})


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def next_name(slug, ext):
    OUT.mkdir(parents=True, exist_ok=True)
    i = 1
    while (OUT / f"{slug}-{i}.{ext}").exists():
        i += 1
    return OUT / f"{slug}-{i}.{ext}"


def photo(slug, query):
    # 키는 환경 변수, 또는 클라우드 환경의 Network secrets(프록시가 요청에 자동으로 붙임) 둘 다 지원
    key = os.environ.get("PEXELS_API_KEY")
    q = urllib.parse.urlencode({"query": query, "per_page": 5, "orientation": "landscape", "locale": "ko-KR"})
    try:
        res = json.loads(http(f"https://api.pexels.com/v1/search?{q}", headers={"Authorization": key} if key else {}))
    except urllib.error.HTTPError as e:
        sys.exit(f"Pexels 오류 {e.code} — PEXELS_API_KEY(환경 변수 또는 Network secrets)를 확인해 주세요.")
    if not res.get("photos"):
        sys.exit("검색 결과가 없어요. 다른 검색어로 시도해 주세요.")
    p = res["photos"][0]
    out = next_name(slug, "jpg")
    out.write_bytes(http(p["src"]["large"]))
    entry = {"src": f"/assets/photos/{out.name}", "license": "Pexels License (상업적 이용 가능)",
             "credit": f"Photo by {p['photographer']} on Pexels", "origin": p["url"], "alt": p.get("alt") or query}
    print(yaml.safe_dump([entry], allow_unicode=True, sort_keys=False))


def ai(slug, prompt):
    key = os.environ.get("OPENAI_API_KEY")  # 없으면 Network secrets 가 인증 헤더를 붙여 준다고 보고 그대로 요청
    c = cfg()
    guard = ("Editorial blog illustration. No text, no letters, no numbers, no logos, no watermarks, "
             "no real or identifiable people, no government emblems. ")
    body = {"model": c.get("openai_model", "gpt-image-2"), "prompt": guard + prompt,
            "size": c.get("openai_size", "1536x1024"), "quality": c.get("openai_quality", "medium"), "n": 1}
    try:
        res = json.loads(http("https://api.openai.com/v1/images/generations", data=json.dumps(body).encode(),
                              headers={**({"Authorization": f"Bearer {key}"} if key else {}), "Content-Type": "application/json"}))
    except urllib.error.HTTPError as e:
        sys.exit(f"OpenAI 오류 {e.code}: {e.read().decode()[:400]} — config.yml images.openai_model 을 확인해 주세요.")
    item = res["data"][0]
    raw = base64.b64decode(item["b64_json"]) if item.get("b64_json") else http(item["url"])
    out = next_name(slug, "png")
    out.write_bytes(raw)
    entry = {"src": f"/assets/photos/{out.name}", "license": f"AI 생성 이미지 ({body['model']})",
             "credit": "AI로 만든 이미지 (셈터)", "alt": re.sub(r"\s+", " ", prompt)[:80]}
    print(yaml.safe_dump([entry], allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ("photo", "ai"):
        sys.exit(__doc__)
    {"photo": photo, "ai": ai}[sys.argv[1]](sys.argv[2], " ".join(sys.argv[3:]))
