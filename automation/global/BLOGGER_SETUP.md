# Blogger 자동 예약 발행 — 처음 한 번 설정 (약 10분)

비밀값은 **GitHub 저장소 Secrets 에만** 넣는다. 채팅에 붙여 넣지 않는다.

## 1. Google Cloud 프로젝트와 Blogger API
1. https://console.cloud.google.com/ → 새 프로젝트 (이름 예: semter-blogger)
2. "API 및 서비스 → 라이브러리" → **Blogger API v3** 검색 → 사용 설정

## 2. OAuth 동의 화면
1. "API 및 서비스 → OAuth 동의 화면" → 사용자 유형 **외부** → 앱 이름·이메일만 입력
2. 범위는 비워 둬도 된다(3단계에서 요청)
3. **게시 상태를 '프로덕션'으로 전환**(앱 게시). '테스트' 상태에서는 갱신 토큰이 **7일 뒤 만료**된다 — Google 안내: https://developers.google.com/health/setup
   - 검증 안 된 앱 경고가 떠도 본인 계정만 쓰니 "고급 → 이동"으로 진행하면 된다

## 3. OAuth 클라이언트 + 갱신 토큰
1. "사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID" → 유형 **웹 애플리케이션**
2. 승인된 리디렉션 URI에 `https://developers.google.com/oauthplayground` 추가 → 만들기 → **클라이언트 ID / 보안 비밀** 확인
3. https://developers.google.com/oauthplayground 열기 → 오른쪽 위 톱니바퀴 → **Use your own OAuth credentials** 체크 → 클라이언트 ID·보안 비밀 입력 (Access type: Offline)
4. 왼쪽 입력칸에 `https://www.googleapis.com/auth/blogger` 입력 → **Authorize APIs** → Blogger 계정으로 허용
5. **Exchange authorization code for tokens** → 나온 **Refresh token** 복사
   - 절차 원문: https://developers.google.com/google-ads/api/docs/oauth/playground
   - 끝나면 리디렉션 URI 는 지워도 된다(하나는 남겨야 함)

## 4. 블로그 ID
Blogger 관리 화면 주소 `https://www.blogger.com/blog/posts/<숫자>` 의 숫자가 블로그 ID

## 5. GitHub Secrets
저장소 → Settings → Secrets and variables → Actions → New repository secret 로 4개:
| 이름 | 값 |
|---|---|
| `BLOGGER_CLIENT_ID` | 3-2의 클라이언트 ID |
| `BLOGGER_CLIENT_SECRET` | 3-2의 보안 비밀 |
| `BLOGGER_REFRESH_TOKEN` | 3-5의 Refresh token |
| `BLOGGER_BLOG_ID` | 4의 숫자 |

## 6. 동작
- `.github/workflows/blogger-publish.yml` 이 매시 40분, 그리고 해외 초안이 main 에 올라올 때 돈다. Actions 탭에서 **Run workflow** 로 바로 돌려도 된다.
- 검증 통과 + 아직 안 올린 글만, 추천 시각(미국 동부 6~22시, 120분 간격)으로 **예약 발행**. 리콜처럼 급한 글은 바로 발행.
- 이미 직접 올린 글(대기함에서 Blogger '발행함' 체크)은 건너뛴다.
- 예약 결과는 `automation/state/blogger_scheduled.json` 에 남고, 대기함 카드에 "예약됨 … · Blogger 자동"으로 뜨며 발행함이 체크된다.
- API 로는 Blogger 의 '검색 설명'과 '맞춤 퍼머링크'를 넣을 수 없다 → 퍼머링크는 제목에서 자동 생성. 필요하면 예약된 글을 Blogger 에서 열어 '검색 설명'만 붙여 넣으면 된다(대기함 [검색 설명] 버튼).
- 예약 취소: Blogger 관리 화면에서 해당 글을 초안으로 되돌리거나 삭제.
