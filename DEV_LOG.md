# Daily Vocab Card Bot (단어장 자동 생성기)

## 프로젝트 개요
- 매일 새로운 단어(스페인어 등)를 선정하여 Gemini를 통해 이미지 생성 프롬프트를 만들고, Imagen 모델을 이용해 3x3 단어 카드 이미지를 그려 텔레그램으로 자동 전송하는 시스템입니다.
- **주요 스택**: Python, Google GenAI (Gemini 3.0 Flash, Imagen 4), Telegram Bot API, GitHub Actions

## 주요 파일
- `main.py`: 단어 생성 -> 이미지 프롬프트 생성 -> Imagen 모델 호출 -> 텍스트 합성 -> 텔레그램 전송을 수행하는 메인 스크립트.
- `tools/issue_to_words.py`: GitHub Issue를 통해 학습 단어 목록(`learned_words.txt`)을 갱신하는 유틸리티.
- `learned_words.txt`: 이미 학습하여 중복 생성을 방지할 단어 목록.

## 환경 설정 (.secrets/.env)
기본적으로 루트 폴더의 `.secrets/.env`를 참조합니다. GitHub Actions에서 실행 시에는 Repository Secrets를 사용합니다.
```env
VOCAB_BOT_TOKEN="텔레그램_봇_토큰"
VOCAB_CHAT_ID="텔레그램_채팅방_ID"
GEMINI_API_KEY="구글_AI_스튜디오_API_키"
```

## 개발 일지
- **2026-03-05**: 프로젝트 초기 폴더(`Daily_Vocab_Card_Bot`) 생성 및 `main.py` 작성.
  - Gemini 2.5 Flash를 이용한 프롬프트 기획 로직 구현.
  - Imagen 모델(`imagen-4.0-generate-001`) 연동 및 이미지 생성 테스트 성공.
- **2026-03-10**: 대규모 고도화 및 시스템 안정화.
  - **모델 업그레이드**: `gemini-3-flash-preview` 적용 (Fallback 로직 포함).
  - **이미지 레이아웃 개선**: Pillow를 이용한 상단 순백색 텍스트 영역 확보 및 격자 정렬 시스템 도입.
  - **실행 환경 단일화**: 로컬 크론탭 제거 및 GitHub Actions(오전 5시 KST)로 통합.
  - **Issue 연동**: GitHub Issue(`update-words` 라벨)를 통한 학습 단어 수동 추가 기능 구현.
