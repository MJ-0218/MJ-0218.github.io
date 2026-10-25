"""대본 + 음성 + 원본 클립 → 1080x1920 완성본(mp4)."""
import random
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


def render(clip, meta, script, cfg, out_path, credit=""):
    vcfg, st = cfg["video"], cfg["style"]
    tcfg = cfg["templates"][script.template]
    t0, t1 = script.trim_start, script.trim_end
    clip_len = t1 - t0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spoken = tts.speak(script.lines, td, cfg)
        placed = place_narration(spoken, t0)
        end = min(max(clip_len, placed[-1][1] + 0.5), vcfg["max_sec"] + 8)
        freeze = max(0.0, end - clip_len)

        s = shifted(script, t0)
        for d in s.dialogue:
            d.start, d.end = d.start - t0, d.end - t0
        for m in s.marks:
            m.start, m.end = m.start - t0, m.end - t0
        landscape = meta["width"] / max(1, meta["height"]) > 0.7
        # 자막은 다음 줄이 나올 때까지(최대 1.5초 더) 남겨 화면이 비지 않게 한다
        timeline = []
        for i, ((a, b, _), l) in enumerate(zip(placed, script.lines)):
            nxt = placed[i + 1][0] if i + 1 < len(placed) else end
            timeline.append((a, min(nxt, b + 1.5), l.text))
        ass = td / "subs.ass"
        colors = {"line1_color": tcfg["line1_color"], "line2_color": tcfg["line2_color"]}
        ass.write_text(subs.build(s, timeline, end, st, credit, colors, mark_pixels(s.marks, meta, landscape)),
                       encoding="utf-8")

        inputs = ["-ss", f"{t0:.2f}", "-t", f"{clip_len:.2f}", "-i", str(clip)]
        n = 1
        vf = []
        if landscape:  # 가로·정사각 영상: 흐린 배경 위에 원본
            vf.append("[0:v]split[bg][fg];"
                      "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bgb];"
                      "[fg]scale=1080:-2[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2+80[base]")
        else:
            vf.append("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base]")
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
