#!/usr/bin/env python3
"""글 이미지 받기 — 원고의 image_requests 를 라이선스가 분명한 이미지로 채운다 (GitHub Actions 에서 실행).

작성 세션은 인터넷이 막혀 있어서, 원고에 '무슨 이미지가 필요한지'만 적고 본문 자리에 표시를 남긴다.
Actions 가 이 스크립트로 이미지를 받아 assets/photos/ 에 줄여 저장하고, 표시 자리에 이미지와 출처 캡션을 넣는다.

원고 front matter
  image_requests:
    - id: track                       # 본문의 <!-- img:track --> 자리에 들어간다
      source: jtwc                    # url | jtwc | wikimedia | openverse
      storm: CHAMPI                   # jtwc: 공식 RSS 에서 이름으로 경로도를 찾는다 (캡션에 받은 시각)
      alt: "태풍 참피 예상 경로 (JTWC)"
      note: "참고 이미지"              # 선택 — 캡션 앞에 붙는다 (방송 맛집 글의 일반 음식 사진 등)
    - id: fish
      source: wikimedia               # 위키미디어 공용 검색
      query: "Konosirus punctatus"
      alt: "전어"

받을 수 있는 이미지 (상업적 이용 가능만)
  - wikimedia / openverse: 퍼블릭 도메인, CC0, CC BY, CC BY-SA (NC·ND 는 받지 않는다)
  - url: 아래 OFFICIAL 에 있는 공공기관 도메인만 (라이선스가 확인된 곳)
  - jtwc: 미 해군 합동태풍경보센터 경로도 (미국 연방 저작물 — 퍼블릭 도메인)
결과는 front matter images:(src·license·credit·source_url)에 남는다 → verify_claims 가 라이선스 없는 이미지를 막는다.

  python3 automation/scripts/image_fetch.py [원고 …]     # 인자 없으면 모든 원고
"""
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "photos"
UA = "semter-blog-images/1.0 (https://mj-0218.github.io; image licensing check)"
DRAFT_DIRS = ["_drafts", "automation/variants", "automation/global/drafts"] + \
    [str(p.relative_to(ROOT)) for p in (ROOT / "automation" / "blogs").glob("*/drafts")]

# 공공기관 원본 — 라이선스를 확인한 도메인만
OFFICIAL = {
    "metoc.navy.mil": ("Public domain (U.S. Navy JTWC)", "Joint Typhoon Warning Center (U.S. Navy)"),
    "nhc.noaa.gov": ("Public domain (NOAA)", "NOAA National Hurricane Center"),
    "noaa.gov": ("Public domain (NOAA)", "NOAA"),
    "nasa.gov": ("Public domain (NASA)", "NASA"),
    "cdc.gov": ("Public domain (CDC)", "U.S. CDC"),
    "cwa.gov.tw": ("政府資料開放授權條款", "交通部中央氣象署"),
}
OK_LICENSE = re.compile(r"^(cc0|pdm|public domain|cc[- ]by(-sa)?([- ][\d.]+)?)$", re.I)
CAPTION = {
    "ko": "사진", "en": "Photo", "vi": "Ảnh", "id": "Foto", "th": "ภาพ", "zh-Hant": "圖片", "hi": "फ़ोटो",
}


def get(url, binary=False, text=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read()
    return data if binary else (data.decode("utf-8", "replace") if text else json.loads(data))


def strip_html(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def from_wikimedia(query):
    q = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 15,
         "gsrsearch": f"filetype:bitmap {query}", "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
         "iiurlwidth": 1400}
    res = get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(q))
    pages = sorted((res.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
        if not OK_LICENSE.match(lic.replace("Public Domain", "public domain")) or ii.get("width", 0) < 600:
            continue
        if ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        credit = strip_html((meta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons"
        return {"download": ii.get("thumburl") or ii["url"], "license": lic, "credit": credit[:120],
                "source_url": ii.get("descriptionurl", ""), "site": "Wikimedia Commons"}
    return None


def from_openverse(query):
    q = {"q": query, "license": "by,by-sa,cc0,pdm", "page_size": 20, "mature": "false"}
    res = get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(q))
    for r in res.get("results", []):
        if (r.get("width") or 0) < 600 or not r.get("url"):
            continue
        lic = ("CC " + r["license"].upper() + " " + (r.get("license_version") or "")).strip() \
            if r["license"] not in ("cc0", "pdm") else r["license"].upper()
        return {"download": r["url"], "license": lic, "credit": (r.get("creator") or r.get("source") or "Openverse")[:120],
                "source_url": r.get("foreign_landing_url") or r.get("url"), "site": "Openverse"}
    return None


def from_jtwc(storm):
    """JTWC 공식 RSS 에서 태풍 이름으로 경로도(wpNNYY.gif)를 찾는다 — 번호를 짐작하지 않는다."""
    rss = get("https://www.metoc.navy.mil/jtwc/rss/jtwc.rss", text=True)
    for item in re.findall(r"<item>(.*?)</item>", rss, re.S):
        if re.search(rf"\b{re.escape(storm)}\b", html.unescape(item), re.I):
            m = re.search(r"https?://[^\s\"'<>]*/products/(wp\d{4})\.gif", html.unescape(item))
            if m:
                info = from_url(m.group(0))
                when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                info["credit"] = f"{info['credit']}, {when}"
                return info
    return None


def from_url(url):
    host = urllib.parse.urlparse(url).hostname or ""
    for dom, (lic, credit) in OFFICIAL.items():
        if host == dom or host.endswith("." + dom):
            return {"download": url, "license": lic, "credit": credit, "source_url": url, "site": credit}
    raise ValueError(f"허용되지 않은 도메인: {host} — OFFICIAL 에 라이선스를 확인하고 추가")


def save_image(raw, dest_base):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    keep_png = im.format in ("PNG", "GIF")  # 지도·그래픽은 글자가 뭉개지지 않게 PNG
    if getattr(im, "is_animated", False):
        im.seek(getattr(im, "n_frames", 1) - 1)  # 움직이는 경로도는 마지막(최신) 장면
    im = im.convert("RGB")
    im.thumbnail((1200, 1200))
    OUT.mkdir(parents=True, exist_ok=True)
    path = dest_base.with_suffix(".png" if keep_png else ".jpg")
    if keep_png:
        im.save(path, "PNG", optimize=True)
    else:
        im.save(path, "JPEG", quality=82, optimize=True, progressive=True)
    return path


def caption(lang, info, note):
    word = CAPTION.get(lang, "Photo")
    head = f"{note} · " if note else ""
    return html.escape(f"{head}{word}: {info['credit']} · {info['license']}")


def process(md):
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return 0
    _, fm_raw, body = text.split("---", 2)
    fm = yaml.safe_load(fm_raw) or {}
    reqs = fm.get("image_requests") or []
    if not reqs:
        return 0
    lang = fm.get("lang") or "ko"
    slug = re.sub(r"\.(tistory|naver)$", "", md.stem)
    done, remaining, new_images = 0, [], []
    for rq in reqs:
        marker = f"<!-- img:{rq['id']} -->"
        try:
            src = rq.get("source", "wikimedia")
            info = {"url": lambda: from_url(rq["url"]), "jtwc": lambda: from_jtwc(rq["storm"]),
                    "openverse": lambda: from_openverse(rq["query"])}.get(src, lambda: from_wikimedia(rq["query"]))()
            if not info:
                print(f"  {md.name} {rq['id']}: 맞는 이미지 없음 ({src} '{rq.get('query', '')}')")
                remaining.append(rq)
                continue
            path = save_image(get(info["download"], binary=True), OUT / f"{slug}-{rq['id']}")
        except Exception as e:
            print(f"  {md.name} {rq['id']}: 실패 — {e}"[:300])
            remaining.append(rq)
            continue
        rel = "/" + str(path.relative_to(ROOT))
        # 한 덩어리 HTML(두 줄) — 문장 나누기(readable_*)가 캡션을 쪼개지 않는다
        alt = html.escape(rq.get("alt", ""), quote=True)
        block = (f'<figure style="margin:20px 0;"><img src="{rel}" alt="{alt}" loading="lazy">\n'
                 f'<figcaption style="font-size:13px;color:#777;text-align:center;">{caption(lang, info, rq.get("note"))}</figcaption></figure>')
        body = body.replace(marker, "\n" + block + "\n") if marker in body else body.rstrip() + "\n\n" + block + "\n"
        new_images.append({"src": rel, "license": info["license"], "credit": info["credit"], "source_url": info["source_url"]})
        print(f"  ✓ {md.name} {rq['id']}: {info['site']} · {info['license']} → {rel}")
        done += 1
    if not done:
        return 0
    lines = fm_raw.strip("\n").split("\n")
    # image_requests 블록을 남은 요청으로 바꾸고, images: 에 받은 이미지를 덧붙인다 (나머지 front matter 모양은 그대로)
    out, i = [], 0
    while i < len(lines):
        if re.match(r"^image_requests:", lines[i]):
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t", "-")) or not lines[i].strip()):
                i += 1
            if remaining:
                out.append(yaml.safe_dump({"image_requests": remaining}, allow_unicode=True, sort_keys=False, width=1000).rstrip())
            continue
        out.append(lines[i])
        i += 1
    img_lines = []
    for im in new_images:
        img_lines += [f"  - src: {im['src']}", f"    license: {json.dumps(im['license'], ensure_ascii=False)}",
                      f"    credit: {json.dumps(im['credit'], ensure_ascii=False)}", f"    source_url: {im['source_url']}"]
    idx = next((k for k, l in enumerate(out) if re.match(r"^images:", l)), None)
    if idx is None:
        out += ["images:"] + img_lines
    else:
        out[idx] = "images:"
        j = idx + 1
        while j < len(out) and out[j].startswith((" ", "-")):
            j += 1
        out[j:j] = img_lines
    md.write_text("---\n" + "\n".join(out) + "\n---" + body, encoding="utf-8")
    return done


def main():
    files = [Path(a) for a in sys.argv[1:]] or [p for d in DRAFT_DIRS for p in sorted((ROOT / d).glob("*.md"))]
    total = sum(process(p if p.is_absolute() else ROOT / p) for p in files)
    print(f"이미지 {total}장 넣음")


if __name__ == "__main__":
    main()
