"""권리 확인. sources.yml 에 권리가 적힌 클립만 통과시킨다."""
from .common import INBOX, load_sources

ALLOWED = {"own", "permission", "licensed", "cc-by"}


def check(entry):
    """문제가 있으면 이유 문자열, 없으면 None."""
    lic = (entry.get("license") or "").strip()
    if lic not in ALLOWED:
        return f"license 가 {sorted(ALLOWED)} 중 하나가 아님: {lic!r}"
    if lic != "own" and not (entry.get("proof") or "").strip():
        return "남의 영상인데 proof(허락·구매 증빙)가 비어 있음"
    if lic == "cc-by" and not (entry.get("credit") or "").strip():
        return "CC BY 는 credit 이 필수"
    return None


def ready_clips():
    """렌더 가능한 클립 목록 [(entry, path)]과 거절 목록 [(id, 이유)]."""
    ok, rejected = [], []
    for e in load_sources():
        cid = e.get("id") or e.get("file") or e.get("url")
        reason = check(e)
        if reason:
            rejected.append((cid, reason))
            continue
        name = e.get("file") or f"{e['id']}.mp4"
        path = INBOX / name
        if not path.exists():
            rejected.append((cid, f"inbox/{name} 파일 없음 (url 이면 fetch 먼저)"))
            continue
        ok.append((e, path))
    return ok, rejected
