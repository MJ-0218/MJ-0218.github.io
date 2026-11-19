# 쇼츠 하루 4편 루틴 (사용자 요청 2026-11-19)

매일 예약 실행이 이 순서대로 한다. 목표: **검수 2회 통과한 쇼츠 4편**을 구글 드라이브 '이게뭐야' 폴더에 'N화 짧은이름' 폴더(영상 + 제목·캡션·태그 문서)로 올리기.

1. 최신 main. `shorts/state/frames/` 에서 장면 사진은 있는데 아직 안 만든(history 에 없는) 클립이 4편 미만이면 Actions `shorts-frames`(limit 10)를 돌리고 커밋을 기다린다.
2. 후보를 장면 사진 시트(ffmpeg tile)와 받아쓰기로 본다. **정책에 걸릴 만한 건 빼고** 다음 후보로 채워 **총 4편**을 맞춘다. 빼는 기준:
   - YouTube 유해·위험 콘텐츠: 실제 위험에 처했다고 믿게 하는 장난(가짜 칼·총·강도·사고), 위험 행동 따라 하기, 아이를 놀래키거나 괴롭히는 장난.
   - 방송·영화·드라마 장면, 남의 영상 모음·재업로드 계정, 브랜드 광고 계정.
   - 선정성·혐오·비하(인종·외모), 미성년자를 성적·위험하게 다루는 것, 실제 사고·부상 장면.
   - 화면이 거의 글자뿐이라 쓸 장면이 없는 것.
   뺀 클립은 `sources.yml` 항목에 `hold: "이유"` 를 적는다(rights.check 가 건너뜀).
3. 4편 대본을 `shorts/scripts/<id>.json` 으로 쓴다(`prompts/style.md`: 히트 제목 공식, 킥 기준 끝 CTA, 나레이션 음성 없음, music_prompt, 원본 자막 띠는 sources.yml 에 cut_top/cut_bottom/blur_band).
4. 커밋·푸시 → Actions `shorts-daily`(limit 10) → 만든 뒤 `state/review/<id>.lines.jpg`·`<id>.jpg` 로 검수 2회(1차 줄별 화면·대사 대조, 2차 화면 이상·장면 경계). fix 면 고쳐서 다시 만들고 1차부터 다시.
5. 4편 모두 '검수 통과'면 `python3 shorts/drive_upload.py <id> "<짧은이름>" ...` (화 번호는 state/drive.json 이 이어서 매김) → `state/drive.json` 커밋.
6. 쇼츠 대기판 갱신(build_board → 같은 url publish). 끝나면 드라이브 폴더 링크 4개와 뺀 클립·이유를 짧게 요약하고 푸시 알림 "쇼츠 4편 드라이브 업로드 (N화~M화)".
