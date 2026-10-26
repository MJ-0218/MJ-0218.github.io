"""인스타·틱톡 급상승 클립 → 허가 대기 후보.

vidIQ 급상승 검색(instagram_tiktok_outlier_search)은 Claude 세션에서만 부를 수 있어서,
세션이 결과를 JSON 목록으로 옮겨 적고 `run.py social-import <파일>` 로 넣는다.

항목 형식: {platform: instagram|tiktok, url, id, handle, caption, hook, views, multiple, followers,
           posted, seconds, lang: ko|en, score, reason}
"""
import datetime as dt
import json
import re

from .common import STATE, load_history, load_sources

# 방송사·OTT·영화 클립 재업로드 계정, 남의 영상을 모으는 계정 — 올린 사람에게 허락받아도 권리가 없다
REPOST_HANDLE = re.compile(r"tvn|tving|coupang|netflix|wavve|mbc|kbs|sbs|jtbc|drama|movie|film|clip|kuja|magazine|news", re.I)
REPOST_TEXT = re.compile(r"줄거리|쿠팡플레이|방송|개봉|드라마|TVING|tvN|풀버전|출연|OTT|명장면|시리즈|예고|스트리밍", re.I)

DM_KO = ("안녕하세요 @{h}님! 올려 주신 영상 정말 재밌게 봤어요. "
         "저희 유튜브 쇼츠 채널에서 이 영상에 한국어 자막과 나레이션을 붙여 소개해도 될까요? "
         "영상 화면과 설명란에 @{h}님 출처와 계정 링크를 꼭 남기겠습니다. "
         "불편하시면 편하게 거절하셔도 괜찮아요. 감사합니다!")
DM_EN = ("Hi @{h}! I loved this video. I run a Korean YouTube Shorts channel — may I re-edit it with "
         "Korean subtitles and narration? I'll credit @{h} on screen and link your account in the "
         "description. Totally fine to say no. Thank you!")


def profile_url(platform, handle):
    return f"https://www.tiktok.com/@{handle}" if platform == "tiktok" else f"https://www.instagram.com/{handle}/"


def rejected(item):
    """거를 이유 또는 None."""
    if REPOST_HANDLE.search(item.get("handle", "")):
        return "방송·모음 계정"
    if REPOST_TEXT.search(item.get("caption", "") + " " + item.get("hook", "")):
        return "방송·영화 클립"
    return None


def import_items(items):
    path = STATE / "candidates.json"
    cands = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    seen = {c["url"] for c in cands} | {e.get("url") for e in load_sources()} | {v.get("url") for v in load_history()["videos"]}
    today = dt.date.today().isoformat()
    added, skipped = 0, []
    for it in items:
        why = rejected(it)
        if why or it["url"] in seen:
            skipped.append((it.get("handle"), why or "이미 있음"))
            continue
        seen.add(it["url"])
        h = it["handle"].lstrip("@")
        cands.append({
            "video_id": f"{it['platform'][:2]}-{it['id']}", "url": it["url"], "platform": it["platform"],
            "title": (it.get("hook") or it.get("caption") or "")[:80], "channel": "@" + h,
            "channel_url": profile_url(it["platform"], h), "channel_id": "",
            "views": int(it.get("views") or 0), "seconds": int(it.get("seconds") or 0),
            "multiple": it.get("multiple"), "score": it.get("score"), "reason": it.get("reason", ""),
            "dm": (DM_KO if it.get("lang", "ko") == "ko" else DM_EN).format(h=h),
            "desc": it.get("caption", "")[:300], "thumb": "", "found": today,
        })
        added += 1
    path.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    for h, why in skipped:
        print(f"  건너뜀 @{h}: {why}")
    print(f"인스타·틱톡 후보 {added}편 추가 (건너뜀 {len(skipped)})")
    return added
