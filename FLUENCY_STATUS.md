# Fluency System Status

작성일: 2026-06-09

이 문서는 현재 구현된 기능, 설계되었지만 아직 구현되지 않은 기능, 운영상 이슈를 명확히 구분한다.

## Implemented

### Core vocab image cards

상태: 구현됨

대상:
- `spanish.py`
- `japanese.py`
- `chinese.py`

기능:
- OpenAI 저가 텍스트 모델로 단어 9개 JSON 생성
- OpenAI 저가 이미지 모델로 3x3 icon sheet 1장 생성
- `create_flashcard()`로 3x3 이미지 카드 생성
- Telegram photo 전송
- `learned_data_es.json`, `learned_data_ja.json`, `learned_data_zh.json`에 학습 이력 저장
- weak 단어를 다음 생성 prompt에 복습 후보로 포함

주의:
- 그림 카드 기능은 삭제되지 않았다.
- 2026-06-09부터 기본 provider를 OpenAI 저가형으로 전환했다.
- 기본 텍스트 모델: `gpt-4.1-nano`
- 기본 이미지 모델: `gpt-image-1-mini`, quality `low`
- 기존 Gemini/Imagen 경로는 환경변수로 되돌릴 수 있다.

비용 추정:
- 실제 스페인어 시험 실행 기준:
  - text: 약 `$0.000322`
  - image: `$0.005`
  - 합계: 약 `$0.005322` / 언어 / 1회
- ES/JA/ZH 매일 1회씩 30일 실행 시:
  - 약 `$0.48` / 월
  - JA/ZH vocab TTS는 Google TTS 무료 1M chars 이내면 추가 비용 없음

### English fluency

상태: 구현됨

모듈:
- `english_vocab.py`
- `english_phrase.py`
- `english_dialogue.py`
- `english_writing.py`
- `english_core.py`

기능:
- 영어 단어 텍스트 카드
- 영영 사전식 definition
- 표현/phrase 카드
- dialogue + TTS
- writing prompt
- writing feedback
- writing submission/feedback 저장
- inline weak feedback

데이터:
- `learned_data_en.json`
- `learned_data_en_phrase.json`
- `dialogue_history.json`
- `writing_sessions.json`
- `writing_submissions.json`
- `english_state.json`

### Japanese fluency

상태: 부분 구현됨

구현됨:
- 이미지 vocab card
- vocab weak feedback
- vocab TTS
- `japanese_rules.py` 이력화
- `learned_data_ja_rules.json`
- `japanese_dialogue.py`
- dialogue TTS
- `dialogue_history_ja.json`

아직 구현 안 됨:
- `japanese_writing.py`
- 일본어 writing feedback 저장
- 경어 평가 점수화
- 한자 음독/훈독 전용 심화 drill

### Chinese fluency

상태: 부분 구현됨

구현됨:
- 이미지 vocab card
- vocab weak feedback
- vocab TTS
- `chinese_tones.py` 이력화
- minimal pair 성조 훈련
- `learned_data_zh_tones.json`
- `chinese_dialogue.py`
- dialogue TTS
- `dialogue_history_zh.json`

아직 구현 안 됨:
- `chinese_writing.py`
- 중국어 writing feedback 저장
- `chinese_grammar.py`
- 보어 구조 전용 drill
- confusable character module
- `learned_data_zh_confusables.json`

### Manager bot

상태: 구현됨

기능:
- `/start`, `/manage`
- ES/JA/ZH 기본 카드 수동 실행
- ES/JA/ZH 부가 시리즈 수동 실행
- EN fluency 수동 실행
- JA/ZH dialogue 수동 실행
- inline callback 처리
- writing feedback command

자동 실행:
- 05:00 KST: ES/JA/ZH vocab image cards
- 05:10 KST: ES patterns, JA rules, ZH tones
- 06:00 KST: English fluency
- 06:20 KST: JA/ZH dialogue

## Designed But Not Implemented

### Japanese writing

목표:
- 50-100자 일본어 단문 쓰기
- 조사, 활용형, 경어 적절성, 자연스러운 표현 피드백
- 제출 원문과 피드백 저장

예상 파일:
- `japanese_writing.py`
- `writing_sessions_ja.json`
- `writing_submissions_ja.json`

### Chinese writing

목표:
- 30-80자 중국어 메시지/의견 쓰기
- 어순, 보어, 양사, 자연스러운 표현 피드백
- 제출 원문과 피드백 저장

예상 파일:
- `chinese_writing.py`
- `writing_sessions_zh.json`
- `writing_submissions_zh.json`

### Chinese grammar drill

목표:
- 결과보어, 방향보어, 정도보어, 가능보어 전용 훈련

예상 파일:
- `chinese_grammar.py`
- `learned_data_zh_grammar.json`

### Chinese confusables

목표:
- 비슷한 간체자 변별 훈련
- 예: `己/已/巳`, `土/士/工`

예상 파일:
- `chinese_confusables.py`
- `learned_data_zh_confusables.json`

## Operational Issues

### Gemini API credit depletion

상태: 우회 완료

증상:
- ES/JA/ZH vocab image cards가 발송되지 않음
- JA/ZH dialogue도 Gemini 생성 단계에서 실패

로그:
- `429 RESOURCE_EXHAUSTED`
- 메시지: `Your prepayment credits are depleted`

원인:
- 그림 카드 기능 삭제가 아니다.
- `spanish.py`, `japanese.py`, `chinese.py`에는 여전히 `generate_icons()`, `create_flashcard()`, `send_to_telegram()` 경로가 있다.
- Gemini 단어 JSON 생성이 실패해서 이미지 생성 함수까지 도달하지 못한다.

마지막 확인:
- 원격 `mh_bot`에 마지막 이미지 파일 존재
  - `final_flashcard.png`
  - `flashcard_ja.png`
  - `flashcard_zh.png`
- timestamp: 2026-06-07 20:00

해결:
- 2026-06-09 OpenAI 저가형 text/image provider로 전환
- 원격 `spanish.py` 시험 실행 성공
- Gemini credit 충전 없이도 기본 vocab image card는 다시 동작한다.
- Gemini/Imagen으로 되돌리려면 Google AI Studio/Gemini billing prepayment credit 충전 또는 API key 교체가 필요하다.

## Source Documents

- `CONTEXT.md`: 날짜별 작업/배포 이력
- `ENGLISH_FLUENCY_SYSTEM.md`: 영어 시스템 상세
- `JA_ZH_FLUENCY_ROADMAP.md`: 일본어/중국어 fluency 로드맵
- `FLUENCY_STATUS.md`: 현재 구현/예정/운영 이슈 구분
