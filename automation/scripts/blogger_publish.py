#!/usr/bin/env python3
"""해외 글을 Google Blogger 에 예약 발행한다 (공식 Blogger API v3, 사용자 승인 2026-10-21).
블로그 여러 개(config.yml blogs: 미국·인도·쇼피 국가별)를 차례로 돈다. 블로그마다 초안 폴더·예약 기록·시간대·하루 편수가 따로다.

GitHub Actions(blogger-publish.yml)가 돌린다. 작성 세션에는 비밀값이 없다.
  1. automation/global/drafts/*.md 중 검증 통과 + 아직 안 올린 글을 고른다
     - 사람이 이미 직접 올린 글(automation/state/published.json 의 blogger=true)은 건너뛴다
     - 이미 예약한 글(automation/state/blogger_scheduled.json)은 건너뛴다
  2. 추천 시각을 정한다: 미국 동부 6~22시, 글 사이 120분 (config.yml us_publish). 즉시 발행 글(Recalls·publish: now)은 바로.
  3. 초안으로 넣고(posts.insert isDraft=true) 그 시각으로 예약 발행(posts.publish publishDate)
  4. 결과를 blogger_scheduled.json 에 남긴다 → 작성 세션이 대기함 '발행함'(db published/<slug>.blogger)에 체크

필요한 GitHub secrets: BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN + 블로그마다 BLOGGER_BLOG_ID(_IN/_PH …)
없으면 계획만 출력하고 끝낸다(--dry-run 과 같음).

  python3 automation/scripts/blogger_publish.py [--dry-run] [--blog in]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.error
import urllib.request
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from build_outbox import is_urgent, render  # noqa: E402
from style_check import check as style_check, split_front_matter  # noqa: E402
from verify_claims import verify  # noqa: E402
from export_paste import fm_value  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")
SCHEDULED = ROOT / "automation" / "state" / "blogger_scheduled.json"
PUBLISHED = ROOT / "automation" / "state" / "published.json"
BLOGS_INFO = ROOT / "automation" / "state" / "blogs.json"  # 블로그 키 → 이름·주소 (카드 꼬리표·대기함에 씀)
API = "https://www.googleapis.com/blogger/v3"


def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def access_token():
    body = urllib.parse.urlencode({
        "client_id": os.environ["BLOGGER_CLIENT_ID"], "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
        "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30) as r:
        return json.loads(r.read())["access_token"]


class ApiError(Exception):
    pass


def call(token, method, path, params=None, body=None, retry=True):
    """429·5xx 는 30초·90초·180초 쉬고 다시 시도한다. 실패하면 Google 이 돌려준 오류 내용을 그대로 보여 준다."""
    url = f"{API}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)  # GET·DELETE 는 본문 없음
    for wait in (30, 90, 180, None):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:1500]
            print(f"  ! {method} {path} → HTTP {e.code}: {detail}")
            if e.code in (429, 500, 502, 503) and wait and retry:
                print(f"  … {wait}초 뒤 다시 시도")
                time.sleep(wait)
                continue
            raise ApiError(f"HTTP {e.code}: {detail}") from None


def list_titles(token, blog):
    out, page = {}, None
    while True:
        q = [("status", "draft"), ("status", "scheduled"), ("status", "live"), ("fetchBodies", "false"), ("maxResults", "50")]
        if page:
            q.append(("pageToken", page))
        res = call(token, "GET", f"/blogs/{blog}/posts?" + urllib.parse.urlencode(q))
        for it in res.get("items", []):
            out.setdefault(it.get("title", "").strip(), it)
        page = res.get("nextPageToken")
        if not page:
            return out


def blogs_config(cfg):
    """config.yml blogs: — 키(us, in, ph …)별 설정. 예전 설정(us_publish)만 있으면 미국 하나로 본다."""
    b = cfg.get("blogs")
    if b:
        return b
    up = cfg.get("us_publish", {})
    return {"us": {"secret": "BLOGGER_BLOG_ID", "tz": "America/New_York", "hours": up.get("hours", [6, 22]),
                   "spacing_minutes": up.get("spacing_minutes", 120), "per_day": 0,
                   "drafts": "automation/global/drafts", "state": "automation/state/blogger_scheduled.json"}}


def next_slot(after, hours, tz, per_day=0, counts=None):
    """after 이후 첫 추천 시각 (그 나라 시간 hours[0]~hours[1] 사이, 정시). per_day 가 차 있는 날은 다음 날로."""
    t = after.astimezone(tz).replace(second=0, microsecond=0)
    t = t.replace(minute=0) + timedelta(hours=1) if t.minute else t
    while True:
        if not (hours[0] <= t.hour < hours[1]):
            t = (t + timedelta(hours=1)).replace(minute=0)
            continue
        if per_day and (counts or {}).get(t.date(), 0) >= per_day:
            t = (t + timedelta(days=1)).replace(hour=hours[0], minute=0)
            continue
        return t


def save_blog_info(blogs):
    """시크릿이 들어 있는 블로그의 이름·주소를 automation/state/blogs.json 에 맞춰 둔다 (시크릿이 맞는지 확인도 겸함)."""
    names = load_json(BLOGS_INFO)
    token = None
    for key, bc in blogs.items():
        blog = os.environ.get(bc["secret"], "")
        if not blog:
            print(f"{key}: 시크릿 {bc['secret']} 없음")
            continue
        token = token or access_token()
        try:
            info = call(token, "GET", f"/blogs/{blog}", retry=False)
        except ApiError as e:
            print(f"{key}: 블로그를 열 수 없음 — 시크릿 {bc['secret']} 값을 확인 ({e})")
            continue
        rec = {"name": info.get("name", ""), "url": info.get("url", "")}
        print(f"{key}: {rec['name']} {rec['url']} (글 {(info.get('posts') or {}).get('totalItems', 0)}편)")
        names[key] = rec
    BLOGS_INFO.write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_blog(key, bc, cfg, now, budget, dry_all, published):
    """블로그 하나: 검증 통과 + 아직 안 올린 글을 예약한다. 새로 만든 글 수를 돌려준다."""
    blog = os.environ.get(bc["secret"], "")
    dry = dry_all or not blog
    tz = ZoneInfo(bc.get("tz", "America/New_York"))
    hours, spacing = bc.get("hours", [6, 22]), int(bc.get("spacing_minutes", 120))
    per_day = int(bc.get("per_day", 0) or 0)
    keep_days = int(cfg.get("publish", {}).get("outbox_days", 21))
    site = cfg.get("site_url", "").rstrip("/")
    state_p = ROOT / bc["state"]
    scheduled = load_json(state_p)
    drafts = sorted((ROOT / bc["drafts"]).glob("*.md"))
    if not drafts:
        return 0, False
    print(f"\n── {key} ({bc.get('label', '')}) {'[블로그 ID 시크릿 없음 — 계획만]' if not blog else ''}")

    counts = {}
    for v in scheduled.values():
        if v.get("publish_at"):
            d = datetime.fromisoformat(v["publish_at"]).astimezone(tz).date()
            counts[d] = counts.get(d, 0) + 1
    last = max([datetime.fromisoformat(v["publish_at"]) for v in scheduled.values() if v.get("publish_at")] or [now])
    cursor = max(now + timedelta(minutes=15), last + timedelta(minutes=spacing))

    todo = []
    for md in drafts:
        slug = md.stem
        if (published.get(slug) or {}).get("blogger"):
            continue
        if slug in scheduled and scheduled[slug].get("status") != "DRAFT":
            continue  # DRAFT = 초안만 만들고 예약 단계에서 멈춘 글 → 같은 초안으로 다시 예약
        text = md.read_text(encoding="utf-8")
        fm, _ = split_front_matter(text)
        asof = fm_value(fm, "info_as_of")
        if asof and (now.date() - datetime.fromisoformat(asof).date()).days > keep_days:
            continue
        v, s = verify(md, fetch=False), style_check(md)
        if v["fail"] or s["fail"]:
            print(f"건너뜀 {slug}: 검증 실패 {v['fail'][:2]} {s['fail'][:2]}")
            continue
        todo.append((md, slug, fm, is_urgent(fm, text)))
    todo.sort(key=lambda x: not x[3])  # 즉시 발행 글 먼저
    if not todo:
        return 0, False

    token = None if dry else access_token()
    # 블로그에 이미 같은 제목 글(초안·예약·발행)이 있으면 새로 만들지 않는다 — 기록이 늦게 반영돼도 중복 방지
    existing = list_titles(token, blog) if not dry else {}
    changed, failed, made = False, False, 0
    for md, slug, fm, urgent in todo:
        if made >= budget:
            print(f"이번 실행 한도 — 남은 {len(todo) - made}편은 다음 실행에서")
            break
        r = render(md, site)
        today = now.astimezone(tz).date()
        if urgent and not (per_day and counts.get(today, 0) >= per_day):
            when = None
        else:
            when = next_slot(cursor, hours, tz, per_day, counts)
            cursor = when + timedelta(minutes=spacing)
        d = (when or now).astimezone(tz).date()
        counts[d] = counts.get(d, 0) + 1
        label = "즉시" if when is None else when.strftime("%m/%d %H:%M ") + str(tz)
        print(f"{'[계획] ' if dry else ''}{slug} → {label}  «{r['title']}»")
        if dry:
            continue
        same = existing.get(r["title"].strip())
        if same and not (scheduled.get(slug) or {}).get("post_id"):
            print(f"  = 이미 블로그에 같은 제목 글이 있음 ({same.get('status')}) — 새로 만들지 않고 기록만 맞춤")
            scheduled[slug] = {"post_id": same["id"], "url": same.get("url", ""), "status": same.get("status", ""),
                               "publish_at": same.get("published") or now.isoformat(timespec="minutes"),
                               "scheduled_at": now.isoformat(timespec="minutes"), "adopted": True}
            changed = True
            continue
        try:
            post_id = (scheduled.get(slug) or {}).get("post_id")
            if not post_id:
                # 글 만들기는 다시 보내지 않는다: 429 가 와도 실제로는 만들어졌을 수 있어서, 블로그를 다시 조회해 확인한다
                try:
                    post = call(token, "POST", f"/blogs/{blog}/posts", {"isDraft": "true"},
                                {"kind": "blogger#post", "title": r["title"], "content": r["html"], "labels": r["tags"]}, retry=False)
                except ApiError:
                    time.sleep(60)
                    post = list_titles(token, blog).get(r["title"].strip())
                    if not post:
                        raise
                    print("  = 오류 응답이었지만 글은 만들어져 있음 — 그 글로 이어서 예약")
                post_id = post["id"]
                existing[r["title"].strip()] = post
                # 초안까지 만든 것을 먼저 남겨 두어 다음 실행에서 중복 초안을 만들지 않는다
                scheduled[slug] = {"post_id": post_id, "status": "DRAFT", "scheduled_at": now.isoformat(timespec="minutes")}
                changed = True
                made += 1
            params = {"publishDate": when.isoformat()} if when else None
            pub = call(token, "POST", f"/blogs/{blog}/posts/{post_id}/publish", params)
        except ApiError as e:
            print(f"중단 {slug}: {e} — 남은 글은 다음 실행(매시 40분)에서 이어서 한다")
            failed = True
            break
        scheduled[slug] = {"post_id": post_id, "url": pub.get("url", ""), "status": pub.get("status", ""),
                           "publish_at": (when or now).astimezone(timezone.utc).isoformat(timespec="minutes"),
                           "scheduled_at": now.isoformat(timespec="minutes")}
        changed = True
        time.sleep(int(cfg.get("blogger_run", {}).get("pause_seconds", 20)))  # 요청 사이 간격
    if changed:
        state_p.parent.mkdir(parents=True, exist_ok=True)
        state_p.write_text(json.dumps(scheduled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return made, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--blog", help="이 블로그만 (us, in, ph …)")
    a = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "automation" / "config.yml").read_text(encoding="utf-8"))
    oauth = all(os.environ.get(k) for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"))
    if not oauth:
        print("Blogger 비밀값이 없어 계획만 출력합니다 (GitHub Settings → Secrets 에 BLOGGER_* 필요)")
    dry = a.dry_run or not oauth
    published = load_json(PUBLISHED)
    now = datetime.now(timezone.utc)
    budget = int(cfg.get("blogger_run", {}).get("max_new_per_run", 8))
    failed_any = False
    if not dry:
        save_blog_info(blogs_config(cfg))
    for key, bc in blogs_config(cfg).items():
        if a.blog and key != a.blog:
            continue
        made, failed = run_blog(key, bc, cfg, now, budget, dry, published)
        budget -= made
        failed_any = failed_any or failed
        if budget <= 0:
            print("이번 실행 한도에 닿음 — 나머지 블로그는 다음 실행에서")
            break
    if failed_any:
        sys.exit(1)


if __name__ == "__main__":
    main()
