"""내 PC 에서 한 번만 실행: YouTube 업로드용 refresh token 을 받는다.

  1) Google Cloud 콘솔 → YouTube Data API v3 사용 설정 → OAuth 클라이언트(데스크톱 앱) 만들기
  2) python shorts/get_token.py <client_id> <client_secret>
  3) 브라우저에서 채널 계정으로 허용 → 터미널에 나온 refresh token 을
     GitHub 저장소 Settings → Secrets → Actions 에 YT_REFRESH_TOKEN 으로 저장 (채팅에 붙이지 말 것)
"""
import http.server
import json
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.force-ssl"
PORT = 8765


def main():
    cid, secret = sys.argv[1], sys.argv[2]
    redirect = f"http://127.0.0.1:{PORT}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent"})
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.end_headers()
            self.wfile.write("완료 — 터미널로 돌아가세요".encode())

        def log_message(self, *a):
            pass

    print("브라우저가 열리지 않으면 이 주소를 여세요:\n" + url)
    webbrowser.open(url)
    http.server.HTTPServer(("127.0.0.1", PORT), H).handle_request()
    body = urllib.parse.urlencode({"code": got["code"][0], "client_id": cid, "client_secret": secret,
                                   "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=body) as r:
        tok = json.loads(r.read())
    print("\nYT_REFRESH_TOKEN =", tok["refresh_token"])


if __name__ == "__main__":
    main()
