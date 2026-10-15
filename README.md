# 셈터 (mj-0218.github.io)

생활 계산기와 출처를 확인한 정보 글을 모은 Jekyll 사이트입니다.

- 계산기: `tools/`, 로직은 `assets/js/tools.js`, 목록은 `_data/tools.yml`
- 글 자동화(초안 생성, 검수, 붙여넣기용 내보내기): [`automation/README.md`](automation/README.md)

```bash
bundle install
bundle exec jekyll serve --drafts   # http://localhost:4000
node automation/scripts/test_tools.js
```
