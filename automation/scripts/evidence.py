#!/usr/bin/env python3
"""원문 수집본(evidence) — 작성 세션에서 열리지 않는 사이트의 원문을 GitHub Actions(레이더)가 대신 받아 둔 것.

레이더(Actions)는 인터넷이 열려 있어서 방송 맛집 기사, 급상승 이슈 기사, 그리고
automation/state/fetch_requests.txt 에 적힌 URL(국토부·복지로처럼 작성 세션에서 막힌 공식 누리집)을
받아 radar-data 브랜치 trends/evidence/<해시>.json 으로 저장한다.

  python3 automation/scripts/evidence.py pull                # radar-data 의 수집본을 /tmp/evidence 로 풀기
  python3 automation/scripts/evidence.py show <URL> [찾을말]  # 수집본 원문 보기 (fetch_source.py 처럼)
  python3 automation/scripts/evidence.py list [검색어]         # 수집본 목록

verify_claims.py 는 원문 열기에 실패하면 SEMTER_EVIDENCE_DIR(기본 /tmp/evidence)의 수집본으로 대조한다.
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DIR = Path(os.environ.get("SEMTER_EVIDENCE_DIR", "/tmp/evidence"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def key(url):
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16]


def html_to_text(raw, ctype=""):
    enc = re.search(r"charset=([\w-]+)", ctype) or re.search(rb'charset=["\']?([\w-]+)', raw[:3000])
    name = enc.group(1) if enc else "utf-8"
    name = name.decode() if isinstance(name, bytes) else name
    try:
        txt = raw.decode(name)
    except (LookupError, UnicodeDecodeError):
        txt = raw.decode("euc-kr", errors="ignore")
    txt = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
    txt = re.sub(r"<br\s*/?>|</p>|</li>|</tr>|</h\d>", "\n", txt, flags=re.I)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    txt = re.sub(r"[ \t\r\f\v]+", " ", txt)
    return re.sub(r"\n\s*\n+", "\n", txt).strip()


def fetch(url, timeout=25):
    # 쿠키를 주고받아야 리다이렉트가 끝나는 누리집(국토부 등)이 있어 쿠키 저장소를 쓴다
    import http.cookiejar
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    with opener.open(req, timeout=timeout) as r:
        return r.geturl(), r.read(), r.headers.get("Content-Type", "")


def save(out_dir, url, title, text, extra=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {"url": url, "title": title, "fetched_at": datetime.now(KST).isoformat(timespec="minutes"), "text": text[:60000]}
    rec.update(extra or {})
    (out_dir / f"{key(url)}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def load(url):
    """수집본이 있으면 {url,title,fetched_at,text} 를 돌려준다."""
    p = DIR / f"{key(url)}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    for f in DIR.glob("*.json") if DIR.exists() else []:  # 리다이렉트로 주소가 바뀐 경우
        rec = json.loads(f.read_text(encoding="utf-8"))
        if url in (rec.get("url"), rec.get("requested_url")):
            return rec
    return None


def pull():
    DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "fetch", "-q", "origin", "radar-data"], check=False)
    names = subprocess.run(["git", "ls-tree", "--name-only", "origin/radar-data", "trends/evidence/"],
                           capture_output=True, text=True).stdout.split()
    for n in names:
        data = subprocess.run(["git", "show", f"origin/radar-data:{n}"], capture_output=True).stdout
        (DIR / Path(n).name).write_bytes(data)
    print(f"수집본 {len(names)}개 → {DIR}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "pull":
        pull()
    elif cmd == "list":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        for f in sorted(DIR.glob("*.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            if q in rec.get("title", "") + rec.get("url", "") + rec.get("topic", ""):
                print(f"{rec['fetched_at']}  {rec.get('topic', '')[:24]:24}  {rec.get('title', '')[:60]}  {rec['url']}")
    elif cmd == "show":
        rec = load(sys.argv[2])
        if not rec:
            sys.exit("수집본 없음 — automation/state/fetch_requests.txt 에 URL 을 적어 두면 다음 레이더 실행(30분 이내)에 받아 둔다")
        print(f"# {rec.get('title', '')}\n# {rec['url']} (수집 {rec['fetched_at']})")
        words = sys.argv[3:]
        if not words:
            print(rec["text"][:4000])
        for w in words:
            idx = [m.start() for m in re.finditer(re.escape(w), rec["text"])]
            print(f"\n=== '{w}' {len(idx)}곳 ===")
            for i in idx[:8]:
                print("…" + rec["text"][max(0, i - 150):i + 250].replace("\n", " ") + "…\n")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
