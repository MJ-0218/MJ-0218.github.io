#!/usr/bin/env python3
"""Blogger 중복 글 정리 — 자동 예약으로 같은 제목 글이 여러 개 생겼을 때 하나만 남기고 지운다.

- 대상: automation/state/blogger_scheduled.json 에 있는 글(자동 발행한 글)의 제목만. 사람이 직접 올린 글은 건드리지 않는다.
- 남기는 글: 기록에 있는 post_id. 기록 글이 블로그에 없으면 가장 먼저 만든 글.
- 기본은 확인만(--apply 를 줘야 실제로 삭제).
  python3 automation/scripts/blogger_dedupe.py [--apply]
"""
import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blogger_publish import SCHEDULED, access_token, call, render, ROOT  # noqa: E402


def all_posts(token, blog):
    out, page = [], None
    while True:
        q = [("status", "draft"), ("status", "scheduled"), ("status", "live"), ("fetchBodies", "false"), ("maxResults", "50")]
        if page:
            q.append(("pageToken", page))
        res = call(token, "GET", f"/blogs/{blog}/posts?" + urllib.parse.urlencode(q))
        out += res.get("items", [])
        page = res.get("nextPageToken")
        if not page:
            return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    blog = os.environ["BLOGGER_BLOG_ID"]
    token = access_token()
    scheduled = json.loads(SCHEDULED.read_text(encoding="utf-8"))
    titles = {}
    for slug, rec in scheduled.items():
        md = ROOT / "automation" / "global" / "drafts" / f"{slug}.md"
        if md.exists():
            titles[render(md, "").get("title", "").strip()] = (slug, rec.get("post_id"))
    posts = all_posts(token, blog)
    deleted = 0
    for title, (slug, keep_id) in titles.items():
        same = sorted([p for p in posts if p.get("title", "").strip() == title], key=lambda p: p.get("updated", ""))
        if len(same) <= 1:
            print(f"OK   {slug}: {len(same)}개")
            continue
        keep = next((p for p in same if p["id"] == keep_id), same[0])
        drop = [p for p in same if p["id"] != keep["id"]]
        print(f"중복 {slug}: {len(same)}개 → 남김 {keep['id']} ({keep.get('status')}), 지움 {[(p['id'], p.get('status')) for p in drop]}")
        if a.apply:
            for p in drop:
                call(token, "DELETE", f"/blogs/{blog}/posts/{p['id']}")
                deleted += 1
        scheduled[slug].update({"post_id": keep["id"], "url": keep.get("url", scheduled[slug].get("url", "")),
                                "status": keep.get("status", scheduled[slug].get("status", ""))})
    if a.apply:
        SCHEDULED.write_text(json.dumps(scheduled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"삭제 {deleted}개" if a.apply else "확인만 함 (--apply 없음)")


if __name__ == "__main__":
    main()
