"""Blogger 403 진단 — 토큰 권한(scope), 블로그별 내 역할·상태, 미국 블로그 초안 1편 시험 작성(성공하면 바로 삭제).
비밀값·블로그 ID·이메일은 출력하지 않는다."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from blogger_publish import access_token  # noqa: E402

API = "https://www.googleapis.com/blogger/v3"
KEYS = ["", "_IN", "_PH", "_SG", "_MY", "_VN", "_ID", "_TH", "_TW"]


def req(method, url, token, body=None):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as x:
            raw = x.read()
            return x.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:600]


tok = access_token()
code, info = req("GET", "https://oauth2.googleapis.com/tokeninfo?access_token=" + urllib.parse.quote(tok), tok)
print("1) 토큰 scope:", info.get("scope") if isinstance(info, dict) else (code, info))
code, me = req("GET", f"{API}/users/self", tok)
print("2) /users/self:", code, "OK" if code == 200 else me)
for k in KEYS:
    bid = os.environ.get("BLOGGER_BLOG_ID" + k, "")
    if not bid:
        continue
    code, d = req("GET", f"{API}/users/self/blogs/{bid}?view=AUTHOR", tok)
    if code == 200:
        b, u = d.get("blog", {}), d.get("blog_user_info", {})
        print(f"3) {k or '_US'}: {b.get('name')} status={b.get('status')} role={u.get('role')} admin={u.get('hasAdminAccess')}")
    else:
        print(f"3) {k or '_US'}: HTTP {code} {d}")
bid = os.environ.get("BLOGGER_BLOG_ID", "")
code, d = req("POST", f"{API}/blogs/{bid}/posts?isDraft=true", tok,
              {"kind": "blogger#post", "title": "diagnose draft (auto delete)", "content": "<p>test</p>"})
print("4) 미국 블로그 초안 작성:", code, d if code != 200 else "성공")
if code == 200:
    c2, _ = req("DELETE", f"{API}/blogs/{bid}/posts/{d['id']}", tok)
    print("   시험 초안 삭제:", c2)
