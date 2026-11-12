"""ElevenLabs 로 배경음악(Music API)과 효과음(Sound Effects API)을 만든다. 만든 파일은 state/ 에 저장해 다시 쓴다.
- 배경음악: POST /v1/music {prompt, music_length_ms} — 영상마다 대본의 music_prompt 로(가사 없는 연주곡).
- 효과음: POST /v1/sound-generation {text, duration_seconds} — 종류별(pop·ding·…) 한 번 만들어 계속 쓴다.
키가 없거나 실패하면 None 을 돌려주고, 렌더러는 기존 합성 효과음·assets/bgm 으로 진행한다."""
import hashlib
import json
import urllib.request

from .common import STATE, env

SFX_PROMPTS = {
    "pop": "short cute cartoon pop, bubble pop, clean, no background",
    "ding": "bright notification ding, single bell chime, clean",
    "boom": "deep cinematic boom impact for a funny reveal",
    "sad": "short sad trombone wah wah, comedic fail",
    "tada": "short cheerful fanfare ta-da, success",
    "whoosh": "quick swoosh transition whoosh",
}


def _post(url, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"xi-api-key": env("ELEVENLABS_API_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sfx(kind):
    p = STATE / "sfx" / f"{kind}.mp3"
    if p.exists():
        return p
    if not env("ELEVENLABS_API_KEY") or kind not in SFX_PROMPTS:
        return None
    try:
        audio = _post("https://api.elevenlabs.io/v1/sound-generation",
                      {"text": SFX_PROMPTS[kind], "duration_seconds": 1.0 if kind in ("pop", "ding", "whoosh") else 1.6,
                       "prompt_influence": 0.6})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(audio)
        print(f"  효과음 생성 {kind}")
        return p
    except Exception as ex:
        print(f"  효과음 생성 실패 {kind}: {ex}")
        return None


def bgm(cid, prompt, seconds):
    """영상마다 배경음악 하나. 프롬프트가 같으면 이전 파일을 다시 쓴다."""
    if not prompt:
        return None
    h = hashlib.sha1(f"{prompt}|{round(seconds)}".encode()).hexdigest()[:8]
    p = STATE / "bgm" / f"{cid}-{h}.mp3"
    if p.exists():
        return p
    if not env("ELEVENLABS_API_KEY"):
        return None
    try:
        audio = _post("https://api.elevenlabs.io/v1/music",
                      {"prompt": prompt + ". Instrumental only, no vocals, no lyrics.",
                       "music_length_ms": int(max(10, min(120, seconds)) * 1000), "model_id": "music_v1"})
        p.parent.mkdir(parents=True, exist_ok=True)
        for old in p.parent.glob(f"{cid}-*.mp3"):
            old.unlink()
        p.write_bytes(audio)
        print(f"  배경음악 생성 {cid} ({round(seconds)}초)")
        return p
    except Exception as ex:
        print(f"  배경음악 생성 실패 {cid}: {ex}")
        return None
