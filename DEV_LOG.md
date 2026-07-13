## [2026-07-10]

- refactor: 영어 말하기 전송 계약 분리 — english_speaking return-only + english_bot 핸들러 등록

## [2026-07-09]

- feat: 서버 로컬 개선 일괄 커밋 (05:10 학습 시리즈, monthly_report 등)
- fix: OpenAI import 되돌림 — 테스트 호환성 우선
- fix: generate_dialogue 실패 처리 및 import 정리
- fix: 데이터 소스 단일화 — speaking_stats() SPEAKING_SESSIONS_FILE만 읽기
- feat: 말하기 세션 지표 통합 — manager_bot/bot_runtime/monthly_report
- fix(P1-c): 코드 리뷰 수정 — STT 중복 제거, 어순 이탈 검출 추가
- feat: 쉐도잉 diff 모드 구현 (P1-c)
- feat: 말하기 세션 분석 파이프라인 구현 (P1-b)
- fix: 3건 리뷰 지적 사항 수정
- feat: 영어 말하기 롤플레이 모드 + manager_bot thin handler 추가

## [2026-07-07]

- chore: docs 최신화 - OpenAI 제공자 전환 및 bot_common 부트스트랩 반영

## [2026-07-06]

- refactor: 봇 부트스트랩을 공용 bot_common으로 교체
- chore: ES/JA/ZH daily GitHub Actions의 schedule 트리거 제거
- feat: OpenAI 저가 provider 전환 + 영어 fluency 시스템 + JA/ZH dialogue 확장

## [2026-04-07]

- feat: --disable all / --enable all 전체 언어 일괄 토글 추가

## [2026-04-05]

- feat: BigQuery billing export 조회 스크립트
- feat: 이미지 생성 Gemini → Imagen4 전환 (비용 65% 절감)

## [2026-04-04]

- feat: 비용 대시보드 + 예산 관리 시스템

## [2026-04-03]

- feat: 버그 수정 + 언어별 색상 테마 + 월간 성취 리포트

## [2026-04-02]

- fix: handle missing LANG_LABEL keys for pattern/rule/tone features
- feat: add menu buttons for pattern/rule/tone features
- feat: Night Worker 학습 단어 JSON 전환 + 취약 단어 재등장
- feat: add Japanese onkun rules learning system
- refactor: simplify text formatting and add Markdown support
- feat: add tone curve visualization to Chinese tone learning
- feat: add Spanish pattern reflections and Chinese tone visualization systems

## [2026-04-01]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-31]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-30]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-29]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]
- chore: restore GitHub Actions schedule triggers
- chore: disable GitHub Actions schedule, migrate to local systemd timers
- feat: change meaning field from Korean to English (1-3 words)

## [2026-03-28]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-27]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-26]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-25]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-24]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-23]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-22]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-21]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]

## [2026-03-20]

- chore: update learned_zh.txt [skip ci]
- chore: update learned_ja.txt [skip ci]
- chore: update learned words list [skip ci]
- fix: resolve PROJECT_DIR path failure in GitHub Actions
- fix: prevent TypeError when log[today] contains float _daily_total_usd

## [2026-03-19]

- feat: add cost tracking and enforce 1K image size
- feat: add Japanese and Chinese daily vocab card bots
- refactor: switch to per-icon Gemini image generation with proper sizing
- chore: upgrade vocab generation to gemini-3.1-flash-lite-preview with 2.5-flash fallback

## [2026-03-10]

- docs: Update DEV_LOG.md and add README.md, GEMINI.md
- feat: add GitHub Issue integration to update learned words
- chore: unify to GitHub Actions, improve image layout and update model to 3.0 (with fallback)

## [2026-03-06]

- feat: initial commit for vocab bot with GitHub Actions

