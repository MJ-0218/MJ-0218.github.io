"""나레이션 음성 합성. 줄마다 mp3 하나를 만들고 길이를 돌려준다."""
import asyncio
import base64
import json
import urllib.request
from pathlib import Path

from .common import env, probe, run


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def elevenlabs(text, out, cfg):
    c = cfg["tts"]["elevenlabs"]
    voice = env("ELEVENLABS_VOICE_ID") or c["voice_id"]
    if not voice:
        raise RuntimeError("ElevenLabs voice_id 가 없음 (config.yml 또는 ELEVENLABS_VOICE_ID)")
    audio = _post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
        {"text": text, "model_id": c["model_id"], "voice_settings": {
            "stability": c["stability"], "similarity_boost": c["similarity_boost"],
            "style": c["style"], "speed": min(1.2, cfg["tts"]["speed"])}},
        {"xi-api-key": env("ELEVENLABS_API_KEY")})
    Path(out).write_bytes(audio)


def google(text, out, cfg):
    data = json.loads(_post(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={env('GOOGLE_TTS_API_KEY')}",
        {"input": {"text": text},
         "voice": {"languageCode": "ko-KR", "name": cfg["tts"]["google"]["voice"]},
         "audioConfig": {"audioEncoding": "MP3", "speakingRate": cfg["tts"]["speed"]}}, {}))
    Path(out).write_bytes(base64.b64decode(data["audioContent"]))


def edge(text, out, cfg):
    import edge_tts  # 비공식 엔드포인트 — 미리보기 전용
    rate = f"+{round((cfg['tts']['speed'] - 1) * 100)}%"
    asyncio.run(edge_tts.Communicate(text, cfg["tts"]["edge"]["voice"], rate=rate).save(str(out)))


def silent(text, out, cfg):
    """테스트용: 글자 수에 맞춘 무음."""
    sec = max(0.6, len(text) * 0.13 / cfg["tts"]["speed"])
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{sec:.2f}", "-y", str(out)])


PROVIDERS = {"elevenlabs": elevenlabs, "google": google, "edge": edge, "silent": silent}


def speak(lines, workdir, cfg):
    """[(start, text)] → [(start, path, 길이)]"""
    fn = PROVIDERS[cfg["tts"]["provider"]]
    out = []
    for i, line in enumerate(lines):
        p = Path(workdir) / f"tts{i:02d}.mp3"
        spoken = line.text.replace("ㄷㄷ", "").replace("ㅋ", "").replace("??", "?").strip() or line.text
        fn(spoken, p, cfg)
        out.append((line.start, p, probe(p)["duration"]))
    return out
