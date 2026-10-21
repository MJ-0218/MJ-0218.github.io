#!/usr/bin/env python3
"""해외 글을 Google Blogger 에 예약 발행한다 (공식 Blogger API v3, 사용자 승인 2026-10-21).

GitHub Actions(blogger-publish.yml)가 돌린다. 작성 세션에는 비밀값이 없다.
  1. automation/global/drafts/*.md 중 검증 통과 + 아직 안 올린 글을 고른다
     - 사람이 이미 직접 올린 글(automation/state/published.json 의 blogger=true)은 건너뛴다
     - 이미 예약한 글(automation/state/blogger_scheduled.json)은 건너뛴다
  2. 추천 시각을 정한다: 미국 동부 6~22시, 글 사이 120분 (config.yml us_publish). 즉시 발행 글(Recalls·publish: now)은 바로.
  3. 초안으로 넣고(posts.insert isDraft=true) 그 시각으로 예약 발행(posts.publish publishDate)
  4. 결과를 blogger_scheduled.json 에 남긴다 → 작성 세션이 대기함 '발행함'(db published/<slug>.blogger)에 체크

필요한 GitHub secrets: BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID
없으면 계획만 출력하고 끝낸다(--dry-run 과 같음).

  python3 automation/scripts/blogger_publish.py [--dry-run] [--limit N]
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


def call(token, method, path, params=None, body=None):
    """429·5xx 는 30초·90초·180초 쉬고 다시 시도한다. 실패하면 Google 이 돌려준 오류 내용을 그대로 보여 준다."""
    url = f"{API}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    for wait in (30, 90, 180, None):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:1500]
            print(f"  ! {method} {path} → HTTP {e.code}: {detail}")
            if e.code in (429, 500, 502, 503) and wait:
                print(f"  … {wait}초 뒤 다시 시도")
                time.sleep(wait)
                continue
            raise ApiError(f"HTTP {e.code}: {detail}") from None


def next_slot(after, hours, spacing):
    """after 이후 첫 추천 시각 (ET 기준 hours[0]~hours[1] 사이, 정시)."""
    t = after.astimezone(ET).replace(second=0, microsecond=0)
    t = t.replace(minute=0) + timedelta(hours=1) if t.minute else t
    while not (hours[0] <= t.hour < hours[1]):
        t = (t + timedelta(hours=1)).replace(minute=0)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "automation" / "config.yml").read_text(encoding="utf-8"))
    upub = cfg.get("us_publish", {})
    hours, spacing = upub.get("hours", [6, 22]), int(upub.get("spacing_minutes", 120))
    keep_days = int(cfg.get("publish", {}).get("outbox_days", 21))
    site = cfg.get("site_url", "").rstrip("/")
    secrets = all(os.environ.get(k) for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN", "BLOGGER_BLOG_ID"))
    dry = a.dry_run or not secrets
    if not secrets:
        print("Blogger 비밀값이 없어 계획만 출력합니다 (GitHub Settings → Secrets 에 BLOGGER_* 4개 필요)")

    scheduled, published = load_json(SCHEDULED), load_json(PUBLISHED)
    now = datetime.now(timezone.utc)
    # 이미 예약된 가장 늦은 시각 뒤로 간격을 둔다
    last = max([datetime.fromisoformat(v["publish_at"]) for v in scheduled.values() if v.get("publish_at")] or [now])
    cursor = max(now + timedelta(minutes=15), last + timedelta(minutes=spacing))

    todo = []
    for md in sorted((ROOT / "automation" / "global" / "drafts").glob("*.md")):
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
    if a.limit:
        todo = todo[: a.limit]

    token = None if dry else access_token()
    blog = os.environ.get("BLOGGER_BLOG_ID", "")
    existing = {}
    if not dry and todo:
        # 블로그에 이미 같은 제목 글(초안·예약·발행)이 있으면 새로 만들지 않는다 — 기록이 늦게 반영돼도 중복 방지
        page = None
        while True:
            q = [("status", "draft"), ("status", "scheduled"), ("status", "live"), ("fetchBodies", "false"), ("maxResults", "50")]
            if page:
                q.append(("pageToken", page))
            res = call(token, "GET", f"/blogs/{blog}/posts?" + urllib.parse.urlencode(q))
            for it in res.get("items", []):
                existing.setdefault(it.get("title", "").strip(), it)
            page = res.get("nextPageToken")
            if not page:
                break
    changed, failed, done = False, False, 0
    for md, slug, fm, urgent in todo:
        r = render(md, site)
        if urgent:
            when = None
        else:
            when = next_slot(cursor, hours, spacing)
            cursor = when + timedelta(minutes=spacing)
        label = "즉시" if when is None else when.strftime("%m/%d %H:%M ET")
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
                post = call(token, "POST", f"/blogs/{blog}/posts", {"isDraft": "true"},
                            {"kind": "blogger#post", "title": r["title"], "content": r["html"], "labels": r["tags"]})
                post_id = post["id"]
                # 초안까지 만든 것을 먼저 남겨 두어 다음 실행에서 중복 초안을 만들지 않는다
                scheduled[slug] = {"post_id": post_id, "status": "DRAFT", "scheduled_at": now.isoformat(timespec="minutes")}
                changed = True
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
        done += 1
        time.sleep(5)  # 요청 사이 간격
    if changed:
        SCHEDULED.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULED.write_text(json.dumps(scheduled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"예약 {done}편 · 대상 {len(todo)}편")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
