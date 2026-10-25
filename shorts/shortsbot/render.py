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


def pick_bgm():
    files = sorted((ASSETS / "bgm").glob("*.mp3")) + sorted((ASSETS / "bgm").glob("*.m4a"))
    return random.choice(files) if files else None


def render(clip, meta, script, cfg, out_path, credit=""):
    vcfg, st = cfg["video"], cfg["style"]
    t0, t1 = script.trim_start, script.trim_end
    clip_len = t1 - t0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spoken = tts.speak(script.lines, td, cfg)
        placed = place_narration(spoken, t0)
        end = min(max(clip_len, placed[-1][1] + 0.5), vcfg["max_sec"] + 8)
        freeze = max(0.0, end - clip_len)

        s = shifted(script, t0)
        # 자막은 다음 줄이 나올 때까지(최대 1.5초 더) 남겨 화면이 비지 않게 한다
        timeline = []
        for i, ((a, b, _), l) in enumerate(zip(placed, script.lines)):
            nxt = placed[i + 1][0] if i + 1 < len(placed) else end
            timeline.append((a, min(nxt, b + 1.5), l.text))
        ass = td / "subs.ass"
        ass.write_text(subs.build(s, timeline, end, st, credit), encoding="utf-8")

        inputs = ["-ss", f"{t0:.2f}", "-t", f"{clip_len:.2f}", "-i", str(clip)]
        n = 1
        vf = []
        landscape = meta["width"] / max(1, meta["height"]) > 0.7
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
            mix.append(f"[0:a]volume={vcfg['original_audio']},apad[orig]")
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
