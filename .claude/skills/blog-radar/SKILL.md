---
name: blog-radar
description: 셈터 실시간 글 작성. 트렌드 레이더(radar-data 브랜치)에서 지금 검색이 뛰는 주제와 정부 공식 발표를 읽고, 기준을 통과하는 후보를 개수 제한 없이 글로 만든다. 모든 숫자에 원문 인용 근거를 붙이고 재검수 2회 뒤 PR로 올린다. "레이더 돌려줘", "실시간 글 써줘", "blog-radar" 또는 예약 작업에서 사용.
---

# 셈터 실시간 글 작성

Claude 구독 세션에서 실행한다. **사실 검증이 최우선이다.** 확인이 안 되면 쓰지 않는다. 쓸 게 없으면 0편이 정상 결과다.
발행은 사람이 한다. 이 작업은 PR까지만 만든다.

## 0. 준비
```bash
pip install -q markdown pyyaml
NOW=$(TZ=Asia/Seoul date +%Y%m%d-%H%M)
git fetch -q origin radar-data && git show origin/radar-data:trends/latest.json > /tmp/radar.json
git checkout -B drafts/$NOW origin/HEAD 2>/dev/null || git checkout -B drafts/$NOW
NET=$(python3 automation/scripts/fetch_source.py https://www.korea.kr/rss/policy.xml >/dev/null 2>&1 && echo OK || echo BLOCKED); echo "NET=$NET"
```
`automation/config.yml`과 `automation/prompts/writing-guide.md`를 먼저 읽는다.
`radar-data`를 가져오지 못하면 WebSearch로 같은 감시 키워드(config.radar.watch_keywords)의 최신 소식을 찾는 것으로 대신한다. 이때 WebSearch 결과는 캐시가 며칠 늦을 수 있으므로 날짜를 반드시 확인한다.

## 1. 후보 고르기
`/tmp/radar.json`의 `candidates`를 점수순으로 본다. 아래를 모두 만족하는 후보만 쓴다(개수 제한 없음, config.writer.max_posts_per_run이 0이 아니면 그 수까지).
- `score` ≥ config.writer.min_score, `already_covered`가 false
- 카테고리가 기타라면 생활 정보 주제일 때만. 사건·사고, 연예인 사생활, 의혹은 제외
- 공식 출처(정부·공공기관·청약홈·선관위·방송사 공식 페이지)를 찾을 수 있다
- 이미 `_posts/`, `_drafts/`, 열린 drafts PR에 같은 주제가 없다. 있으면 새 글 대신 기존 글의 **갱신**(날짜·숫자 업데이트)을 고려한다

후보마다 한 줄로 쓸지 말지와 이유를 메모해 둔다(로그에 들어간다).

## 2. 조사 — 원문 인용 확보
- 공식 출처의 **원문 페이지**를 연다. `NET=OK`이면:
  `python3 automation/scripts/fetch_source.py <URL> <찾을말>` 로 원문 문장을 그대로 복사한다.
- `NET=BLOCKED`이면 WebSearch로 공식 페이지 URL과 내용을 찾고, claims에 `manual: "작성 세션에서 원문 접근 불가"`를 붙인다. CI가 원문을 다시 대조하고, 못 찾으면 사람 확인 목록으로 넘긴다.
- 공식 발표와 언론 보도가 다르면 공식을 따르고 차이를 글에 적는다. 확정 전 정책은 상태를 밝힌다.

## 3. 초안 + claims
- `_drafts/<slug>.md` — writing-guide 형식. `trend`, `info_as_of`, 마감이 있으면 `deadline`.
- `automation/claims/<slug>.yml` — 본문의 **모든** 숫자·날짜·금액·나이·기간을 claim으로. 원문 인용(quote)과 출처(source) 필수, 계산값은 derived.

## 4. 재검수 1차 — 문체
`automation/prompts/review-1-voice.md`를 따른다. 이어서 `python3 automation/scripts/style_check.py _drafts/<slug>.md`.

## 5. 재검수 2차 — 독자·사실
`automation/prompts/review-2-reader-facts.md`를 따른다. claims의 항목을 하나씩 원문과 다시 맞춰 보고, 확인 안 되는 문장은 지운다.
```bash
python3 automation/scripts/verify_claims.py _drafts/<slug>.md $( [ "$NET" = OK ] && echo --fetch )
python3 automation/scripts/style_check.py _drafts/<slug>.md
```
둘 다 FAIL 0개, style 점수 ≥ config.writer.style_min_score가 될 때까지 고친다. 세 번 고쳐도 안 되면 그 글은 버리고 이유를 로그에 적는다.

## 6. 붙여넣기용 HTML
`python3 automation/scripts/export_paste.py _drafts/<slug>.md --site <config.site_url>`

## 7. 로그
`automation/log/$NOW.md`: 검토한 후보 전체(쓴 것/버린 것과 이유), 글마다 style 점수와 verify 결과 표, 1차 변경 요약.

## 8. 빌드, 푸시, PR
```bash
bundle install --quiet && bundle exec jekyll build --drafts -q 2>/dev/null && echo BUILD_OK
git add _drafts automation exports && git commit -m "drafts: $NOW 실시간 초안 N편"
git push -u origin drafts/$NOW
```
글이 0편이면 로그만 커밋하지 말고 아무것도 푸시하지 않는다.
GitHub 도구가 있으면 기본 브랜치로 PR을 연다. 본문에: 글 목록(카테고리, 트렌드 키워드, 점수), verify 결과 표, 사람 확인 항목, 그리고 체크리스트

- [ ] fact-check CI 통과 확인 (출처 원문 자동 대조)
- [ ] 사람 확인 항목을 원문에서 직접 확인
- [ ] 셈터 발행: `python3 automation/scripts/publish.py _drafts/<slug>.md` 후 커밋
- [ ] 네이버/티스토리: `exports/<slug>.html` 열고 [본문 복사] → 붙여넣기

## 하지 않는 것
- `_posts/`에 직접 쓰거나 기본 브랜치에 푸시하지 않는다.
- 출처 없는 숫자, 확인 안 된 정보, 지어낸 체험, 방송 캡처, 후보·정당 평가를 쓰지 않는다.
