# 셈터 자동화 운영 가이드

**매년·매달·매주 사람들이 다시 찾는 정보**와 **지금 검색이 뛰는 주제**를 골라, 원문으로 사실을 검증한 글을 **네이버판·티스토리판**으로 따로 써서 발행 대기함에 올려 두는 파이프라인입니다.

## 전체 흐름

```
[주제]
  반복 수요 캘린더 automation/calendar.yml ── 연말정산·장려금·세금·장학금·지급일·청약 주간 일정 …
  실시간 트렌드 레이더 (GitHub Actions 30분마다) ── Google 트렌드·정책브리핑·뉴스량·청약홈
        │
[Claude 구독 세션 · 예약 실행]  .claude/skills/blog-radar
  ① 캘린더 → 실시간 순으로 후보 선택 (개수 제한 없음)
  ② 공식 원문에서 이번 주기 실제 날짜·금액 확인 → claims (원문 인용)
  ③ 네이버판 _drafts/<slug>.md + 티스토리판 automation/variants/<slug>.tistory.md (다른 문장)
  ④ 재검수 1차(문체) → ⑤ 재검수 2차(독자·사실) → 검증기·문체·유사도 통과
  ⑥ 발행 대기함 exports/outbox.html (비공개 아티팩트로도 게시) → PR
        │
[GitHub Actions · PR마다]  출처 원문 자동 대조 + 두 판 유사도 + 테스트
        │
[사람 · 글당 1~2분]
  발행 대기함 열기 → [제목 복사][본문 복사][태그 복사] → 네이버·티스토리에 붙여넣기 → '발행함' 체크
```

## 왜 네이버 + 티스토리인가

| 채널 | 근거 | 역할 |
|---|---|---|
| 네이버 블로그 | 국내 검색 점유율 약 66% (2026년 2월, 인터넷트렌드) | 주력 |
| 티스토리 | 다음 검색 점유율은 2%대로 줄었지만, 티스토리는 다음과 구글 양쪽에서 노출되고 애드센스를 붙일 수 있음 | 보조 (구글 유입 + 애드센스) |
| 셈터 (이 사이트) | 계산기는 네이버 블로그에서 실행 불가 | 계산기 허브. 블로그 글에서 링크 |

네이버·티스토리 모두 공식 글쓰기 API가 없고, 매크로 자동 게시는 제재 대상이 될 수 있어 **붙여넣기는 사람이 합니다.** 대기함이 추천 발행 시각을 90분 간격으로 나눠 주니, 한꺼번에 몰아 올리지 마세요.

## 사실 검증 4중 장치

| 단계 | 무엇을 막나 |
|---|---|
| 글쓰기 기준 | 정부혜택·청약·선거·세금·노동 글은 공식 출처만 근거로 인정 |
| `verify_claims.py` | 본문의 숫자·날짜·금액 하나하나가 claims(원문 인용)와 연결됐는지. 빠지면 FAIL |
| fact-check CI | 출처 페이지를 실제로 내려받아 인용문 대조. 다르면 FAIL, 못 열면 '사람 확인' |
| 마감일 검사 | `deadline`이 지난 글은 발행 차단, 사이트에는 '마감됨' 표시 |

## 처음 한 번 해야 할 설정

1. **GitHub 연결**: Claude가 저장소에 푸시할 수 있어야 합니다.
2. **Actions 켜기**: 저장소 Settings → Actions → General에서 Workflow permissions를 *Read and write*로. 첫 실행은 Actions 탭에서 trend-radar를 *Run workflow*로 수동 실행해 수집원 상태(sources)를 확인합니다.
3. **(권장) 청약홈 API 키**: 공공데이터포털에서 '한국부동산원_청약홈 분양정보 조회 서비스' 활용 신청 → 저장소 Settings → Secrets에 `DATA_GO_KR_KEY` 등록. 응답 필드가 다르면 `trend_radar.py`의 `src_applyhome`을 고칩니다.
4. **(권장) 작성 세션 네트워크 허용**: Claude 클라우드 환경 설정 → Network access → Allowed domains에 `korea.kr`, `*.go.kr`, `applyhome.co.kr`, `lh.or.kr`, `i-sh.co.kr`, `nec.go.kr`, `trends.google.com`, `news.google.com` 추가. 허용하지 않으면 작성 세션은 원문을 직접 못 읽고, 근거를 CI와 사람이 확인하게 됩니다.
5. **예약 작업**: Claude에게 "blog-radar를 매시간 실행하는 예약 작업 만들어줘"라고 요청합니다.
6. **티스토리 블로그 개설**과 네이버 블로그 준비. 티스토리에는 애드센스, 네이버에는 애드포스트를 신청합니다.

## 스크립트

| 명령 | 역할 |
|---|---|
| `python3 automation/scripts/calendar_due.py [--date YYYY-MM-DD]` | 지금 준비할 반복 주제 (오프라인) |
| `python3 automation/scripts/trend_radar.py --out trends/latest.json` | 실시간 후보 수집·점수 (캘린더 포함) |
| `python3 automation/scripts/similarity_check.py A.md B.md` | 네이버판·티스토리판 문장 겹침 검사 |
| `python3 automation/scripts/build_outbox.py` | 발행 대기함 생성 |
| `python3 automation/scripts/fetch_source.py <URL> <찾을말>` | 원문에서 인용할 문장 찾기 |
| `python3 automation/scripts/verify_claims.py <md> [--fetch]` | 사실 검증 |
| `python3 automation/scripts/style_check.py <md>` | 문체 검사 |
| `python3 automation/scripts/export_paste.py <md>` | 네이버·티스토리 붙여넣기용 HTML |
| `python3 automation/scripts/publish.py <md>` | `_drafts` → `_posts` 발행 (검사 재실행) |
| `python3 automation/scripts/test_verify.py`, `node automation/scripts/test_tools.js` | 테스트 |

`automation/keywords/queue.yml`은 후보가 없을 때 쓸 상시 주제(계산기 연계) 대기열입니다. 캘린더 주제를 늘리려면 `automation/calendar.yml`에 항목을 추가하세요(공식 출처 URL 필수).

## 수익화

- 네이버: 애드포스트 (가입 기준은 네이버 애드포스트 공지 확인)
- 티스토리: 애드센스 승인 후 티스토리 플러그인으로 연결
- 셈터: 개인 도메인 연결 → 애드센스 → `_config.yml`의 `adsense_client`와 슬롯 ID, 루트에 `ads.txt`
