# 셈터 자동화 운영 가이드

**실시간 검색 급상승 주제를 잡아, 사실 검증을 통과한 글만 사람 확인 후 발행하는** 파이프라인입니다.

## 전체 흐름

```
[GitHub Actions · 30분마다]  trend-radar.yml
   Google 트렌드 한국 급상승어 ─┐
   정책브리핑 정책뉴스·보도자료 ─┼─▶ 분류(정부혜택·청약·선거·세금·노동·방송) + 점수
   감시 키워드 24시간 뉴스량   ─┤      └▶ radar-data 브랜치 trends/latest.json
   청약홈 분양정보 API (선택)  ─┘
                │
[Claude 구독 세션 · 예약 실행]  .claude/skills/blog-radar
   ① 점수 높은 후보 중 기준 통과한 것 전부 (개수 제한 없음)
   ② 공식 원문 확보 → 초안 _drafts/<slug>.md
   ③ 모든 숫자·날짜에 원문 인용 → automation/claims/<slug>.yml
   ④ 재검수 1차(문체) → ⑤ 재검수 2차(독자·사실 재대조)
   ⑥ verify_claims + style_check 통과 → 붙여넣기 HTML → PR
                │
[GitHub Actions · PR마다]  fact-check.yml
   출처 원문을 실제로 내려받아 인용문이 그대로 있는지 대조
   본문 숫자 중 근거 없는 것이 하나라도 있으면 실패
                │
[사람 · 5~10분]
   CI 통과 + '사람 확인' 항목 확인 → publish.py 로 발행 / 네이버·티스토리 붙여넣기
```

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

## 스크립트

| 명령 | 역할 |
|---|---|
| `python3 automation/scripts/trend_radar.py --out trends/latest.json` | 후보 수집·점수 |
| `python3 automation/scripts/fetch_source.py <URL> <찾을말>` | 원문에서 인용할 문장 찾기 |
| `python3 automation/scripts/verify_claims.py <md> [--fetch]` | 사실 검증 |
| `python3 automation/scripts/style_check.py <md>` | 문체 검사 |
| `python3 automation/scripts/export_paste.py <md>` | 네이버·티스토리 붙여넣기용 HTML |
| `python3 automation/scripts/publish.py <md>` | `_drafts` → `_posts` 발행 (검사 재실행) |
| `python3 automation/scripts/test_verify.py`, `node automation/scripts/test_tools.js` | 테스트 |

`automation/keywords/queue.yml`은 실시간 후보가 없을 때 쓸 상시 주제(계산기 연계) 대기열입니다.

## 채널 전략

| 글 종류 | 어디에 | 이유 |
|---|---|---|
| 실시간 정부혜택·청약·선거 | 네이버 블로그 + 셈터 | 국내 검색은 네이버가 60%대. 셈터는 구글 유입과 애드센스용 |
| 방송 정보 | 네이버·티스토리 | 방송 직후 네이버 검색 집중 |
| 계산기 | 셈터만 | 네이버 블로그는 스크립트 실행 불가 |

같은 글을 그대로 여러 곳에 올리면 중복 문서로 취급될 수 있으니, 한쪽은 요약본 + 원문 링크로 올리는 것을 권장합니다.

## 애드센스

개인 도메인 연결 → 글 15편 이상 → 신청 → 승인 후 `_config.yml`에 `adsense_client`와 슬롯 ID 입력, 루트에 `ads.txt` 추가.
