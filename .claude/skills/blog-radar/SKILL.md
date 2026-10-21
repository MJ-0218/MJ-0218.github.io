---
name: blog-radar
description: 셈터 글 작성 루프. 반복 수요 캘린더(매년·매달·매주 찾는 정보)와 실시간 트렌드 레이더에서 지금 써야 할 주제를 골라, 원문 인용으로 사실을 검증한 네이버판·티스토리판 글을 개수 제한 없이 만들고 발행 대기함까지 갱신한다. "레이더 돌려줘", "글 써줘", "blog-radar" 또는 예약 작업에서 사용.
---

# 셈터 글 작성 루프

Claude 구독 세션에서 실행한다. 사용량은 넉넉히 써도 된다. 대신 **사실 검증이 최우선**이다. 확인이 안 되면 쓰지 않는다.
네이버·티스토리 발행은 사람이 발행 대기함에서 복사해서 한다. 이 작업은 초안, 검증, 대기함 갱신, main 머지까지 한다.

## 0. 준비
```bash
pip install -q markdown pyyaml
NOW=$(TZ=Asia/Seoul date +%Y%m%d-%H%M)
git fetch -q origin
git checkout -B drafts/$NOW origin/HEAD 2>/dev/null || git checkout -B drafts/$NOW
NET=$(python3 automation/scripts/fetch_source.py https://www.korea.kr/rss/policy.xml >/dev/null 2>&1 && echo OK || echo BLOCKED); echo "NET=$NET"
python3 automation/scripts/calendar_due.py --json > /tmp/calendar.json
git show origin/radar-data:trends/latest.json > /tmp/radar.json 2>/dev/null || echo '{"candidates":[]}' > /tmp/radar.json
python3 automation/scripts/evidence.py pull   # Actions 가 받아 둔 원문 수집본(방송 맛집 기사, 막힌 공식 누리집) → /tmp/evidence
```
`automation/config.yml`, `automation/prompts/writing-guide.md`를 먼저 읽는다.

## 1. 후보 고르기 — 캘린더 먼저, 그다음 실시간
1. **캘린더**(`/tmp/calendar.json`): 매년·매달·매주 반복해서 검색되는 주제. 한 번 자리 잡으면 해마다 다시 읽히니 우선한다.
   - 공식 출처(`official_sources`)에서 **이번 주기의 실제 날짜**를 확인한다. 캘린더의 months는 "보통 이 시기"일 뿐이다.
   - 이미 지났거나 이번 주기엔 쓸 게 없으면 `automation/state/skipped_cycles.txt`에 `cycle  # 사유`를 한 줄 추가한다.
   - 쓰는 글의 front matter에 `cycle: <cycle 값>`을 반드시 넣는다(중복 방지).
   - 한 주제의 단계별 검색 의도(예: 신청기간 / 지급일 / 기한 후 신청)는 각각 별도 글로 쓴다.
2. **실시간**(`/tmp/radar.json`의 candidates, `source != calendar`): `score ≥ config.writer.min_score`, `already_covered=false`, 공식 출처가 있는 생활 정보만. 사건·사고, 연예인 사생활, 의혹은 제외.
   - **급상승 우선**: `spike` 값이 있는 후보(직전 3시간보다 최근 1시간 기사 수가 2배 이상, 급상승 검색어 새 진입, 정책브리핑 인기뉴스 새 진입)는 캘린더보다 먼저 검토한다. 사람들이 지금 막 찾기 시작한 주제라 빨리 쓸수록 유입이 크다. 단, 공식 원문으로 사실을 확인하지 못하면 쓰지 않고 로그에 "급상승·원문 미확보"로 남긴다.
   - 급상승 검색어가 인물·사건이어도, 그와 연결된 **생활 정보**(신청 방법, 지급일, 일정, 계산법)가 공식 출처로 확인되면 그 정보 각도로 쓴다.
   - **방송 맛집**(`source == tv_food`): 프로그램·방송일 하나가 후보 하나. `score ≥ 15`면 검토하고, 방송일이 3일 넘게 지났으면 건너뛴다. 쓰는 법은 writing-guide 1-4(가게마다 서로 다른 매체 2곳 교차 확인, 블로그 수집본 `evidence.py list blog.naver` 포함, 위치 못 찾은 가게는 장소 없이). 방송 당일에 올라가야 하니 가장 먼저 쓴다.
   - 급상승(spike)으로 쓴 글은 front matter 에 `publish: now` → 대기함에서 즉시 발행으로 뜬다.
   - **급상승 이슈**(`spike` 있는 google_trends·google_news·korea_kr): 정부 정보가 아니어도 writing-guide 1-5 기준을 통과하면 `category: 이슈`로 쓴다.
3. 이미 같은 주제의 글이 `_drafts/`·`_posts/`·열린 drafts PR에 있으면 건너뛴다.

개수 제한은 없다(config.writer.max_posts_per_run이 0이 아니면 그 수까지). 후보마다 쓸지 말지와 이유를 로그에 남긴다.

## 1-1. 주간 청약 일정 (weekly-subscription)
`python3 automation/scripts/applyhome_week.py <그 주 월요일> --radar /tmp/radar.json --out /tmp/week.json` 이 단지별 일정·세대수와 청약홈 공고 원문 인용 claims 를 만들어 준다. 본문 날짜는 claims 의 "M월 D일" 표기 그대로 쓴다. 상대 시점 표현("오늘", "내일")은 쓰지 않는다.

## 2. 조사 — 원문 인용 확보
- `NET=OK`: `python3 automation/scripts/fetch_source.py <공식 URL> <찾을말>`로 원문 문장을 그대로 복사한다.
- 작성 세션에서 안 열리는 사이트(언론사, 국토부·복지로 등): 레이더 후보의 `evidence` URL 을 `python3 automation/scripts/evidence.py show <URL> <찾을말>`로 읽는다. 필요한 공식 URL 이 수집본에 없으면 `automation/state/fetch_requests.txt`에 한 줄 추가해 main 에 올리고, 다음 실행에서 쓴다(이번 실행에서는 보류). verify_claims 는 열기 실패 시 이 수집본으로 대조한다.
- `NET=BLOCKED`: WebSearch로 공식 페이지 URL과 내용을 찾고, claims에 `manual: "작성 세션에서 원문 접근 불가"`. CI가 원문을 다시 대조한다.
- 날짜는 **연도까지** 확인한다. 작년 공고를 올해 것으로 쓰는 실수가 가장 흔하다.

## 3. 쓰기 — 같은 사실, 두 개의 다른 글
- **네이버판** `_drafts/<slug>.md`: writing-guide의 네이버 항목을 따른다. `tags`(8~15개), `cycle` 또는 `trend`, 마감이 있으면 `deadline`.
- **티스토리판** `automation/variants/<slug>.tistory.md`: 같은 claims를 쓰되 제목, 도입, 소제목 구성, 문장을 새로 쓴다. 네이버판을 다듬어 고친 수준이면 안 된다.
- **claims** `automation/claims/<slug>.yml`: 두 판의 모든 숫자·날짜·금액·나이·기간. 원문 인용 + 출처, 계산값은 derived.

## 3-1. 이미지 (writing-guide 1-3)
```bash
pip install -q playwright 2>/dev/null
python3 automation/scripts/make_cards.py _drafts/<slug>.md automation/variants/<slug>.tistory.md   # 정보 카드
[ "$NET" = OK ] && python3 automation/scripts/evidence_shot.py <slug>                            # 공식 원문 형광펜 캡처 (capture: true 인 claim)
# 필요할 때만: python3 automation/scripts/get_image.py photo <slug> "영문 검색어"   (PEXELS_API_KEY)
#            python3 automation/scripts/get_image.py ai <slug> "장면 묘사"          (OPENAI_API_KEY)
```
캡처가 실패하면(열기 실패·인용문 못 찾음) 그 자리는 카드로 대신한다. 사진·AI 이미지는 출력된 YAML을 front matter `images:`에 붙인다.
`git add`에 `assets/cards assets/photos`도 포함한다(사이트에 올라가야 복사한 본문 속 이미지가 보인다).

## 4. 재검수 1차 — 문체 (두 판 모두)
`automation/prompts/review-1-voice.md`.

## 5. 재검수 2차 — 독자·사실 (두 판 모두)
`automation/prompts/review-2-reader-facts.md`. 이어서 전부 통과할 때까지:
```bash
for f in _drafts/<slug>.md automation/variants/<slug>.tistory.md; do
  python3 automation/scripts/verify_claims.py "$f" $( [ "$NET" = OK ] && echo --fetch )
  python3 automation/scripts/style_check.py "$f"
done
python3 automation/scripts/similarity_check.py _drafts/<slug>.md automation/variants/<slug>.tistory.md
```
세 번 고쳐도 안 되면 그 글은 버리고 이유를 로그에 적는다.

## 6. 발행 대기함
```bash
python3 automation/scripts/build_outbox.py $( [ "$NET" = OK ] && echo --fetch ) --artifact /tmp/outbox-artifact.html   # → exports/outbox.html + 아티팩트용 사본
```
Artifact 도구가 있으면 `/tmp/outbox-artifact.html`을 아티팩트로 발행한다. `automation/state/outbox_url.txt`에 URL이 있으면 먼저 그 URL을 `action: "read"`로 읽은 뒤 같은 `url`로 publish 해서 갱신하고, 없으면 새로 만들어 URL을 그 파일에 저장한다. 아티팩트는 비공개라 사람이 휴대폰에서 열어 바로 복사할 수 있다.

## 7. 로그, 커밋, PR
`automation/log/$NOW.md`: 검토한 후보 전체(쓴 것/건너뛴 것과 이유), 글마다 verify 표·style 점수·유사도.
```bash
git add _drafts automation exports assets/cards assets/photos && git commit -m "drafts: $NOW 초안 N편"
git push -u origin drafts/$NOW
```
쓴 글이 0편이고 skipped_cycles만 바뀌었으면 그것만 커밋해 푸시한다. 아무 변화가 없으면 푸시하지 않는다.
이번 실행의 verify(--fetch 가능하면)·style·유사도가 모두 통과했는지 다시 확인한다. FAIL이 남은 글은 커밋하지 않는다. 그다음 **main 에 바로 합친다** — 초안이 main에 쌓여야 다음 실행의 중복 검사와 발행 대기함이 이어진다(`_drafts/`, `exports/`는 사이트에 공개되지 않음).
```bash
git fetch -q origin main && git rebase -q origin/main && git push -q origin HEAD:main
```
- GitHub 도구(mcp__github__*)가 있으면 위 대신 PR을 열고 squash 머지해도 된다. PR 본문: 글 목록, verify 결과, 사람 확인 항목, 발행 대기함 링크.
- 푸시가 경합으로 거절되면 fetch·rebase 후 한 번만 다시 시도한다.
- 머지 뒤 fact-check CI가 원문을 한 번 더 대조한다. 실패하면 다음 실행에서 그 글을 고치거나 `automation/state/skipped_cycles.txt`로 내린다.

## 하지 않는 것
- 네이버·티스토리에 직접 로그인하거나 자동 발행하지 않는다(매크로·자동 게시는 계정 제재 위험).
- 출처 없는 숫자, 확인 안 된 정보, 지어낸 체험, 방송 캡처, 후보·정당 평가를 쓰지 않는다.

---

# 해외(미국 · Google Blogger) — 같은 실행에서 이어서

국내 글을 끝낸 뒤 같은 방식으로 미국 독자용 영어 글을 만든다. 번역이 아니라 미국 주제다. 규칙은 `automation/global/writing-guide-en.md`.

## U0. 준비
```bash
git show origin/radar-data:trends/us/latest.json > /tmp/radar_us.json 2>/dev/null || echo '{"candidates":[]}' > /tmp/radar_us.json
python3 automation/scripts/calendar_due.py --market us
python3 automation/scripts/evidence.py list            # .gov 원문 수집본 (작성 세션에서는 .gov 가 막혀 있음)
```

## U1. 후보
1. 캘린더(`calendar_due.py --market us`) → 2. 실시간(`/tmp/radar_us.json`, `spike` 우선) 순서. 기준은 국내와 같다(공식 출처·생활 정보·사건사고/사생활/정치 평가 제외).
2. 필요한 공식 URL 이 수집본에 없으면 `automation/global/fetch_requests.txt`에 추가하고 main 에 올린 뒤, GitHub 도구가 있으면 `trend-radar.yml`을 workflow_dispatch 로 돌려 3~5분 뒤 `evidence.py pull`로 받는다. 없으면 다음 실행으로 미룬다.

## U2. 쓰기·검증
- 초안 `automation/global/drafts/us-<slug>.md` (front matter `lang: en`, `labels`, `permalink`), claims `automation/claims/us-<slug>.yml`.
- 한 판만 쓴다(Blogger). 재검수 2회는 writing-guide-en 1·2절 기준으로.
```bash
export SEMTER_EVIDENCE_DIR=/tmp/evidence
python3 automation/scripts/make_cards.py automation/global/drafts/us-<slug>.md
python3 automation/scripts/verify_claims.py automation/global/drafts/us-<slug>.md --fetch   # 열기 실패 시 수집본으로 대조
python3 automation/scripts/style_check.py automation/global/drafts/us-<slug>.md
```
- 대기함은 `build_outbox.py` 한 번으로 국내·해외 탭이 같이 갱신된다. 로그는 `automation/global/log/$NOW.md`.
- 새 글 알림은 국내·해외를 합쳐 "대기함에 새 글 N편 (국내 a · 해외 b)".
