#!/usr/bin/env python3
"""초안 문체·품질 검사기.

사람이 다듬은 글과 'AI가 찍어낸 글'을 가르는 표시들을 기계적으로 잡아낸다.
- FAIL: 반드시 고쳐야 발행 가능 (가짜 체험담, 출처 부족, 금지 상투어 등)
- WARN: 리듬·구성 문제. 고치는 걸 권장

사용: python3 automation/scripts/style_check.py _drafts/파일.md [--json]
종료 코드: FAIL 이 하나라도 있으면 1
"""
import json
import re
import statistics
import sys
from pathlib import Path

# 정보글에서 AI 초안 티가 가장 많이 나는 상투 표현. 나오면 FAIL.
BANNED = [
    "알아보겠습니다", "알아보도록", "알아볼까요", "살펴보겠습니다", "살펴보도록", "살펴볼까요",
    "결론적으로", "요약하자면", "정리하자면", "마무리하며", "마치며", "이상으로",
    "도움이 되셨", "도움이 되었으면", "도움이 되길", "유익한 정보", "유익한 시간",
    "총정리", "완벽 가이드", "완벽 정리", "A to Z",
    "함께 알아", "에 대해 알아",
    "포스팅", "이번 글에서는", "이 글에서는",
]
# 써도 되지만 몰아 쓰면 기계 같아지는 표현: (표현, 허용 횟수)
LIMITED = [
    ("다양한", 1), ("중요합니다", 1), ("중요한", 2), ("필수", 1), ("효과적", 1),
    ("할 수 있습니다", 4), ("수 있어요", 4), ("것이 좋습니다", 1), ("것이 좋아요", 1),
    ("또한", 2), ("특히", 3), ("뿐만 아니라", 1), ("한편", 1), ("즉,", 2),
    # 블로그 말투에서 자연스럽지만 반복되면 티 나는 표현
    ("꿀팁", 1), ("여러분", 1), ("오늘은 ", 1), ("놓치지 마세요", 1), ("궁금하셨죠", 1),
]
# 블로그 말투 꾸밈 기준 (네이버판 / 티스토리판)
EMOJI_RANGE = {"naver": (3, 15), "tistory": (0, 6)}
# 실제로 겪지 않은 체험을 지어내는 문장. firsthand: true 가 아니면 FAIL.
FAKE_EXPERIENCE = [
    "직접 가봤", "직접 가 봤", "직접 가보", "다녀왔", "다녀 왔", "방문해 보니", "방문해보니", "먹어봤", "먹어 봤",
    "먹어보니", "먹어 보니", "제가 써보", "제가 써 보", "써봤는데", "써 봤는데", "제가 사용해", "직접 사용해",
]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
REQUIRED_FM = ["title", "description", "category", "info_as_of"]


def split_front_matter(text):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[1], parts[2]
    return "", text


def parse_fm(fm):
    data, sources, cur = {}, [], None
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            cur = m.group(1)
            data[cur] = m.group(2).strip().strip('"\'')
            continue
        if cur == "sources" and re.search(r"url:\s*\S+", line):
            sources.append(re.search(r"url:\s*(\S+)", line).group(1).strip('"\''))
    data["_sources"] = sources
    return data


def plain(body):
    body = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
    return body


def sentences(text):
    lines = [l for l in text.splitlines()
             if l.strip() and not l.lstrip().startswith(("#", "|", "-", "*", ">")) and not re.match(r"^\s*\d+\.", l)]
    joined = " ".join(lines).replace("**", "")
    parts = re.split(r"(?<=[.!?~])\s+|(?<=[\U0001F300-\U0001FAFF\u2600-\u27BF])\s+|(?<=다\.)|(?<=요\.)", joined)
    return [p.strip() for p in parts if len(p.strip()) > 4]


def check(path):
    text = Path(path).read_text(encoding="utf-8")
    fm_raw, body = split_front_matter(text)
    fm = parse_fm(fm_raw)
    flat = plain(body)
    fails, warns, stats = [], [], {}

    for k in REQUIRED_FM:
        if not fm.get(k):
            fails.append(f"front matter `{k}` 가 비어 있음")
    srcs = fm["_sources"]
    if len(set(srcs)) < 2:
        fails.append(f"출처(sources)가 {len(set(srcs))}개 — 서로 다른 출처 2개 이상 필요")

    for w in BANNED:
        n = flat.count(w)
        if n:
            fails.append(f"상투어 '{w}' {n}회")
    for w, cap in LIMITED:
        n = flat.count(w)
        if n > cap:
            warns.append(f"'{w}' {n}회 (권장 {cap}회 이하)")
    if fm.get("firsthand", "").lower() != "true":
        for w in FAKE_EXPERIENCE:
            if w in flat:
                fails.append(f"체험 표현 '{w}' — 실제 체험이 아니면 삭제 (실제 체험이면 front matter에 firsthand: true)")

    # 블로그 말투: 이모지·느낌표·물결은 쓰되 과하지 않게
    platform = "tistory" if ".tistory" in str(path) else "naver"
    emojis = EMOJI.findall(flat)
    lo, hi = EMOJI_RANGE[platform]
    stats["emoji"] = len(emojis)
    if len(emojis) < lo:
        warns.append(f"이모지 {len(emojis)}개 — 블로그 말투로 소제목·문장 끝에 {lo}개 이상 권장")
    if len(emojis) > hi:
        fails.append(f"이모지 {len(emojis)}개 — {platform}판은 {hi}개 이하 (과하면 광고글처럼 보여요)")
    tables = "\n".join(l for l in body.splitlines() if l.lstrip().startswith("|"))
    if EMOJI.search(tables):
        fails.append("표 안에는 이모지를 넣지 않기 (숫자·날짜가 흐려져요)")

    sents = sentences(flat)
    stats["sentences"] = len(sents)
    if len(sents) >= 8:
        lens = [len(s) for s in sents]
        mean = statistics.mean(lens)
        cv = statistics.pstdev(lens) / mean if mean else 0
        stats["sentence_len_mean"] = round(mean, 1)
        stats["sentence_len_cv"] = round(cv, 2)
        if cv < 0.38:
            warns.append(f"문장 길이가 너무 균일함 (변동계수 {cv:.2f}) — 짧은 문장과 긴 문장을 섞기")
        if mean > 70:
            warns.append(f"평균 문장 길이 {mean:.0f}자 — 너무 김")
        endings = [re.sub(r"[.!?\s]+$", "", s)[-3:] for s in sents]
        top = max(set(endings), key=endings.count)
        share = endings.count(top) / len(endings)
        stats["top_ending"] = f"{top} ({share:.0%})"
        if share > 0.45:
            warns.append(f"문장 끝 '{top}'이(가) {share:.0%} — 어미를 바꿔 리듬 주기")
        formal = sum(1 for s in sents if re.search(r"(니다|니까)[.!?]?$", s.strip()))
        stats["formal_ratio"] = f"{formal / len(sents):.0%}"
        if formal / len(sents) > 0.35:
            warns.append(f"'~습니다/~합니다' 문장 {formal / len(sents):.0%} — 부드러운 해요체로 바꾸기 (35% 이하 권장)")
        bang = sum(1 for s in sents if s.rstrip().endswith("!"))
        stats["exclaim"] = f"{bang / len(sents):.0%}"
        if bang / len(sents) > 0.3:
            warns.append(f"느낌표 문장 {bang / len(sents):.0%} — 강조할 때만 (30% 이하)")
        openers = [s.split()[0] for s in sents if s.split()]
        for i in range(len(openers) - 2):
            if openers[i] == openers[i + 1] == openers[i + 2]:
                warns.append(f"세 문장 연속 같은 시작어 '{openers[i]}'")
                break

    lines = [l for l in body.splitlines() if l.strip()]
    list_lines = [l for l in lines if re.match(r"^\s*([-*]|\d+\.)\s", l)]
    if lines and len(list_lines) / len(lines) > 0.55:
        warns.append(f"목록 비율 {len(list_lines) / len(lines):.0%} — 문단으로 풀어 쓴 설명을 늘리기")
    bolds = len(re.findall(r"\*\*[^*]+\*\*", body))
    paras = max(1, len([l for l in lines if not l.lstrip().startswith(("#", "|", "-", "*"))]))
    if bolds > paras:
        warns.append(f"굵은 글씨 {bolds}개 — 문단 수({paras})보다 많음")
    h2 = re.findall(r"^##\s+(.+)$", body, flags=re.M)
    if len(h2) > 7:
        warns.append(f"소제목 {len(h2)}개 — 너무 잘게 쪼갬")
    q_heads = [h for h in h2 if h.strip().endswith("?")]
    if len(h2) >= 3 and len(q_heads) == len(h2):
        warns.append("모든 소제목이 질문형 — 템플릿처럼 보임")

    chars = len(re.sub(r"\s", "", flat))
    stats["chars"] = chars
    if chars < 900:
        warns.append(f"본문 {chars}자 — 내용이 얇음 (900자 이상 권장)")

    score = max(0, 100 - 25 * len(fails) - 6 * len(warns))
    return {"file": str(path), "score": score, "fail": fails, "warn": warns, "stats": stats}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    results = [check(a) for a in args]
    if "--json" in sys.argv:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"\n■ {r['file']}  — 점수 {r['score']}")
            print("  " + ", ".join(f"{k}={v}" for k, v in r["stats"].items()))
            for f in r["fail"]:
                print(f"  ✗ FAIL  {f}")
            for w in r["warn"]:
                print(f"  △ WARN  {w}")
            if not r["fail"] and not r["warn"]:
                print("  ✓ 통과")
    sys.exit(1 if any(r["fail"] for r in results) else 0)


if __name__ == "__main__":
    main()
