"""쇼츠 자동화 실행기.

  python shorts/run.py demo              # 키 없이 렌더링만 시험 (가짜 클립·무음 나레이션)
  python shorts/run.py scout             # CC BY 인기 쇼츠 자동 탐색·등록 + 허락 요청 후보 목록
  python shorts/run.py fetch             # sources.yml 의 url(허락·구매 증빙 있는 것만) → inbox/
  python shorts/run.py make [--limit N]  # 클립 → 대본 → 음성 → 완성본 (out/)
  python shorts/run.py upload            # 완성본을 다음 업로드 시각에 예약
  python shorts/run.py daily             # scout + fetch + make(daily_count) + upload
  python shorts/run.py social-import <f> # 인스타·틱톡 급상승 클립(vidIQ, 세션이 JSON 으로 옮김) → 허가 대기 후보
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

from shortsbot import brain, rights, stt, variety  # noqa: E402
from shortsbot.common import INBOX, OUT, STATE, load_config, load_history, load_sources, probe, run, save_history  # noqa: E402
from shortsbot.render import render  # noqa: E402


PLATFORM = {"instagram": "인스타그램", "tiktok": "틱톡", "xiaohongshu": "샤오홍슈", "youtube": "유튜브"}
HOW = {"cc-by": "CC BY 라이선스에 따라 출처를 밝히고 사용했습니다.",
       "permission": "원작자의 허락을 받고 사용했습니다.",
       "licensed": "라이선스를 구매해 사용했습니다."}


def platform_of(entry):
    if entry.get("platform"):
        return entry["platform"]
    url = entry.get("url", "")
    return next((k for k in PLATFORM if k in url or (k == "youtube" and "youtu" in url)), "")


def credit_label(entry):
    """영상 화면 아래쪽에 계속 띄우는 출처 한 줄."""
    if not entry.get("credit"):
        return ""
    pl = PLATFORM.get(platform_of(entry), "")
    return f"{entry['credit']} ({pl})" if pl else entry["credit"]


def credit_block(entry):
    """설명란 맨 아래 출처 묶음 — 원작자 계정, 계정 링크, 원본 링크, 사용 근거."""
    if not entry.get("credit") or entry.get("license") == "own":
        return ""
    rows = ["", "", "──────────", "[출처]", f"원작자: {entry['credit']}" + (f" ({PLATFORM[platform_of(entry)]})" if platform_of(entry) else "")]
    if entry.get("credit_url"):
        rows.append(f"원작자 계정: {entry['credit_url']}")
    if entry.get("url"):
        rows.append(f"원본 영상: {entry['url']}")
    rows.append(HOW.get(entry.get("license"), ""))
    return "\n".join(r for r in rows if r is not None)


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


def review_sheet(mp4, out_jpg, n=12):
    """완성본에서 고르게 n장(시각 표시)을 뽑아 한 장으로 — 세션이 검수 2회에 쓴다."""
    import tempfile
    d = probe(mp4)["duration"]
    times = [round(0.3 + i * (d - 0.8) / (n - 1), 1) for i in range(n)]
    Path(out_jpg).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        for k, t in enumerate(times):
            run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4), "-frames:v", "1", "-vf",
                 f"scale=270:-2,drawtext=text='{t:.1f}s':x=6:y=h-30:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6",
                 "-y", f"{td}/f{k:02d}.png"])
        run(["ffmpeg", "-v", "error", "-i", f"{td}/f%02d.png", "-vf", f"tile=6x{(n + 5) // 6}",
             "-frames:v", "1", "-q:v", "4", "-y", str(out_jpg)])
    return times


FONT_FILES = {"banner": "BlackHanSans-Regular.ttf", "sub": "Pretendard-Black.otf"}


def missing_glyphs(script):
    """배너(Black Han Sans)·자막(Pretendard) 글꼴에 없는 글자 — 화면에서 빈칸으로 빠진다(예: '얔')."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return []
    fonts = Path(__file__).resolve().parent / "assets" / "fonts"
    cm = {k: set(TTFont(fonts / f).getBestCmap()) for k, f in FONT_FILES.items() if (fonts / f).exists()}
    texts = {"banner": [script.banner_line1, script.banner_line2],
             "sub": [l.text for l in script.lines] + [a.text for a in script.asides] + [d.text for d in script.dialogue]
             + [script.ending_caption]}
    bad = []
    for k, arr in texts.items():
        if k not in cm:
            continue
        for t in arr:
            bad += [f"{k}:{ch}" for ch in t if not ch.isspace() and ord(ch) not in cm[k] and ord(ch) > 0x2000]
    return sorted(set(bad))


def cmd_review(vid, pas, verdict, note):
    """검수 기록. 서로 다른 관점의 검수 2회(1: 내용·사실·자막 시점, 2: 화면 이상)가 모두 ok 여야 '검수 통과'."""
    history = load_history()
    v = next((x for x in history["videos"] if x["id"] == vid), None)
    if not v:
        sys.exit(f"{vid} 가 history 에 없음")
    rv = [r for r in v.get("review", []) if r["pass"] != pas]
    rv.append({"pass": pas, "verdict": verdict, "note": note, "at": dt.datetime.now().isoformat(timespec="seconds")})
    v["review"] = sorted(rv, key=lambda r: r["pass"])
    ok = {r["pass"] for r in v["review"] if r["verdict"] == "ok"}
    v["status"] = "검수 통과" if {1, 2} <= ok else ("다시 만들기" if verdict == "fix" else "검수 대기")
    save_history(history)
    log = STATE / "review" / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        rec = next(r for r in v["review"] if r["pass"] == pas)
        f.write(json.dumps({"id": vid, **rec}, ensure_ascii=False) + "\n")
    print(f"{vid}: {pas}차 {verdict} → {v['status']}")


def cmd_remake(vid):
    """대본(scripts/<id>.json)을 고친 뒤 다시 만들도록 history 에서 뺀다."""
    history = load_history()
    history["videos"] = [x for x in history["videos"] if x["id"] != vid]
    save_history(history)
    print(f"{vid}: 다음 제작 때 다시 만듦")


def cmd_frames(cfg, n=16):
    """아직 안 만든 클립의 장면 사진·길이·받아쓰기를 state/frames/<id>/ 에 남긴다 — 세션이 보고 대본(scripts/<id>.json)을 쓴다."""
    from shortsbot.brain import extract_frames
    done = {v["id"] for v in load_history()["videos"]}
    for e in load_sources():
        cid = e.get("id")
        path = INBOX / (e.get("file") or f"{cid}.mp4")
        if cid in done or not path.exists() or rights.check(e):
            continue
        d = STATE / "frames" / cid
        if (d / "meta.json").exists():
            continue
        d.mkdir(parents=True, exist_ok=True)
        meta = probe(path)
        for t, f in extract_frames(path, meta["duration"], n, d):
            f.rename(d / f"t{t:05.1f}.jpg")
        try:
            transcript = stt.transcribe(path, cfg) if meta["has_audio"] else []
        except Exception as ex:
            transcript = []
            print(f"  받아쓰기 실패 {cid}: {ex}")
        (d / "meta.json").write_text(json.dumps({"meta": meta, "transcript": transcript, "note": e.get("note", ""),
                                                 "credit": e.get("credit", "")}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"장면 사진 {cid}: {meta['duration']:.1f}초")


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
            transcript = stt.transcribe(path, cfg) if meta["has_audio"] else []
            feedback, script = "", None
            for attempt in range(3):
                script = brain.write_script(path, meta, entry, cfg, history, feedback, transcript)
                feedback = variety.check(script, history)
                if not feedback:
                    break
                print(f"  {cid} 다시 쓰기({attempt + 1}): {feedback}")
            if feedback:
                print(f"실패 {cid}: 다양성 검사 통과 못 함 — {feedback}")
                continue
            bad = missing_glyphs(script)
            if bad:
                print(f"실패 {cid}: 글꼴에 없는 글자 {bad} — 대본(scripts/{cid}.json)에서 바꿔 주세요")
                continue
            out = day / f"{cid}.mp4"
            length = render(path, meta, script, cfg, out, credit=credit_label(entry),
                            cut=(entry.get("cut_top", 0), entry.get("cut_bottom", 0)), blur_band=entry.get("blur_band"))
            posters = STATE / "posters"
            posters.mkdir(parents=True, exist_ok=True)
            run(["ffmpeg", "-v", "error", "-ss", "1.5", "-i", str(out), "-frames:v", "1", "-vf", "scale=216:-2",
                 "-q:v", "5", "-y", str(posters / f"{cid}.jpg")])
            desc = script.description.strip() + "\n\n" + " ".join(script.hashtags) + credit_block(entry)
            item = {
                "id": cid, "url": entry.get("url", ""), "file": str(out.relative_to(OUT.parent)), "length": round(length, 1),
                "title": script.title, "description": desc, "hashtags": script.hashtags, "tags": script.tags,
                "hook_type": script.hook_type, "first_line": script.lines[0].text,
                "narration": " ".join(l.text for l in script.lines),
                "pinned_comment": script.pinned_comment,
                "rendered_at": dt.datetime.now().isoformat(timespec="seconds"),
                "status": "검수 대기", "review": [],
            }
            review_sheet(out, STATE / "review" / f"{cid}.jpg")
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
    pending = [v for v in history["videos"] if not v.get("video_id") and v.get("status") == "검수 통과"
               and (OUT.parent / v["file"]).exists()]
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
                "id": (c['video_id'] if c.get('platform') else f"yt-{c['video_id']}"), "url": c["url"], "license": "permission",
                "proof": f"대기판에서 사용자가 허가 확인 {a.get('at', '')}: {a.get('note', '')}".strip(),
                "credit": c["channel"], "platform": c.get("platform", "youtube"),
                "credit_url": c.get("channel_url") or (f"https://www.youtube.com/channel/{c['channel_id']}" if c.get("channel_id") else ""),
                **({"cut_top": c["cut_top"]} if c.get("cut_top") else {}),
                **({"cut_bottom": c["cut_bottom"]} if c.get("cut_bottom") else {}),
                **({"blur_band": c["blur_band"]} if c.get("blur_band") else {}),
                "note": f"원제: {c['title']} / {c.get('desc', '')[:150]}".replace("\n", " "),
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


def cmd_demo(cfg, template="story"):
    """API 키 없이 렌더링 경로 전체를 시험한다."""
    from shortsbot.brain import Aside, Dialogue, Line, Mark, ShortScript, Sfx, Zoom
    cfg["tts"]["provider"] = "silent"
    clip = OUT / "demo_src.mp4"
    OUT.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=14",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=14", "-shortest", "-pix_fmt", "yuv420p", "-y", str(clip)])
    script = ShortScript(
        scene_summary="테스트 패턴", template=template, hook_type="결과형", trim_start=0.5, trim_end=13.5,
        banner_line1="징그러울 정도로", banner_line2="더러운 빗청소ㄷㄷ",
        lines=[Line(start=0.6, text="유튜버가"), Line(start=1.6, text="빗을 보여 주자"),
               Line(start=3.4, text="댓글이 난리가 났는데요"), Line(start=6.0, text="그러자 바로 청소를 시작했는데"),
               Line(start=9.0, text="결국 새 빗으로 갈아탑니다ㅋㅋㅋ")],
        asides=[Aside(start=2.0, end=3.4, text="(빗 뭐야???)", color="yellow"),
                Aside(start=10.0, end=11.6, text="(새거지롱~~)", color="green")],
        sfx=[Sfx(at=2.0, kind="pop"), Sfx(at=6.0, kind="whoosh"), Sfx(at=9.0, kind="sad"), Sfx(at=10.0, kind="tada")],
        zooms=[Zoom(start=2.0, end=3.2, scale=1.18)],
        dialogue=[Dialogue(start=7.0, end=8.6, text="이거 청소가 되긴 할까요?", color="green")],
        marks=[Mark(start=0.6, end=2.2, x=0.5, y=0.45, kind="circle"), Mark(start=9.2, end=10.6, x=0.3, y=0.6, kind="arrow")],
        ending_caption="여러분은 빗 몇 년째 쓰세요?",
        title="징그러울 정도로 더러운 빗 청소 ㅋㅋㅋ", description="테스트", hashtags=["#shorts"], tags=["빗 청소"], pinned_comment="")
    if template == "clip":
        script.lines = script.lines[:1]
    out = OUT / f"demo_{template}.mp4"
    length = render(clip, probe(clip), script, cfg, out, credit="@demo")
    print(f"데모 완성: {out} ({length:.1f}초)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["demo", "scout", "fetch", "make", "upload", "daily", "sync", "release", "social-import", "frames", "review", "remake", "sheet"])
    ap.add_argument("--pass", dest="pas", type=int)
    ap.add_argument("--verdict", choices=["ok", "fix"])
    ap.add_argument("--note", default="")
    ap.add_argument("path", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--id")
    a = ap.parse_args()
    cfg = load_config()
    if a.cmd == "demo":
        cmd_demo(cfg, a.path or "story")
    elif a.cmd == "scout":
        from shortsbot.scout import scout
        scout(cfg, a.limit or cfg["channel"]["daily_count"])
    elif a.cmd == "fetch":
        cmd_fetch(cfg)
    elif a.cmd == "review":
        cmd_review(a.path, a.pas, a.verdict, a.note)
    elif a.cmd == "remake":
        cmd_remake(a.path)
    elif a.cmd == "sheet":
        print(review_sheet(a.path, a.out))
    elif a.cmd == "frames":
        cmd_fetch(cfg)
        cmd_frames(cfg)
    elif a.cmd == "make":
        cmd_make(cfg, a.limit or cfg["channel"]["daily_count"], a.id)
    elif a.cmd == "upload":
        cmd_upload(cfg)
    elif a.cmd == "sync":
        cmd_sync(a.path)
    elif a.cmd == "release":
        cmd_release()
    elif a.cmd == "social-import":
        from shortsbot.social import import_items
        import_items(json.loads(Path(a.path).read_text(encoding="utf-8")))
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
