# Daily Vocab Card Bot - 진행 상황 요약

작성일: 2026-06-08

## 1. 현재 프로젝트 상태

`Daily_Vocab_Card_Bot`은 매일 외국어 학습 콘텐츠를 생성해 Telegram으로 전송하는 자동화 봇이다.

기존에는 Spanish / Japanese / Chinese 단어 카드 중심이었다. 현재는 영어 학습을 단어 암기보다 넓은 fluency 훈련으로 확장하는 작업이 진행되어, `ENGLISH_FLUENCY_SYSTEM.md`와 영어 전용 모듈들이 추가된 상태다.

현재 구현 축은 다음과 같다.

- ES / JA / ZH: 이미지 기반 3x3 vocab card
- ES / JA / ZH 보조 학습: 패턴, 문법 규칙, 성조/TTS
- EN: 텍스트 기반 vocab / phrase / dialogue / writing fluency system
- Telegram manager bot: 수동 실행, inline/reply menu, 영어 피드백 interaction
- 비용 관리: Gemini 이미지/텍스트 비용, Google TTS 문자 수, 언어별 enable/disable

## 2. 주요 문서

### `README.md`

프로젝트의 기본 소개 문서다. 다만 현재 영어 fluency 모듈, manager bot interaction, 비용/통계 확장까지는 충분히 반영되어 있지 않다.

### `GEMINI.md`

초기 프로젝트 비전과 아키텍처 설명 문서다. 현재 구현 전체의 최신 요약이라기보다는 방향성 문서에 가깝다.

### `ENGLISH_FLUENCY_SYSTEM.md`

영어 확장 기능의 현재 기준 문서다. 영어 시스템의 목적, 구현된 모듈, 데이터 파일, 자동 실행 시간, 비용 정책이 정리되어 있다.

### `repomix-output.md`

AI 분석용으로 repo 내용을 합친 파일이다. 실제 운영 문서가 아니며, 최신 파일 목록과 다를 수 있으므로 원본 코드 기준으로 확인해야 한다.

## 3. 기존 다국어 카드 시스템

### Spanish - `spanish.py`

- Gemini로 매일 스페인어 단어 9개 생성
- Imagen 4 Fast로 단어별 visual concept 아이콘 생성
- Pillow로 3x3 flashcard 합성
- Telegram photo 전송
- `learned_data_es.json`에 학습 이력 저장
- weak 단어는 다음 생성 prompt에 review 후보로 포함

### Japanese - `japanese.py`

- 일본어 단어 9개 카드 생성
- 일본어 표기, 발음/뜻/예문 기반 카드 구성
- `learned_data_ja.json`에 학습 이력 저장
- GitHub Actions에서 별도 daily workflow로 실행 가능

### Chinese - `chinese.py`

- 중국어 단어 9개 카드 생성
- 중국어 표기, 병음, 뜻, 예문 기반 카드 구성
- `learned_data_zh.json`에 학습 이력 저장
- GitHub Actions에서 별도 daily workflow로 실행 가능

## 4. 기존 보조 학습 시리즈

### Spanish pattern - `main_patterns.py`

- 요일별 Spanish speaking/writing pattern 전송
- 추가 표현 3개를 주간 순환 방식으로 제공
- TTS 음성 발송 지원

### Japanese rules - `japanese_rules.py`

- 일본어 문법/표현 규칙 학습용 보조 콘텐츠
- manager bot에서 수동 실행 가능
- daily supplement scheduler에 포함

### Chinese tones - `chinese_tones.py`

- HSK 1-2급 단어와 성조 학습 콘텐츠 전송
- 성조 곡선 이미지 생성
- 일부 단어/예문 TTS 음성 발송

## 5. 영어 Fluency System

상세 기준 문서는 `ENGLISH_FLUENCY_SYSTEM.md`다. 현재 영어 시스템은 이미지 카드를 만들지 않고, 텍스트 카드와 TTS, Telegram interaction, writing feedback을 중심으로 구현되어 있다.

### Shared core - `english_core.py`

영어 모듈들의 공통 helper다.

- 환경 변수 로드
- Gemini client 생성
- JSON 응답 parsing
- Gemini token 비용 logging
- Telegram text/audio 전송
- 영어 학습 상태 저장
- learned data merge
- weak item marking
- dialogue history 관리
- writing pending 상태 관리
- 영어 TTS 생성

주요 데이터 파일:

- `learned_data_en.json`
- `learned_data_en_phrase.json`
- `dialogue_history.json`
- `writing_sessions.json`
- `writing_submissions.json`
- `english_state.json`

### English vocab - `english_vocab.py`

- 매일 영어 단어 9개 생성
- 대상 범위: B1-C1
- 필드:
  - `word`
  - `ipa`
  - `pos`
  - `definition_en`
  - `collocation`
  - `example`
  - `category`
  - `register`
- Telegram text message로 전송
- inline button:
  - `다 알아`
  - `모르는 거 있어`
- 헷갈리는 단어를 선택하면 `learned_data_en.json`에 `weak: true`로 기록

### English phrase - `english_phrase.py`

- 월/수/금 영어 phrase, idiom, collocation 6개 생성
- 필드:
  - `phrase`
  - `meaning_ko`
  - `example`
  - `register`
  - `trap`
  - `category`
- Korean learner error warning을 포함
- inline button으로 weak phrase 표시 가능
- `learned_data_en_phrase.json`에 이력 저장

### English dialogue - `english_dialogue.py`

- 매일 회화 시나리오 1개 생성
- domain rotation:
  - workplace
  - social
  - service
  - travel
  - academic
  - conflict
  - negotiation
  - small_talk
- 출력:
  - Korean situation
  - English context instruction
  - 6-turn model dialogue
  - target expressions 3개
  - cultural note
  - Korean trap
- Google TTS로 model dialogue MP3 전송
- inline button:
  - 비슷한 상황 하나 더
  - 어려웠어
  - 자신 있어
- 하루 추가 dialogue 생성은 최대 3회
- `dialogue_history.json`에 최근 90개 이력 저장

### English writing - `english_writing.py`

- 일요일 weekly writing assignment 발행
- manager bot에서 수동 실행하면 `--force`로 요일 제한 없이 실행
- prompt 구성:
  - topic
  - difficulty
  - target connectives
  - structure map
  - model paragraph
  - vocabulary boost
  - submission instruction
- writing pending 상태에서 긴 영어 텍스트를 받으면 feedback 생성
- `/writing_feedback` 명령으로도 제출 가능
- feedback 구성:
  - strengths
  - revisions
  - grammar/vocabulary/structure scores
  - next step
- `writing_sessions.json`은 최근 52개 세션 유지
- `writing_submissions.json`은 최근 250개 제출 이력 유지

## 6. Manager Bot 통합

`manager_bot.py`가 운영 허브다.

### 수동 실행 메뉴

기존 메뉴에 영어 항목이 추가되어 있다.

- EN 단어
- EN 표현
- EN 회화
- EN 글쓰기
- EN 오늘 전체

### Callback interaction

영어 관련 callback을 처리한다.

- vocab/phrase weak prompt
- vocab/phrase 특정 항목 weak marking
- dialogue 추가 생성
- dialogue hard/ok 응답

### Writing feedback 입력 처리

두 가지 방식이 있다.

- writing pending 상태에서 40단어 이상 텍스트를 보내면 자동 feedback
- `/writing_feedback` 뒤에 글을 붙이거나, 제출 메시지에 reply로 `/writing_feedback`

### 자동 실행 스케줄

현재 manager bot scheduler 기준:

- 05:00 KST: ES / JA / ZH 기본 vocab card
- 05:10 KST: ES pattern / JA rules / ZH tones
- 06:00 KST: English fluency series

English fluency series 구성:

- 매일: `english_vocab.py`, `english_dialogue.py`
- 월/수/금: `english_phrase.py` 추가
- 일요일: `english_writing.py` 추가

## 7. 비용과 예산 관리

### 공통 엔진 - `card_engine.py`

- Gemini/Imagen 비용을 `cost_log.json`에 기록
- TTS 문자 수를 월 단위로 누적
- `budget.json`을 읽어 월 예산 초과 시 실행 중단
- `lang_enabled`로 언어별 실행 가능 여부 제어
- 현재 기본 언어 키:
  - `es`
  - `ja`
  - `zh`
  - `en`

### 비용 CLI - `cost.py`

기능:

- 이번 달 비용 dashboard
- 최근 30일 history
- 월 예산 변경
- 언어별 enable/disable
- TTS enable/disable

영어 비용도 `EN`으로 표시된다.

### 현재 비용 정책

- ES/JA/ZH vocab card는 Imagen sheet 비용이 발생
- EN vocab/phrase/writing은 image 비용 없음
- EN dialogue는 TTS 비용 발생
- 영어 Gemini text generation 비용은 `log_cost("en", 0, ...)`로 기록
- TTS는 월 1,000,000자 무료 tier 이후 $4/1M chars 기준으로 계산

## 8. GitHub Actions

현재 workflow는 기존 언어별 daily run 중심이다.

- `.github/workflows/daily_run.yml`: Spanish daily card
- `.github/workflows/japanese_daily.yml`: Japanese daily card
- `.github/workflows/chinese_daily.yml`: Chinese daily card
- `.github/workflows/update_learned_words.yml`: GitHub Issue 기반 learned words 업데이트

주의할 점:

- 영어 fluency workflow는 별도 GitHub Actions 파일로는 아직 확인되지 않는다.
- 영어 자동 실행은 현재 `manager_bot.py`의 상주 scheduler 기준으로 연결되어 있다.

## 9. 데이터 파일 정리

### 기존 언어

- `learned_data_es.json`
- `learned_data_ja.json`
- `learned_data_zh.json`
- 기존 txt fallback:
  - `learned_words.txt`
  - `learned_ja.txt`
  - `learned_zh.txt`

### 영어

- `learned_data_en.json`: 영어 단어 이력
- `learned_data_en_phrase.json`: 영어 표현 이력
- `dialogue_history.json`: 회화 이력
- `writing_sessions.json`: 글쓰기 과제 세션
- `writing_submissions.json`: 제출 글과 feedback
- `english_state.json`: 최신 카드, pending writing, dialogue extra count 등 interaction 상태

### 비용

- `budget.json`: 월 예산, TTS, 언어별 활성화 상태
- `cost_log.json`: 날짜별 API 비용과 TTS 문자 수
- `cost_log.json.lock`: 비용 로그 파일 locking용

## 10. 현재 주의할 점

### `requirements.txt` 확인 필요

현재 코드에서 사용하는 dependency 중 일부가 `requirements.txt`에 보이지 않는다.

코드상 필요한 항목:

- `python-telegram-bot`
- `apscheduler`
- `google-cloud-texttospeech`
- `google-auth`

현재 `requirements.txt`에는 다음만 있다.

- `google-genai`
- `python-dotenv`
- `pillow`
- `textwrap3`
- `requests`

로컬 환경에는 이미 설치되어 있을 수 있지만, GitHub Actions나 새 환경에서 manager/영어/TTS를 실행하려면 dependency 정리가 필요하다.

### GitHub Actions와 manager scheduler의 역할 분리

현재 기존 daily workflow는 각 언어 script를 직접 실행한다. 반면 영어 fluency는 manager bot scheduler에 연결되어 있다.

선택지가 있다.

- 상주 manager bot으로 영어를 운영한다.
- 영어용 GitHub Actions workflow를 추가한다.
- 기존 workflow를 manager 중심으로 재설계한다.

### README 최신화 필요

`README.md`는 초기 기능 중심이라 현재 구현과 차이가 크다. 이 문서를 기준으로 README를 다시 작성하면 onboarding과 운영 이해가 쉬워진다.

## 11. 다음 작업 제안

우선순위는 다음 순서가 적절하다.

1. `requirements.txt`를 현재 코드 기준으로 보강
2. 영어 데이터 파일이 없을 때 첫 실행이 정상 동작하는지 smoke test
3. manager bot의 영어 callback과 writing feedback 경로 테스트
4. 영어 GitHub Actions가 필요한지 결정
5. `README.md`를 현재 구조 기준으로 업데이트
6. `ENGLISH_FLUENCY_SYSTEM.md`와 이 문서의 역할을 분리해서 유지

## 12. 문서 역할 권장안

- `README.md`: 사용법, 설치, 실행, 환경 변수, 운영 가이드
- `PROJECT_STATUS.md`: 현재 구현 상태와 진행 상황 요약
- `ENGLISH_FLUENCY_SYSTEM.md`: 영어 fluency system 상세 설계와 정책
- `GEMINI.md`: 비전 또는 AI assistant용 프로젝트 원칙
