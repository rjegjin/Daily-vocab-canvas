# English Fluency Practice System

## 목적

기존 vocab card 시스템을 영어 학습용으로 확장한 모듈이다. 영어는 이미지 단어 카드가 아니라 텍스트, 회화 TTS, 글쓰기 피드백을 중심으로 운영한다.

## 현재 구현된 모듈

### `english_vocab.py`

- 매일 영어 단어 9개 생성
- 이미지 생성 없음
- 영영 사전식 `definition_en`, IPA, 품사, register, collocation, example 제공
- Telegram inline button:
  - `✅ 다 알아`
  - `⚠️ 모르는 거 있어`
- 약점 단어는 `learned_data_en.json`에 `weak: true`로 기록

### `english_phrase.py`

- 월/수/금 영어 표현 6개 생성
- 의미, 예문, register, 한국어 화자 함정 표현 제공
- Telegram inline button:
  - `✅ 알겠어`
  - `⚠️ 헷갈려`
- 약점 표현은 `learned_data_en_phrase.json`에 기록

### `english_dialogue.py`

- 매일 회화 시나리오 1개 생성
- domain rotation 사용:
  - workplace, social, service, travel, academic, conflict, negotiation, small_talk
- 텍스트 시나리오와 모범 대화 전송
- Google TTS로 모범 발화 MP3 전송
- A/B 발화자를 다른 voice로 분리해 전송
  - 기본 A: `en-US-Neural2-D`
  - 기본 B: `en-US-Neural2-F`
- Telegram inline button:
  - `🔁 비슷한 상황 하나 더`
  - `💪 어려웠어`
  - `✅ 자신 있어`
- 하루 추가 생성은 최대 3회
- 이력은 `dialogue_history.json`에 저장

### `english_writing.py`

- 일요일 자동 글쓰기 과제 발행
- manager 메뉴에서 수동 실행하면 요일 제한 없이 `--force`로 발행
- 과제에는 topic, difficulty, structure guide, connectives, model sentence, vocabulary boost 포함
- 제출 감지:
  - writing pending 상태에서 긴 영어 텍스트 수신
  - 또는 `/writing_feedback` 명령 사용
- AI 피드백:
  - strengths
  - revision suggestions
  - grammar/vocabulary/structure scores
  - phrase_usage
  - next step
- 최근 `english_phrase.py` 표현과 weak phrase를 피드백 prompt에 반영

## 데이터 파일

### `learned_data_en.json`

영어 단어 학습 이력. 중복 방지, seen count, weak flag 저장.

### `learned_data_en_phrase.json`

영어 표현 학습 이력. 중복 방지, seen count, weak flag 저장.

### `dialogue_history.json`

회화 domain, scenario, target expressions, TTS 발송 여부 저장.

### `writing_sessions.json`

글쓰기 과제 단위 메타데이터 저장.

저장 항목:
- date
- topic_ko
- difficulty
- target_connectives
- vocabulary_boost
- submitted
- submission_count
- latest_scores
- feedback_sent

### `writing_submissions.json`

학습자가 제출한 글과 피드백 상세 이력 저장.

저장 항목:
- session_date
- submitted_at
- topic_ko
- difficulty
- submission_text
- feedback
- scores
- phrase_context
- phrase_usage

최근 250개 제출 이력을 유지한다.

### `english_state.json`

현재 상호작용 상태 저장.

예:
- latest_en_vocab
- latest_en_phrase
- latest_en_dialogue
- writing_pending
- dialogue_extras

## 자동 실행

`manager_bot.py`의 scheduler 기준:

- 05:00 KST: ES/JA/ZH 기본 카드
- 05:10 KST: ES/JA/ZH 부가 학습 시리즈
- 06:00 KST: 영어 플루언시
  - 매일: `english_vocab.py`, `english_dialogue.py`
  - 월/수/금: `english_phrase.py` 추가
  - 일요일: `english_writing.py` 추가

## 비용 정책

- 영어 vocab/phrase/writing은 이미지 생성 없음
- dialogue만 TTS 사용
- `budget.json`의 `lang_enabled.en`으로 영어 전체 활성/비활성 제어
- `cost.py`에서 `EN` 비용 표시
