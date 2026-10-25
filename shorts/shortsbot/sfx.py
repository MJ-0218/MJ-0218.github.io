"""효과음을 수식으로 직접 합성한다(저작권 걱정 없음). assets/sfx/<이름>.wav 가 있으면 그 파일을 우선 쓴다."""
from .common import ASSETS, run

RECIPES = {
    "pop": "aevalsrc='0.8*sin(2*PI*(500+3500*t)*t)*exp(-38*t)':d=0.14",
    "ding": "aevalsrc='0.6*sin(2*PI*1320*t)*exp(-6*t)+0.3*sin(2*PI*2640*t)*exp(-9*t)':d=0.7",
    "boom": "aevalsrc='0.9*sin(2*PI*(55+70*exp(-9*t))*t)*exp(-3.5*t)':d=0.9",
    "sad": "aevalsrc='0.5*sin(2*PI*(392-140*t)*t)*exp(-1.6*t)':d=1.1",
    "tada": ("aevalsrc='0.4*sin(2*PI*523*t)*exp(-3*t)"
             "+0.4*sin(2*PI*659*t)*exp(-3*(t-0.1))*gt(t,0.1)"
             "+0.4*sin(2*PI*784*t)*exp(-3*(t-0.2))*gt(t,0.2)':d=1.0"),
    "whoosh": "anoisesrc=d=0.45:c=pink:a=0.6,bandpass=f=1800:width_type=o:w=2,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.25",
}


def path(kind):
    d = ASSETS / "sfx"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{kind}.wav"
    if not p.exists():
        run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", RECIPES[kind], "-ar", "44100", "-ac", "1", "-y", str(p)])
    return p
