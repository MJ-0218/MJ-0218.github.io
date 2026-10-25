"""경로·설정·ffmpeg 공용 도구."""
import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
OUT = ROOT / "out"
STATE = ROOT / "state"
ASSETS = ROOT / "assets"
HISTORY = STATE / "history.json"


def load_config():
    return yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))


def load_sources():
    data = yaml.safe_load((ROOT / "sources.yml").read_text(encoding="utf-8")) or {}
    return data.get("clips") or []


def load_history():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return {"videos": []}


def save_history(h):
    STATE.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} 실패:\n{r.stderr[-3000:]}")
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(info["format"]["duration"]),
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "has_audio": a is not None,
    }


def env(name, default=""):
    return os.environ.get(name, default).strip()
