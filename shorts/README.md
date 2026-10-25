# 쇼츠 자동화

원본 클립 → Claude가 화면을 보고 대본 작성 → AI 음성 → 상단 배너·자막·속마음 자막·효과음·확대 합성 → YouTube 예약 업로드.
숏싹숏싹·신기+템 상위 영상을 장면 단위로 분석한 편집 문법(`prompts/style.md`)을 그대로 쓴다.

## 흐름
```
sources.yml (권리 장부) ─┐
inbox/*.mp4 ─────────────┴→ rights 검사 → brain(Claude: 프레임 24장 → 대본 JSON)
  → variety(최근 60편과 문장·제목·훅 유형 겹침 검사, 겹치면 다시 쓰기 최대 3번)
  → tts(ElevenLabs / Google Chirp3 HD) → render(ffmpeg + ASS 자막) → out/날짜/*.mp4
  → upload(YouTube API, config 의 시각에 예약) → state/history.json
```

## 처음 한 번 준비
1. **원본 클립**: `inbox/` 에 넣고 `sources.yml` 에 한 줄씩 등록. 직접 찍은 영상(`own`)이 아니면 허락·구매 증빙(`proof`) 없이는 렌더링하지 않는다.
2. **GitHub Secrets** (저장소 Settings → Secrets and variables → Actions, 채팅에 붙이지 말 것)
   - `ANTHROPIC_API_KEY` — 대본
   - `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` — 음성 (또는 `GOOGLE_TTS_API_KEY` 후 config 의 provider 를 google 로)
   - `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` — 업로드 (`python shorts/get_token.py <id> <secret>` 로 발급)
3. **API 감사(audit)**: 2020-07-28 이후 만든 API 프로젝트는 감사를 통과하기 전까지 업로드가 '비공개'로 잠긴다(Google `videos.insert` 문서). 감사 전에는 `upload.enabled: false` 로 두고 out/ 의 영상을 YouTube Studio 에서 예약하면 된다.
4. **배경음악**(선택): YouTube 오디오 보관함에서 받은 mp3 를 `assets/bgm/` 에. 효과음은 코드가 직접 합성한다.

## 실행
```
python shorts/run.py demo            # 키 없이 렌더링만 시험
python shorts/run.py make --limit 2  # 2편만 만들어 보기
python shorts/run.py daily           # 하루치 제작 + 예약
```
Actions `shorts-daily` 가 매일 05:07(KST)에 `daily` 를 돌린다. 완성본은 실행 화면의 Artifacts 에 14일 보관.

## 손볼 곳
- 말투·제목 패턴: `prompts/style.md`
- 편수·시각·색·글꼴·볼륨: `config.yml`
