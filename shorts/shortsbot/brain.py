"""클립 프레임을 Claude 가 보고, 화면 사건에 맞춘 대본(JSON)을 쓴다."""
import base64
import tempfile
from pathlib import Path
from typing import List, Literal

import anthropic
from pydantic import BaseModel

from .common import ROOT, run

Template = Literal["story", "clip"]
MarkKind = Literal["circle", "arrow"]
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


class Dialogue(BaseModel):
    """화면 속 사람 말 — 따옴표 자막(외국어면 한국어로 옮긴다)."""
    start: float
    end: float
    text: str
    color: Color


class Mark(BaseModel):
    """핵심 사물·인물 강조. x, y 는 프레임 기준 0~1 위치."""
    start: float
    end: float
    x: float
    y: float
    kind: MarkKind


class ShortScript(BaseModel):
    scene_summary: str
    template: Template
    hook_type: HookType
    trim_start: float
    trim_end: float
    banner_line1: str
    banner_line2: str
    lines: List[Line]
    asides: List[Aside]
    sfx: List[Sfx]
    zooms: List[Zoom]
    dialogue: List[Dialogue]
    marks: List[Mark]
    ending_caption: str
    title: str
    description: str
    hashtags: List[str]
    tags: List[str]
    pinned_comment: str


SYSTEM = """너는 한국 유튜브 쇼츠 편집 작가다. 시청 지속률과 반복 재생을 끌어올리는 짧은 나레이션 대본을 쓴다.
프레임마다 [t=초] 표시가 붙어 있다. 화면에서 실제로 보이는 사건에만 근거해서 쓰고, 보이지 않는 사실(가격·효능·국적·이름)은 지어내지 않는다.
메모(note)가 있으면 사실 정보로 써도 된다.
template 은 스타일 가이드의 틀 A(story)·틀 B(clip) 중 클립에 맞는 것을 고른다. clip 이면 lines 는 첫 줄 하나(최대 두 줄)만 쓰고, 나머지는 dialogue 와 asides 로 끌고 간다.
dialogue 는 받아쓰기 원문이 있을 때 그 시각에 맞춰 쓴다(외국어는 자연스러운 한국어 구어로 옮기고, 한국어는 그대로 다듬는다). 원문이 없으면 비워 둔다.
marks 는 0~2초의 핵심 사물·인물 1개(필요하면 반전 순간 1개 더)에 원(circle) 또는 화살표(arrow). x, y 는 해당 프레임에서 그 대상 중심의 위치(가로·세로 0~1).
ending_caption 은 마지막 1.5초에 띄울 댓글 유도 질문 한 줄(25자 이내).
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


def transcript_block(lines):
    if not lines:
        return "받아쓰기: 없음(원본에 말소리가 없거나 받아쓰기 실패)."
    rows = [f"[{a:.1f}-{b:.1f}] {spk}: {text}" for a, b, spk, text in lines]
    return "받아쓰기(원본 말소리, 화자별):\n" + "\n".join(rows)


def write_script(path, meta, entry, cfg, history, feedback="", transcript=()):
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
        f"완성 길이: story 면 {cfg['templates']['story']['min_sec']}~{cfg['templates']['story']['max_sec']}초, "
        f"clip 이면 {cfg['templates']['clip']['min_sec']}~{cfg['templates']['clip']['max_sec']}초. 지루한 앞뒤는 trim 으로 잘라라.",
        transcript_block(transcript),
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
    s = resp.parsed_output
    return clean(s, meta["duration"], {**vcfg, **cfg["templates"][s.template]})


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
    s.dialogue = sorted([d for d in s.dialogue if inside(d.start) and d.text.strip()], key=lambda d: d.start)
    s.marks = [m for m in s.marks if inside(m.start)][:3]
    for m in s.marks:
        m.x, m.y = min(0.95, max(0.05, m.x)), min(0.95, max(0.05, m.y))
        m.end = min(max(m.end, m.start + 0.6), m.start + 2.5)
    if s.template == "clip":
        s.lines = s.lines[:2]
    for z in s.zooms:
        z.scale = min(1.3, max(1.03, z.scale))
    s.hashtags = [h if h.startswith("#") else "#" + h for h in s.hashtags][:6]
    s.tags = [t.lstrip("#").strip() for t in s.tags if t.strip()][:12]
    if "#shorts" not in [h.lower() for h in s.hashtags]:
        s.hashtags.append("#shorts")
    return s
