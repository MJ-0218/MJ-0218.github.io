"""대본 + 음성 + 원본 클립 → 1080x1920 완성본(mp4)."""
import random
import json
import tempfile
from pathlib import Path

from . import sfx, subs, tts
from .common import ASSETS, run


def place_narration(spoken, t0):
    """음성이 겹치지 않게 배치. [(시작, 끝, 경로)]"""
    cursor, placed = 0.0, []
    for start, path, dur in spoken:
        s = max(start - t0, cursor)
        placed.append((s, s + dur, path))
        cursor = s + dur + 0.06
    return placed


def fit_to_slots(spoken, t0, workdir, max_tempo=1.4):
    """줄이 실제로 시작하는 시각(앞줄에 밀린 것까지)부터 다음 줄 계획 시각 안에 끝나도록 그 줄만 빠르게(atempo).
    밀림이 쌓여 이전 문장이 다음 장면 위에 뜨는 걸 막는다."""
    out, cursor = [], 0.0
    for i, (start, path, dur) in enumerate(spoken):
        actual = max(start, cursor)
        if i + 1 < len(spoken):
            window = spoken[i + 1][0] - actual - 0.15
            if window > 0.3 and dur > window:
                tempo = min(max_tempo, dur / window)
                fast = Path(workdir) / f"fit{i:02d}.mp3"
                run(["ffmpeg", "-v", "error", "-i", str(path), "-filter:a", f"atempo={tempo:.3f}", "-y", str(fast)])
                path, dur = fast, dur / tempo
        out.append((start, path, dur))
        cursor = actual + dur + 0.06
    return out


def scene_cuts(clip, t0, t1, thresh=0.3):
    """원본 클립의 장면 전환 시각(편집 기준, 초). 자막이 다음 장면으로 넘어가지 않게 쓴다."""
    import re
    import subprocess
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{t0:.2f}", "-t", f"{t1 - t0:.2f}", "-i", str(clip), "-vf",
                        f"select='gt(scene,{thresh})',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def zoom_expr(zooms):
    if not zooms:
        return None
    terms = "+".join(f"{z.scale - 1:.3f}*between(it,{z.start:.2f},{z.end:.2f})" for z in zooms)
    return f"1+{terms}"


def shifted(script, t0):
    s = script.model_copy(deep=True)
    for a in s.asides:
        a.start, a.end = a.start - t0, a.end - t0
    for x in s.sfx:
        x.at -= t0
    for z in s.zooms:
        z.start, z.end = z.start - t0, z.end - t0
    return s


def mark_pixels(marks, meta, landscape):
    """프레임 기준 0~1 위치 → 1080x1920 화면 픽셀."""
    w, h = max(1, meta["width"]), max(1, meta["height"])
    out = []
    for m in marks:
        if landscape:
            fh = h * 1080 / w
            x, y = m.x * 1080, (1920 - fh) / 2 + 80 + m.y * fh
        else:
            sc = max(1080 / w, 1920 / h)
            x = m.x * w * sc - (w * sc - 1080) / 2
            y = m.y * h * sc - (h * sc - 1920) / 2
        out.append((m.start, m.end, int(min(1040, max(40, x))), int(min(1880, max(360, y))), m.kind))
    return out


def pick_bgm():
    files = sorted((ASSETS / "bgm").glob("*.mp3")) + sorted((ASSETS / "bgm").glob("*.m4a"))
    return random.choice(files) if files else None


def render(clip, meta, script, cfg, out_path, credit="", cut=(0.0, 0.0), blur_band=None):
    """cut=(위, 아래): 원본 화면에서 잘라 낼 비율(0~0.35). 원본에 박힌 외국어 자막 띠를 없앨 때 쓴다."""
    vcfg, st = cfg["video"], cfg["style"]
    ct, cb = (max(0.0, min(0.35, float(x or 0))) for x in cut)
    pre = ""
    if ct or cb:
        top = int(meta["height"] * ct)
        meta = dict(meta, height=int(meta["height"] * (1 - ct - cb)) // 2 * 2)
        pre = f"crop=iw:{meta['height']}:0:{top},"
    src = "[0:v]"
    head = ""
    if blur_band:  # 원본 가운데에 박힌 글씨 띠(세로 비율 y0~y1)를 흐리게 가린다
        y0, y1 = (max(0.0, min(1.0, float(x))) for x in blur_band)
        if y1 > y0:
            h0, hb = int(meta["height"] * y0) // 2 * 2, max(2, int(meta["height"] * (y1 - y0)) // 2 * 2)
            head = (f"[0:v]{pre}split[o][m];[m]crop=iw:{hb}:0:{h0},boxblur=28:4,eq=brightness=-0.12[mb];"
                    f"[o][mb]overlay=0:{h0}[src];")
            src, pre = "[src]", ""
    tcfg = cfg["templates"][script.template]
    t0, t1 = script.trim_start, script.trim_end
    clip_len = t1 - t0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spoken = fit_to_slots(tts.speak(script.lines, td, cfg), t0, td)
        placed = place_narration(spoken, t0)
        # 실제로 뜬 시각 기록 — 검수 시트가 계획 시각이 아니라 실제 시각으로 화면을 뽑는다
        Path(out_path).with_suffix(".timing.json").write_text(json.dumps(
            [{"text": l.text, "planned": round(l.start - t0, 2), "placed": round(a, 2), "drift": round(a - (l.start - t0), 2)}
             for (a, _b, _p), l in zip(placed, script.lines)], ensure_ascii=False, indent=1), encoding="utf-8")
        end = min(max(clip_len, placed[-1][1] + 0.5), vcfg["max_sec"] + 8)
        freeze = max(0.0, end - clip_len)

        s = shifted(script, t0)
        for d in s.dialogue:
            d.start, d.end = d.start - t0, d.end - t0
        for m in s.marks:
            m.start, m.end = m.start - t0, m.end - t0
        landscape = meta["width"] / max(1, meta["height"]) > 0.7
        # 자막은 다음 줄이 나올 때까지(최대 1.5초 더) 남겨 화면이 비지 않게 한다
        timeline, crossings = [], []
        cuts = scene_cuts(clip, t0, t1)
        for i, ((a, b, _), l) in enumerate(zip(placed, script.lines)):
            nxt = placed[i + 1][0] if i + 1 < len(placed) else end
            nxt_plan = script.lines[i + 1].start - t0 - 0.05 if i + 1 < len(script.lines) else end
            e = min(nxt, nxt_plan, b + tcfg.get("linger", 1.5))
            cut = next((c for c in cuts if c > a + 0.4), None)
            if cut is not None and e > cut:  # 음성이 장면 전환 전에 끝나면 자막도 전환에서 끊는다
                e = max(b, cut - 0.03) if b <= cut else b
                if b > cut + 0.3:
                    crossings.append({"text": l.text, "cut": round(cut, 2), "audio_end": round(b, 2)})
            timeline.append((a, max(a + 0.5, min(e, nxt)), l.text))
        Path(out_path).with_suffix(".cuts.json").write_text(json.dumps(
            {"cuts": [round(c, 2) for c in cuts], "crossings": crossings}, ensure_ascii=False), encoding="utf-8")
        ass = td / "subs.ass"
        colors = {"line1_color": tcfg["line1_color"], "line2_color": tcfg["line2_color"]}
        ass.write_text(subs.build(s, timeline, end, st, credit, colors, mark_pixels(s.marks, meta, landscape)),
                       encoding="utf-8")

        inputs = ["-ss", f"{t0:.2f}", "-t", f"{clip_len:.2f}", "-i", str(clip)]
        n = 1
        vf = []
        if landscape:  # 가로·정사각 영상: 흐린 배경 위에 원본
            vf.append(head + f"{src}{pre}split[bg][fg];"
                      "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bgb];"
                      "[fg]scale=1080:-2[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2+80[base]")
        else:
            vf.append(head + f"{src}{pre}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base]")
        chain = "[base]setsar=1,fps=30"
        z = zoom_expr(s.zooms)
        if z:
            chain += f",zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
        if freeze > 0:
            chain += f",tpad=stop_mode=clone:stop_duration={freeze:.2f}"
        bh = st["banner_height"]
        chain += f",drawbox=x=0:y=0:w=iw:h={bh}:color=0x{st['banner_color']}@1:t=fill"
        if st.get("accent_bar"):
            chain += f",drawbox=x=0:y={bh}:w=iw:h=8:color=0x{st['accent_bar']}@1:t=fill"
        fontsdir = (ASSETS / "fonts").as_posix()
        chain += f",ass='{ass.as_posix()}':fontsdir='{fontsdir}',format=yuv420p[v]"
        vf.append(chain)

        mix = []
        if meta["has_audio"]:
            # 나레이션이 나오는 동안만 원본 소리를 낮춘다(틀 B 는 평소 원본 소리가 주인공)
            base = tcfg["original_audio"]
            duck = min(base, 0.22)
            during = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b, _ in placed) or "0"
            mix.append(f"[0:a]volume='if({during},{duck},{base})':eval=frame,apad[orig]")
            labels = ["[orig]"]
        else:
            labels = []
        for i, (a, _, p) in enumerate(placed):
            inputs += ["-i", str(p)]
            mix.append(f"[{n}:a]aresample=44100,adelay={int(a * 1000)}:all=1[n{i}]")
            labels.append(f"[n{i}]")
            n += 1
        for i, x in enumerate(s.sfx):
            inputs += ["-i", str(sfx.path(x.kind))]
            mix.append(f"[{n}:a]aresample=44100,volume={vcfg['sfx_volume']},adelay={int(max(0, x.at) * 1000)}:all=1[s{i}]")
            labels.append(f"[s{i}]")
            n += 1
        bgm = pick_bgm()
        if bgm:
            inputs += ["-stream_loop", "-1", "-i", str(bgm)]
            mix.append(f"[{n}:a]aresample=44100,volume={vcfg['bgm_volume']},afade=t=out:st={max(0, end - 1.2):.2f}:d=1.2[bgm]")
            labels.append("[bgm]")
            n += 1
        if not labels:
            mix.append("anullsrc=r=44100:cl=stereo[sil]")
            labels.append("[sil]")
        mix.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
                   f"atrim=0:{end:.2f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[a]")

        graph = ";".join(vf + mix)
        run(["ffmpeg", "-v", "error", *inputs, "-filter_complex", graph,
             "-map", "[v]", "-map", "[a]", "-t", f"{end:.2f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-y", str(out_path)])
    return end
