# Japanese / Chinese Fluency Roadmap

작성일: 2026-06-08

## 기준

영어 fluency 시스템은 vocab, phrase, dialogue, writing, feedback loop를 갖는다. 일본어와 중국어는 아직 vocab card 중심이므로 상호작용, 출력 훈련, 언어별 핵심 난관 훈련을 단계적으로 보강한다.

## 1차 반영 완료

### JA/ZH vocab weak feedback

상태: 완료

변경:
- `japanese.py`, `chinese.py` 카드 발송 뒤 inline feedback 메시지 전송
- `vocab_feedback.py` 추가
- `manager_bot.py`에서 `ja:vocab:*`, `zh:vocab:*` callback 처리

흐름:
- `✅ 다 알아`: 확인 메시지 전송
- `⚠️ 모르는 거 있어`: 최신 9개 단어 목록 버튼 표시
- 단어 선택: `learned_data_ja.json` 또는 `learned_data_zh.json`에 `weak: true`, `weak_date` 저장
- 다음 카드 생성 시 기존 weak 복습 로직이 해당 단어를 2-3개 후보로 재포함

저장 파일:
- `vocab_feedback_state.json`: 최신 JA/ZH vocab 카드 항목
- `learned_data_ja.json`: 일본어 weak flag
- `learned_data_zh.json`: 중국어 weak flag

## 즉시 후보

### Japanese TTS

상태: 완료

목표:
- `japanese.py` 카드 발송 후 약점 단어 또는 신규 단어 일부를 `ja-JP` TTS로 전송

구현:
- weak 단어가 있으면 weak 우선, 없으면 신규 단어 기준 3개 선택
- 단어와 예문을 하나의 MP3로 묶어 전송

### Chinese vocab TTS

상태: 완료

목표:
- `chinese.py` 카드 발송 후 예문 1-2개를 `cmn-CN` TTS로 전송

구현:
- weak 단어가 있으면 weak 우선, 없으면 신규 단어 기준 2개 선택
- 단어와 짧은 예문을 하나의 MP3로 묶어 전송

### Japanese rules history

상태: 완료

목표:
- `japanese_rules.py`에 `learned_data_ja_rules.json` 도입
- rule category, seen_count, weak 저장
- inline feedback으로 헷갈리는 규칙 재출현 가능하게 구성

구현:
- `ja_rules:*` callback 추가
- 오늘 다룬 한자/읽기 항목을 `learned_data_ja_rules.json`에 저장
- `✅ 이해했어`, `⚠️ 헷갈려` feedback 지원

### Chinese tones history and minimal pairs

상태: 완료

목표:
- `chinese_tones.py`에 최소대립쌍 세트 추가
- `learned_data_zh_tones.json`에 성조 학습 이력 저장

구현:
- `ma`, `shi`, `mai` 최소대립쌍 추가
- weak 항목 우선 재출현
- 최소대립쌍 TTS 추가
- `zh_tones:*` callback 추가

## 단기 후보

### `japanese_dialogue.py`

상태: 완료

필드:
- domain
- scenario_ko
- keigo_level: `丁寧語`, `普通体`, `敬語`
- target_expressions
- model_dialogue
- tts_script
- korean_trap

핵심:
- 매주 최소 1회 경어 상황 포함
- 직장, 고객 응대, 부탁, 거절, 사과 상황 우선

구현:
- 신규 모듈 `japanese_dialogue.py`
- `dialogue_history_ja.json` 저장
- `ja-JP` TTS 전송
- manager 메뉴/자동 실행/callback 연결

### `chinese_dialogue.py`

상태: 완료

필드:
- domain
- formality
- target_patterns
- complement_focus
- model_dialogue
- tts_script
- korean_trap

핵심:
- 결과보어, 방향보어, 가능보어를 회화 패턴 안에서 훈련

구현:
- 신규 모듈 `chinese_dialogue.py`
- `dialogue_history_zh.json` 저장
- `cmn-CN` TTS 전송
- manager 메뉴/자동 실행/callback 연결

### `chinese_tones.py` minimal pairs

상태: 완료

목표:
- `ma`, `shi`, `yi`, `wu` 같은 최소대립쌍을 누적 관리
- 4성 연속 TTS와 짧은 context sentence 제공
- `learned_data_zh_tones.json`에 이력 저장

## 중기 후보

### `japanese_writing.py`

목표:
- 50-100자 일본어 단문 쓰기
- 피드백 항목: 조사, 활용형, 경어 적절성, 자연스러운 표현

### `chinese_writing.py`

목표:
- 30-80자 중국어 메시지/의견 쓰기
- 피드백 항목: 어순, 보어, 양사, 성조/병음 참고

### `chinese_grammar.py`

목표:
- 보어 체계 전용 훈련
- 결과보어, 방향보어, 정도보어, 가능보어를 주 단위로 순환

### Chinese confusables

목표:
- 비슷한 간체자 변별 훈련
- 예: `己/已/巳`, `土/士/工`
- `learned_data_zh_confusables.json`에 이력 저장
