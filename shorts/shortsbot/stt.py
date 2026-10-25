"""원본 클립의 말소리를 받아쓴다(ElevenLabs Speech-to-Text). 대사 자막·번역에 쓴다. 실패해도 제작은 계속한다."""
import json
import tempfile
import urllib.request
import uuid
from pathlib import Path

from .common import env, run


def _multipart(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    data = Path(file_path).read_bytes()
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="a.mp3"\r\n'
                 f'Content-Type: audio/mpeg\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def utterances(words, gap=0.6, max_chars=28):
    """단어 목록 → [(시작, 끝, 화자, 문장)]"""
    out, cur = [], None
    for w in words:
        if w.get("type") != "word":
            continue
        spk = w.get("speaker_id") or "s"
        if cur and (w["start"] - cur[1] > gap or spk != cur[2] or len(cur[3]) > max_chars):
            out.append(tuple(cur))
            cur = None
        if cur is None:
            cur = [w["start"], w["end"], spk, w["text"].strip()]
        else:
            cur[1] = w["end"]
            cur[3] += " " + w["text"].strip()
    if cur:
        out.append(tuple(cur))
    return out


def transcribe(clip, cfg):
    """[(시작, 끝, 화자, 원문)] 또는 []"""
    key = env("ELEVENLABS_API_KEY")
    if not key:
        return []
    try:
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "a.mp3"
            run(["ffmpeg", "-v", "error", "-i", str(clip), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", "-y", str(audio)])
            body, ctype = _multipart({"model_id": cfg["stt"]["model_id"], "diarize": "true",
                                      "timestamps_granularity": "word", "tag_audio_events": "true"}, "file", audio)
            req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=body,
                                         headers={"xi-api-key": key, "Content-Type": ctype})
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.loads(r.read())
        return utterances(res.get("words", []))
    except Exception as e:
        print(f"  받아쓰기 실패(대사 자막 없이 진행): {e}")
        return []
