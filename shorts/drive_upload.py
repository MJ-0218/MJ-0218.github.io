"""검수 통과한 쇼츠를 구글 드라이브 '이게뭐야' 폴더에 'N화 제목' 폴더(영상 + 제목·캡션·태그 문서)로 올린다.
인증: 환경 변수 GDRIVE_TOKEN_JSON(드라이브 권한 refresh token). 기록: state/drive.json(다음 화 번호, 올린 영상).
사용: python3 shorts/drive_upload.py <영상id> "<짧은 이름>" [...]   (영상id·이름 쌍을 여러 개)"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "drive.json"
API = "https://www.googleapis.com"


def token():
    t = json.loads(os.environ["GDRIVE_TOKEN_JSON"])
    body = urllib.parse.urlencode({"client_id": t["client_id"], "client_secret": t["client_secret"],
                                   "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request(t["token_uri"], data=body), timeout=30).read())["access_token"]


def call(at, method, url, data=None, ctype="application/json", extra=None):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + at, "Content-Type": ctype, **(extra or {})})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r, (r.read() or b"{}")


def doc_text(name, v):
    return (f"{name}\n\n[제목]\n{v['title']}\n\n[설명(캡션)]\n{v['description']}\n\n[태그]\n{', '.join(v.get('tags') or [])}"
            f"\n\n[고정 댓글]\n{v.get('pinned_comment', '')}\n\n[영상 길이]\n{v.get('length')}초\n")


def upload(pairs):
    st = json.loads(STATE.read_text(encoding="utf-8"))
    hist = {v["id"]: v for v in json.loads((ROOT / "state" / "history.json").read_text(encoding="utf-8"))["videos"]}
    at = token()
    for vid, short in pairs:
        if vid in st["uploaded"]:
            print(f"이미 올림 {vid} → {st['uploaded'][vid]['folder']}")
            continue
        v = hist[vid]
        if v.get("status") != "검수 통과":
            sys.exit(f"{vid} 는 검수 통과 전({v.get('status')}) — 올리지 않음")
        name = f"{st['next']}화 {short}"
        _, b = call(at, "POST", f"{API}/drive/v3/files?fields=id,webViewLink",
                    json.dumps({"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [st["folder_id"]]}).encode())
        fd = json.loads(b)
        mp4 = urllib.request.urlopen(v["download_url"], timeout=600).read()
        r, _ = call(at, "POST", f"{API}/upload/drive/v3/files?uploadType=resumable&fields=id",
                    json.dumps({"name": f"{name}.mp4", "parents": [fd["id"]]}).encode(), "application/json; charset=UTF-8",
                    {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(mp4))})
        call(at, "PUT", r.headers["Location"], mp4, "video/mp4")
        bd = "xxBOUNDARYxx"
        meta = json.dumps({"name": f"{name} - 제목·캡션·태그", "mimeType": "application/vnd.google-apps.document", "parents": [fd["id"]]})
        body = (f"--{bd}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{bd}\r\n"
                f"Content-Type: text/plain; charset=UTF-8\r\n\r\n{doc_text(name, v)}\r\n--{bd}--").encode()
        call(at, "POST", f"{API}/upload/drive/v3/files?uploadType=multipart&fields=id", body, f"multipart/related; boundary={bd}")
        st["uploaded"][vid] = {"folder": name, "url": fd["webViewLink"]}
        st["next"] += 1
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"올림 {name} {fd['webViewLink']}")


if __name__ == "__main__":
    a = sys.argv[1:]
    upload(list(zip(a[0::2], a[1::2])))
