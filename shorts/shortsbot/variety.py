"""반복·템플릿 판정을 피하기 위한 다양성 검사. 최근 영상과 문장이 비슷하면 다시 쓰게 한다."""


def grams(text, n=3):
    t = "".join(text.split())
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def similarity(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def check(script, history, k=60, max_sim=0.35, max_same_hook=3):
    """문제가 있으면 이유, 없으면 None."""
    narr = " ".join(l.text for l in script.lines)
    recent = history["videos"][-k:]
    for v in recent:
        sim = similarity(narr, v.get("narration", ""))
        if sim > max_sim:
            return f"나레이션이 '{v.get('title')}' 와 {sim:.0%} 겹침 — 다른 문장·전개로"
        if similarity(script.title, v.get("title", "")) > 0.6:
            return f"제목이 '{v.get('title')}' 와 너무 비슷함"
    last = [v.get("hook_type") for v in recent[-max_same_hook:]]
    if len(last) == max_same_hook and all(h == script.hook_type for h in last):
        return f"최근 {max_same_hook}편 연속 {script.hook_type} — 다른 훅 유형으로"
    if not script.lines:
        return "나레이션이 비어 있음"
    return None
