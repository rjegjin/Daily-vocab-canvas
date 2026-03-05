# Daily Vocab Card Bot (단어장 자동 생성기)

## 프로젝트 개요
- 매일 새로운 단어(현재는 중국어 감정 형용사)를 선정하여 Gemini를 통해 이미지 생성 프롬프트를 만들고, Imagen 모델을 이용해 3x3 단어 카드 이미지를 그려 텔레그램으로 자동 전송하는 시스템입니다.
- **주요 스택**: Python, Google GenAI (Gemini 2.5 Flash, Imagen 4), Telegram Bot API

## 주요 파일
- `main.py`: 단어 생성 -> 이미지 프롬프트 생성 -> Imagen 모델 호출 -> 텔레그램 전송을 수행하는 메인 스크립트.

## 환경 설정 (.secrets/.env)
기존에 사용하던 `GEMINI_BOT_TOKEN`과 `GEMINI_CHAT_ID`를 기본으로(Fallback) 사용하도록 설계되었습니다. 새로운 봇과 방을 사용하려면 루트 폴더의 `.secrets/.env`에 다음 변수를 추가해야 합니다.
```env
VOCAB_BOT_TOKEN="새로운_텔레그램_봇_토큰"
VOCAB_CHAT_ID="새로운_텔레그램_채팅방_ID"
```

## 개발 일지
- **2026-03-05**: 프로젝트 초기 폴더(`Daily_Vocab_Card_Bot`) 생성 및 `main.py` 작성.
  - Gemini 2.5 Flash를 이용한 프롬프트 기획 로직 구현.
  - Imagen 모델(`imagen-4.0-generate-001`) 연동 및 이미지 생성 테스트 성공 (최신 Imagen 4 모델 적용 완료).
  - 텔레그램 메신저 전송 로직 구현 및 실제 전송 확인 성공.