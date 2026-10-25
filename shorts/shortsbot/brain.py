"""클립 프레임을 Claude 가 보고, 화면 사건에 맞춘 대본(JSON)을 쓴다."""
import base64
import tempfile
from pathlib import Path
from typing import List, Literal

import anthropic
from pydantic import BaseModel

from .common import ROOT, run

HookType = Literal["의문형", "소문형", "결과형", "공감형", "숫자형", "비교형", "도전형"]
Color = Literal["yellow", "green", "pink", "red", "cyan"]
SfxKind = Literal["pop", "ding", "whoosh", "boom", "sad", "tada"]


class Line(BaseModel):
    start: float
    text: str


class Aside(BaseModel):
    start: float
    end: float
    text: str
    color: Color


class Sfx(BaseModel):
    at: float
    kind: SfxKind


class Zoom(BaseModel):
    start: float
    end: float
    scale: float


class ShortScript(BaseModel):
    scene_summary: str
    hook_type: HookType
    trim_start: float
    trim_end: float
    banner_line1: str
    banner_line2: str
    lines: List[Line]
    asides: List[Aside]
    sfx: List[Sfx]
    zooms: List[Zoom]
    title: str
    description: str
    hashtags: List[str]
    tags: List[str]
    pinned_comment: str


SYSTEM = """너는 한국 유튜브 쇼츠 편집 작가다. 시청 지속률과 반복 재생을 끌어올리는 짧은 나레이션 대본을 쓴다.
프레임마다 [t=초] 표시가 붙어 있다. 화면에서 실제로 보이는 사건에만 근거해서 쓰고, 보이지 않는 사실(가격·효능·국적·이름)은 지어내지 않는다.
메모(note)가 있으면 사실 정보로 써도 된다.
hashtags 는 설명란 끝에 붙일 3~5개(#포함), tags 는 YouTube 태그 칸에 넣을 검색어 6~12개(# 없이, 한국어 위주, 영어 1~2개)다.
모든 시각(start, end, at)은 원본 클립 기준 초 단위다. trim_start~trim_end 는 쓸 구간이고, 그 밖의 시각은 쓰지 않는다.

아래 스타일 가이드를 따른다.
"""


def extract_frames(path, duration, n, workdir):
    n = max(6, min(n, int(duration * 2)))
    step = duration / n
    frames = []
    for i in range(n):
        t = round(i * step + step / 2, 2)
        out = Path(workdir) / f"f{i:02d}.jpg"
        run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
             "-vf", "scale=384:-2", "-q:v", "4", "-y", str(out)])
        frames.append((t, out))
    return frames


def history_block(history, k=40):
    recent = history["videos"][-k:]
    if not recent:
        return "아직 올린 영상 없음."
    rows = [f"- [{v.get('hook_type')}] {v.get('title')} / 첫 줄: {v.get('first_line')}" for v in recent]
    return "최근 올린 영상(이 제목·첫 줄·구성과 겹치지 않게, 훅 유형도 골고루 돌려 쓸 것):\n" + "\n".join(rows)


def write_script(path, meta, entry, cfg, history, feedback=""):
    style = (ROOT / "prompts" / "style.md").read_text(encoding="utf-8")
    vcfg = cfg["video"]
    with tempfile.TemporaryDirectory() as td:
        frames = extract_frames(path, meta["duration"], cfg["claude"]["max_frames"], td)
        content = []
        for t, f in frames:
            content.append({"type": "text", "text": f"[t={t}]"})
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.standard_b64encode(f.read_bytes()).decode()}})
    brief = [
        f"클립 길이 {meta['duration']:.1f}초, 원본 소리 {'있음' if meta['has_audio'] else '없음'}.",
        f"완성 길이는 {vcfg['min_sec']}~{vcfg['max_sec']}초. 지루한 앞뒤는 trim 으로 잘라라.",
        f"메모: {entry.get('note') or '없음'}",
        history_block(history),
    ]
    if entry.get("credit"):
        brief.append(f"원작자 {entry['credit']} 의 허락을 받은 영상이다. 설명란에 출처로 적는다.")
    if feedback:
        brief.append(f"지난 시도의 문제: {feedback} — 고쳐서 다시 써라.")
    content.append({"type": "text", "text": "\n".join(brief)})

    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=cfg["claude"]["model"],
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": cfg["claude"].get("effort", "medium")},
        system=SYSTEM + style,
        messages=[{"role": "user", "content": content}],
        output_format=ShortScript,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude 가 이 클립의 대본 작성을 거절함 — 클립을 바꿔 주세요")
    return clean(resp.parsed_output, meta["duration"], vcfg)


def clean(s: ShortScript, duration, vcfg):
    """시각을 클립 안으로 맞추고, 너무 긴 자막을 정리한다."""
    s.trim_start = max(0.0, min(s.trim_start, duration - 1))
    s.trim_end = min(duration, max(s.trim_end, s.trim_start + vcfg["min_sec"]))
    if s.trim_end - s.trim_start > vcfg["max_sec"]:
        s.trim_end = s.trim_start + vcfg["max_sec"]
    inside = lambda t: s.trim_start <= t < s.trim_end
    s.lines = sorted([l for l in s.lines if inside(l.start) and l.text.strip()], key=lambda l: l.start)
    s.asides = [a for a in s.asides if inside(a.start)]
    s.sfx = [x for x in s.sfx if inside(x.at)]
    s.zooms = [z for z in s.zooms if inside(z.start) and z.end > z.start]
    for z in s.zooms:
        z.scale = min(1.3, max(1.03, z.scale))
    s.hashtags = [h if h.startswith("#") else "#" + h for h in s.hashtags][:6]
    s.tags = [t.lstrip("#").strip() for t in s.tags if t.strip()][:12]
    if "#shorts" not in [h.lower() for h in s.hashtags]:
        s.hashtags.append("#shorts")
    return s
