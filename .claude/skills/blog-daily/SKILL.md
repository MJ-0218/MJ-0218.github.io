---
name: blog-daily
description: 셈터 블로그의 하루치 글 초안을 만든다. 방송 정보 글 1편과 계산기 연계 생활정보 글 1편을 조사하고 초안을 쓴 뒤, 재검수 2회와 문체 검사를 거쳐 네이버·티스토리 붙여넣기용 HTML까지 만들어 drafts 브랜치에 올린다. "오늘 글 만들어줘", "blog-daily 실행" 또는 매일 예약 작업에서 사용.
---

# 셈터 일일 초안 작업

Claude 구독 세션에서 실행된다. API 키는 쓰지 않고, 조사는 이 세션의 WebSearch/WebFetch로 한다.
**발행은 하지 않는다.** 결과물은 사람이 확인한 뒤 발행한다.

## 0. 준비
```bash
pip install -q markdown
TODAY=$(TZ=Asia/Seoul date +%F)
git checkout -B drafts/$TODAY
```
`automation/config.yml`, `automation/prompts/writing-guide.md`를 먼저 읽는다.
이미 다룬 주제와 겹치지 않도록 `_posts/`, `_drafts/`, `automation/log/`의 제목들을 확인한다.

## 1. 주제 고르기
**방송 정보 글 (config.per_run.broadcast 편)**
- config의 programs 중 어제·오늘 방송분을 WebSearch로 찾는다. 예: `생생정보 {어제 날짜} 맛집`, `생방송 투데이 {날짜} 방송 정보`.
- 소개된 가게나 상품 하나를 고른다. 아래 조건을 **모두** 만족해야 한다.
  - 방송사 공식 페이지나 기사 1곳 이상과, 지도 플랫폼 업체 정보나 업체 공식 채널 1곳 이상에서 이름·주소가 일치한다.
  - 확인이 안 되면 다른 가게로 넘어가고, 그래도 안 되면 이 유형은 건너뛴다. 억지로 쓰지 않는다.
- 슬러그 예: `tv-saengsaeng-20261015-ojingeo-jeyuk`

**생활정보 글 (config.per_run.evergreen 편)**
- `automation/keywords/queue.yml`에서 `status: todo`인 첫 항목을 고른다.
- 대기열이 비면 `_data/tools.yml`의 계산기와 관련해 사람들이 자주 검색할 질문을 새로 3개 추가하고 그중 하나를 쓴다.

## 2. 조사
- 주제마다 공식 출처를 우선해 최소 2곳을 WebFetch로 직접 열어 읽는다. 법령은 국가법령정보센터, 정책은 정부·공공기관 페이지, 방송은 방송사 페이지를 우선한다.
- 확인한 사실은 `항목 | 값 | 출처 URL` 형태의 메모로 정리한다. 이 메모가 로그에 들어간다.

## 3. 초안
`automation/prompts/writing-guide.md`를 따라 `_drafts/<slug>.md`를 쓴다.
`info_as_of`는 오늘 날짜로, `sources`는 실제로 열어 본 URL로 채운다.

## 4. 재검수 1차 — 문체
`automation/prompts/review-1-voice.md`를 따라 다시 쓴다. 그다음 실행:
```bash
python3 automation/scripts/style_check.py _drafts/<slug>.md
```

## 5. 재검수 2차 — 독자·사실
`automation/prompts/review-2-reader-facts.md`를 따라 사실을 하나씩 다시 열어 확인하고 고친다.
style_check를 다시 돌려 FAIL 0개, 점수가 `config.review.min_score` 이상이 될 때까지 반복한다.
세 번 고쳐도 통과하지 못하면 그 글은 `_drafts/_rejected/`로 옮기고, 이유를 로그에 적는다.

## 6. 붙여넣기용 HTML
```bash
python3 automation/scripts/export_paste.py _drafts/<slug>.md --site <config.site_url>
```

## 7. 로그와 대기열
`automation/log/$TODAY.md`에 다음을 남긴다.
- 글마다: 제목, 유형, 최종 style_check 점수, 1차 변경 요약, 2차 사실 확인 표, 출처 목록
- 건너뛴 주제와 이유

생활정보 글을 썼다면 queue.yml에서 해당 항목을 `status: drafted`로 바꾼다.

## 8. 사이트 빌드 확인과 푸시
```bash
bundle install --quiet && bundle exec jekyll build --drafts -q 2>/dev/null && echo BUILD_OK
git add _drafts exports automation && git commit -m "drafts: $TODAY 초안 N편"
git push -u origin drafts/$TODAY
```
GitHub 도구가 있으면 `drafts/$TODAY` → 기본 브랜치로 PR을 연다.
PR 본문에는 글 목록, 점수, 붙여넣기 HTML 경로, 그리고 아래 **사람 확인 체크리스트**를 넣는다.

- [ ] 사실(가게 정보·숫자)을 직접 한 번 더 확인했다
- [ ] 셈터 발행: `python3 automation/scripts/publish.py _drafts/<slug>.md` 실행 후 커밋
- [ ] 네이버/티스토리: `exports/<slug>.html`을 브라우저로 열고 [본문 복사] → 에디터에 붙여넣기

## 하지 않는 것
- `_posts/`에 직접 쓰거나 기본 브랜치에 푸시하지 않는다(발행은 사람이 한다).
- 겪지 않은 체험을 지어내지 않는다. 방송 캡처나 남의 사진을 쓰지 않는다.
- 확인되지 않은 정보를 쓰지 않는다. 쓸 게 없으면 "오늘은 0편"도 정상 결과다.
