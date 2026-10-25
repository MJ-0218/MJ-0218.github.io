"""쇼츠 자동화 실행기.

  python shorts/run.py demo              # 키 없이 렌더링만 시험 (가짜 클립·무음 나레이션)
  python shorts/run.py scout             # CC BY 인기 쇼츠 자동 탐색·등록 + 허락 요청 후보 목록
  python shorts/run.py fetch             # sources.yml 의 url(허락·구매 증빙 있는 것만) → inbox/
  python shorts/run.py make [--limit N]  # 클립 → 대본 → 음성 → 완성본 (out/)
  python shorts/run.py upload            # 완성본을 다음 업로드 시각에 예약
  python shorts/run.py daily             # scout + fetch + make(daily_count) + upload
  python shorts/run.py sync <db.json>    # 대기판에서 누른 허가·거절·업로드함 반영
  python shorts/run.py release           # 완성본을 GitHub 릴리스에 올려 휴대폰에서 바로 받게
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shortsbot import brain, rights, variety  # noqa: E402
from shortsbot.common import INBOX, OUT, STATE, load_config, load_history, load_sources, probe, run, save_history  # noqa: E402
from shortsbot.render import render  # noqa: E402


def cmd_fetch(cfg):
    INBOX.mkdir(parents=True, exist_ok=True)
    for e in load_sources():
        if not e.get("url"):
            continue
        reason = rights.check(e)
        if reason:
            print(f"건너뜀 {e.get('id')}: {reason}")
            continue
        dest = INBOX / (e.get("file") or f"{e['id']}.mp4")
        if dest.exists():
            continue
        print(f"받는 중 {e['id']} ← {e['url']}")
        try:
            run(["yt-dlp", "-q", "-f", "bv*[height<=1920]+ba/b", "--merge-output-format", "mp4",
                 "-o", str(dest), e["url"]])
        except RuntimeError as ex:  # 서버 IP 차단 등 — 내 PC 에서 fetch 하면 된다
            print(f"  받기 실패 {e['id']}: {str(ex)[-200:]}")


def cmd_make(cfg, limit, only=None):
    history = load_history()
    done = {v["id"] for v in history["videos"]}
    ready, rejected = rights.ready_clips()
    for cid, why in rejected:
        print(f"보류 {cid}: {why}")
    todo = [(e, p) for e, p in ready if e["id"] not in done and (not only or e["id"] == only)][:limit]
    if not todo:
        print("새로 만들 클립이 없음 — inbox/ 에 클립을 넣고 sources.yml 에 등록하세요")
        return 0
    day = OUT / dt.date.today().isoformat()
    day.mkdir(parents=True, exist_ok=True)
    made = 0
    for entry, path in todo:
        cid = entry["id"]
        try:
            meta = probe(path)
            feedback, script = "", None
            for attempt in range(3):
                script = brain.write_script(path, meta, entry, cfg, history, feedback)
                feedback = variety.check(script, history)
                if not feedback:
                    break
                print(f"  {cid} 다시 쓰기({attempt + 1}): {feedback}")
            if feedback:
                print(f"실패 {cid}: 다양성 검사 통과 못 함 — {feedback}")
                continue
            out = day / f"{cid}.mp4"
            length = render(path, meta, script, cfg, out, credit=entry.get("credit", ""))
            posters = STATE / "posters"
            posters.mkdir(parents=True, exist_ok=True)
            run(["ffmpeg", "-v", "error", "-ss", "1.5", "-i", str(out), "-frames:v", "1", "-vf", "scale=216:-2",
                 "-q:v", "5", "-y", str(posters / f"{cid}.jpg")])
            desc = script.description.strip()
            if entry.get("credit"):
                how = {"cc-by": "CC BY", "permission": "원작자 허락", "licensed": "라이선스 구매"}.get(entry["license"], "")
                desc += f"\n\n원본: {entry['credit']} {entry.get('url', '')} ({how})".replace("  ", " ")
            desc += "\n\n" + " ".join(script.hashtags)
            item = {
                "id": cid, "url": entry.get("url", ""), "file": str(out.relative_to(OUT.parent)), "length": round(length, 1),
                "title": script.title, "description": desc, "hashtags": script.hashtags, "tags": script.tags,
                "hook_type": script.hook_type, "first_line": script.lines[0].text,
                "narration": " ".join(l.text for l in script.lines),
                "pinned_comment": script.pinned_comment,
                "rendered_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
            (day / f"{cid}.json").write_text(json.dumps(script.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
            history["videos"].append(item)
            save_history(history)
            made += 1
            print(f"완성 {cid}: {script.title} ({length:.1f}초)")
        except Exception as ex:
            print(f"실패 {cid}: {ex}")
    return made


def cmd_upload(cfg):
    from shortsbot import upload
    if not cfg["upload"]["enabled"]:
        print("upload.enabled=false — out/ 의 mp4 와 history.json 의 제목·설명으로 직접 올리세요")
        return
    if not upload.configured():
        print("YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN 이 없어 업로드를 건너뜀")
        return
    history = load_history()
    pending = [v for v in history["videos"] if not v.get("video_id") and (OUT.parent / v["file"]).exists()]
    taken = [v["publish_at"] for v in history["videos"] if v.get("publish_at")]
    slots = upload.next_slots(cfg["channel"]["slots_kst"], taken, len(pending))
    for v, slot in zip(pending, slots):
        try:
            v["video_id"] = upload.upload(OUT.parent / v["file"], v, slot, cfg)
            v["publish_at"] = slot
            save_history(history)
            print(f"예약 {v['id']} → {slot} (https://youtube.com/shorts/{v['video_id']})")
        except Exception as ex:
            print(f"업로드 실패 {v['id']}: {ex}")
            if "quotaExceeded" in str(ex) or "uploadLimitExceeded" in str(ex):
                break


def made_today(history):
    today = dt.date.today().isoformat()
    return sum(1 for v in history["videos"] if v.get("rendered_at", "").startswith(today))


def cmd_sync(db_path):
    """대기판 db 내용(JSON: {approve:{vid:{note,at}}, reject:{vid:{}}, uploaded:{id:{at}}})을 반영."""
    from shortsbot.scout import append_sources
    db = json.loads(Path(db_path).read_text(encoding="utf-8"))
    cpath = STATE / "candidates.json"
    cands = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else []
    known = {e.get("url") for e in load_sources()}
    add, keep = [], []
    for c in cands:
        a = (db.get("approve") or {}).get(c["video_id"])
        if a and c["url"] not in known:
            add.append({
                "id": f"yt-{c['video_id']}", "url": c["url"], "license": "permission",
                "proof": f"대기판에서 사용자가 허가 확인 {a.get('at', '')}: {a.get('note', '')}".strip(),
                "credit": c["channel"], "note": f"원제: {c['title']} / {c.get('desc', '')[:150]}".replace("\n", " "),
            })
        elif not a and c["video_id"] not in (db.get("reject") or {}):
            keep.append(c)
    if add:
        append_sources(add)
    cpath.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    history = load_history()
    marked = 0
    for v in history["videos"]:
        u = (db.get("uploaded") or {}).get(v["id"])
        if u and not v.get("uploaded_manual"):
            v["uploaded_manual"] = u.get("at") or True
            marked += 1
    save_history(history)
    print(f"동기화: 허가 {len(add)}편 → sources.yml, 후보 {len(keep)}편 남음, 업로드함 {marked}편")


def cmd_release():
    """out/ 의 새 완성본을 날짜별 GitHub 릴리스에 올리고 받기 주소를 기록. 14일 지난 릴리스는 지운다."""
    import os
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("GITHUB_REPOSITORY 가 없어 릴리스를 건너뜀(Actions 에서만 동작)")
        return
    history = load_history()
    todo = [v for v in history["videos"] if not v.get("download_url") and (OUT.parent / v["file"]).exists()]
    for v in todo:
        tag = "shorts-" + v["rendered_at"][:10]
        f = OUT.parent / v["file"]
        exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
        if not exists:
            run(["gh", "release", "create", tag, "--title", tag, "--notes", "쇼츠 완성본 (14일 뒤 자동 삭제)", "--latest=false"])
        run(["gh", "release", "upload", tag, str(f), "--clobber"])
        v["download_url"] = f"https://github.com/{repo}/releases/download/{tag}/{f.name}"
    save_history(history)
    cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    tags = run(["gh", "release", "list", "--limit", "100", "--json", "tagName", "-q", ".[].tagName"]).split()
    for t in tags:
        if t.startswith("shorts-") and t[7:] < cutoff:
            subprocess.run(["gh", "release", "delete", t, "--cleanup-tag", "-y"], capture_output=True)
    print(f"릴리스: {len(todo)}편 올림")


def cmd_demo(cfg):
    """API 키 없이 렌더링 경로 전체를 시험한다."""
    from shortsbot.brain import Aside, Line, ShortScript, Sfx, Zoom
    cfg["tts"]["provider"] = "silent"
    clip = OUT / "demo_src.mp4"
    OUT.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=14",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=14", "-shortest", "-pix_fmt", "yuv420p", "-y", str(clip)])
    script = ShortScript(
        scene_summary="테스트 패턴", hook_type="결과형", trim_start=0.5, trim_end=13.5,
        banner_line1="징그러울 정도로", banner_line2="더러운 빗청소ㄷㄷ",
        lines=[Line(start=0.6, text="유튜버가"), Line(start=1.6, text="빗을 보여 주자"),
               Line(start=3.4, text="댓글이 난리가 났는데요"), Line(start=6.0, text="그러자 바로 청소를 시작했는데"),
               Line(start=9.0, text="결국 새 빗으로 갈아탑니다ㅋㅋㅋ")],
        asides=[Aside(start=2.0, end=3.4, text="(빗 뭐야???)", color="yellow"),
                Aside(start=10.0, end=11.6, text="(새거지롱~~)", color="green")],
        sfx=[Sfx(at=2.0, kind="pop"), Sfx(at=6.0, kind="whoosh"), Sfx(at=9.0, kind="sad"), Sfx(at=10.0, kind="tada")],
        zooms=[Zoom(start=2.0, end=3.2, scale=1.18)],
        title="징그러울 정도로 더러운 빗 청소 ㅋㅋㅋ", description="테스트", hashtags=["#shorts"], tags=["빗 청소"], pinned_comment="")
    out = OUT / "demo.mp4"
    length = render(clip, probe(clip), script, cfg, out, credit="@demo")
    print(f"데모 완성: {out} ({length:.1f}초)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["demo", "scout", "fetch", "make", "upload", "daily", "sync", "release"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--id")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "demo":
        cmd_demo(cfg)
    elif a.cmd == "scout":
        from shortsbot.scout import scout
        scout(cfg, a.limit or cfg["channel"]["daily_count"])
    elif a.cmd == "fetch":
        cmd_fetch(cfg)
    elif a.cmd == "make":
        cmd_make(cfg, a.limit or cfg["channel"]["daily_count"], a.id)
    elif a.cmd == "upload":
        cmd_upload(cfg)
    elif a.cmd == "sync":
        cmd_sync(a.path)
    elif a.cmd == "release":
        cmd_release()
    else:
        from shortsbot.scout import scout
        history = load_history()
        count = max(0, (a.limit or cfg["channel"]["daily_count"]) - made_today(history))
        if not count:
            print("오늘 편수를 이미 채움")
            return
        done = {v["id"] for v in history["videos"]}
        waiting = sum(1 for e in load_sources() if e.get("id") not in done and not rights.check(e))
        if waiting < count:
            try:
                scout(cfg, count - waiting)
            except Exception as ex:
                print(f"탐색 실패(계속 진행): {ex}")
        cmd_fetch(cfg)
        cmd_make(cfg, count)
        cmd_upload(cfg)


if __name__ == "__main__":
    main()
