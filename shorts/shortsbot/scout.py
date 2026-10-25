"""원본 클립 자동 탐색 (YouTube Data API).

- cc     : 크리에이티브 커먼즈(CC BY)로 공개된 짧은 인기 영상 → sources.yml 에 바로 등록(출처 표기 자동)
- 허락용 : 일반 라이선스 인기 영상 → state/candidates.md 에 허락 요청 문구와 함께 목록만 만든다.
           원작자가 허락하면 sources.yml 에 license: permission + proof 로 옮기면 된다.
"""
import datetime as dt
import json
import re
import urllib.parse
import urllib.request

import yaml

from .common import ROOT, STATE, env, load_history, load_sources

API = "https://www.googleapis.com/youtube/v3"
# 남의 영상을 모아 올리는 채널일 가능성이 큰 제목은 CC 표시를 믿지 않는다
REUPLOAD_HINT = re.compile(r"compilation|모음|best of|reupload|tiktok|틱톡|credit|출처|via @", re.I)


def _auth():
    if all(env(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
        from .upload import access_token
        return {"Authorization": f"Bearer {access_token()}"}, {}
    if env("YT_API_KEY"):
        return {}, {"key": env("YT_API_KEY")}
    raise RuntimeError("YT_API_KEY 또는 YT_CLIENT_ID/SECRET/REFRESH_TOKEN 이 필요함")


def _get(path, params, auth):
    headers, extra = auth
    url = f"{API}/{path}?" + urllib.parse.urlencode({**params, **extra})
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.loads(r.read())


def _seconds(iso):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def search(query, license_, scfg, auth):
    since = (dt.datetime.utcnow() - dt.timedelta(days=scfg["max_age_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = _get("search", {
        "part": "snippet", "type": "video", "q": query, "videoLicense": license_,
        "videoDuration": "short", "order": "viewCount", "publishedAfter": since,
        "maxResults": 25, "safeSearch": "strict"}, auth)
    ids = [it["id"]["videoId"] for it in res.get("items", [])]
    if not ids:
        return []
    vids = _get("videos", {"part": "snippet,status,contentDetails,statistics", "id": ",".join(ids)}, auth)
    out = []
    for v in vids.get("items", []):
        sec = _seconds(v["contentDetails"]["duration"])
        views = int(v["statistics"].get("viewCount", 0))
        if not (scfg["min_sec"] <= sec <= scfg["max_sec"]) or views < scfg["min_views"]:
            continue
        out.append({
            "video_id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}",
            "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
            "channel_id": v["snippet"]["channelId"], "license": v["status"].get("license"),
            "seconds": sec, "views": views,
            "desc": (v["snippet"].get("description") or "")[:300],
        })
    return out


def known_urls():
    urls = {e.get("url") for e in load_sources()}
    urls |= {v.get("url") for v in load_history()["videos"]}
    return {u for u in urls if u}


def append_sources(entries):
    """sources.yml 끝에 덧붙인다(위쪽 주석은 그대로 둔다)."""
    text = (ROOT / "sources.yml").read_text(encoding="utf-8").rstrip("\n") + "\n"
    for e in entries:
        block = yaml.safe_dump([e], allow_unicode=True, sort_keys=False, width=200)
        text += "".join("  " + line + "\n" for line in block.splitlines())
    (ROOT / "sources.yml").write_text(text, encoding="utf-8")


def scout(cfg, need):
    scfg = cfg["scout"]
    auth = _auth()
    seen = known_urls()
    today = dt.date.today().isoformat()
    added, candidates = [], []
    for q in scfg["queries"]:
        if len(added) >= need:
            break
        for c in search(q, "creativeCommon", scfg, auth):
            if c["url"] in seen or c["license"] != "creativeCommon" or REUPLOAD_HINT.search(c["title"] + " " + c["desc"]):
                continue
            seen.add(c["url"])
            added.append({
                "id": f"cc-{c['video_id']}", "url": c["url"], "license": "cc-by",
                "proof": f"YouTube API status.license=creativeCommon ({today} 확인)",
                "credit": c["channel"], "note": f"원제: {c['title']} / {c['desc'][:150]}".replace("\n", " "),
            })
            if len(added) >= need:
                break
    if scfg.get("permission_candidates"):
        for q in scfg["queries"][: scfg["permission_queries"]]:
            for c in search(q, "youtube", scfg, auth):
                if c["url"] not in seen:
                    seen.add(c["url"])
                    candidates.append(c)
    if added:
        append_sources(added)
    if candidates:
        write_candidates(candidates)
    print(f"탐색: CC BY {len(added)}편 등록, 허락 요청 후보 {len(candidates)}편")
    return len(added)


def write_candidates(cands):
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / "candidates.md"
    old = path.read_text(encoding="utf-8") if path.exists() else "# 허락 요청 후보\n\n원작자가 허락하면 sources.yml 에 `license: permission`, `proof`(허락 날짜·캡처 경로), `credit` 로 옮긴다.\n"
    rows = []
    for c in sorted(cands, key=lambda c: -c["views"])[:30]:
        rows.append(
            f"\n## {c['title']}\n- {c['url']} · {c['channel']} · 조회 {c['views']:,} · {c['seconds']}초\n"
            f"- 채널: https://www.youtube.com/channel/{c['channel_id']}\n"
            f"- 요청 문구:\n  > Hi {c['channel']}! I run a Korean Shorts channel and loved this video. "
            f"May I re-edit it with Korean narration and subtitles? I'll credit you in the video and description "
            f"and link your channel. Thank you!\n")
    path.write_text(old + f"\n---\n### {dt.date.today().isoformat()}\n" + "".join(rows), encoding="utf-8")
