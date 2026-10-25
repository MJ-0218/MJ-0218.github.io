"""YouTube Data API v3 예약 업로드 (재개 가능 업로드)."""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from .common import env

KST = ZoneInfo("Asia/Seoul")


def access_token():
    body = urllib.parse.urlencode({
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30) as r:
        return json.loads(r.read())["access_token"]


def configured():
    return all(env(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def next_slots(slots_kst, taken, count, now=None):
    """이미 잡힌 시각(taken, ISO)을 피해서 앞으로의 업로드 시각 count 개."""
    now = now or dt.datetime.now(KST)
    taken = set(taken)
    out, day = [], now.date()
    while len(out) < count:
        for hm in slots_kst:
            h, m = map(int, hm.split(":"))
            t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=KST)
            iso = t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if t > now + dt.timedelta(minutes=20) and iso not in taken:
                out.append(iso)
                taken.add(iso)
                if len(out) == count:
                    break
        day += dt.timedelta(days=1)
    return out


def upload(path, meta, publish_at, cfg):
    token = access_token()
    up = cfg["upload"]
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"],
            "tags": [h.lstrip("#") for h in meta["hashtags"]],
            "categoryId": cfg["channel"]["category_id"],
            "defaultLanguage": "ko", "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": up["privacy_until_publish"],
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": cfg["channel"]["made_for_kids"],
            "containsSyntheticMedia": up["contains_synthetic_media"],
        },
    }
    size = os.path.getsize(path)
    init = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    with urllib.request.urlopen(init, timeout=60) as r:
        location = r.headers["Location"]
    with open(path, "rb") as f:
        put = urllib.request.Request(location, data=f.read(), method="PUT", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
    with urllib.request.urlopen(put, timeout=600) as r:
        video = json.loads(r.read())
    vid = video["id"]
    if meta.get("pinned_comment"):
        try:
            comment(token, vid, meta["pinned_comment"])
        except Exception as e:  # 댓글 실패는 업로드 실패가 아니다
            print(f"  댓글 등록 실패({vid}): {e}")
    return vid


def comment(token, vid, text):
    body = {"snippet": {"videoId": vid, "topLevelComment": {"snippet": {"textOriginal": text}}}}
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
