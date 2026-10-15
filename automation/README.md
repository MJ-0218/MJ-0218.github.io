# 셈터 자동화 운영 가이드

영상의 방식(방송·생활 검색 수요를 노린 글 + 애드센스)을 **계산기 도구 + 사람 검수 초안** 구조로 바꾼 파이프라인입니다.

## 전체 흐름

```
[매일 아침 예약 작업 — Claude 구독 세션, API 키 없음]
   ① 주제 고르기 ── 방송 정보 1편 (config.yml programs)
   │                └ 생활정보 1편 (keywords/queue.yml)
   ② 조사: 공식 출처 2곳 이상 직접 열어서 확인
   ③ 초안 → _drafts/<slug>.md          (prompts/writing-guide.md)
   ④ 재검수 1차: 문체                   (prompts/review-1-voice.md)
   ⑤ 재검수 2차: 독자 관점 + 사실 재확인  (prompts/review-2-reader-facts.md)
   ⑥ style_check.py 통과 (FAIL 0, 80점 이상)
   ⑦ export_paste.py → exports/<slug>.html
   ⑧ drafts/YYYY-MM-DD 브랜치 푸시 + PR
        │
[사람: 하루 5~10분]
   ⑨ PR에서 글 읽고 사실 한 번 더 확인
   ⑩-a 셈터 발행: python3 automation/scripts/publish.py _drafts/<slug>.md → 커밋 → 머지
   ⑩-b 네이버/티스토리: exports/<slug>.html 브라우저로 열기 → [본문 복사] → 에디터에 붙여넣기
```

실행 절차 전체는 `.claude/skills/blog-daily/SKILL.md`에 있습니다. Claude Code 세션에서 "blog-daily 실행"이라고 하면 같은 작업을 수동으로 돌릴 수 있습니다.

## 채널 전략

| 글 종류 | 어디에 | 이유 |
|---|---|---|
| 방송 정보 (A) | 네이버 블로그 우선, 티스토리 | 국내 검색 점유율은 네이버가 60%대. 방송 직후 검색이 몰리는 곳 |
| 생활정보 (D) | 셈터 + 네이버 둘 다 | 네이버 글 끝의 계산기 링크로 셈터에 유입 → 셈터 애드센스 |
| 계산기 | 셈터만 | 네이버 블로그는 스크립트를 실행할 수 없음 |

같은 글을 여러 곳에 그대로 올리면 중복 문서로 취급될 수 있습니다. 한쪽은 요약본으로 올리고 원문 링크를 거는 방식을 권장합니다.

## 스크립트

| 명령 | 역할 |
|---|---|
| `python3 automation/scripts/style_check.py <md>` | 상투어, 지어낸 체험, 이모지, 출처 수, 문장 리듬 검사. FAIL이면 exit 1 |
| `python3 automation/scripts/export_paste.py <md>` | 네이버·티스토리 붙여넣기용 HTML (`pip install markdown` 필요) |
| `python3 automation/scripts/publish.py <md>` | `_drafts` → `_posts` 발행 (발행 전 검사 재실행) |
| `node automation/scripts/test_tools.js` | 계산기 로직 테스트 |
| `bundle exec jekyll serve --drafts` | 초안까지 포함해 로컬 미리보기 |

## 애드센스 켜기 (필수 순서)

1. **개인 도메인 연결.** github.io 하위 주소는 소유권 확인이 어려워 승인이 사실상 어렵습니다. 도메인을 사서 GitHub Pages 설정 → Custom domain에 입력하고, `_config.yml`의 `url`과 `automation/config.yml`의 `site_url`을 바꿉니다.
2. 글 15편 이상, 소개 페이지와 개인정보처리방침이 갖춰진 뒤 애드센스를 신청합니다(둘 다 이미 있음).
3. 승인되면 `_config.yml`에 `adsense_client: ca-pub-...`와 슬롯 ID를 넣습니다. 루트에 `ads.txt`도 추가합니다.

## 지키는 원칙 (수익을 지키기 위한 것)

- 구글 정책은 AI로 독자에게 가치를 더하지 않는 페이지를 대량 생산하는 것을 스팸(scaled content abuse)으로 봅니다. 그래서 하루 편수를 적게 두고 사람이 검수합니다.
- 겪지 않은 체험은 쓰지 않습니다. 검사기가 막습니다.
- 방송 화면 캡처나 남의 사진은 쓰지 않습니다.
