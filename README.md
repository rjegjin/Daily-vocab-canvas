# Daily Vocab Card Bot 🖋️🎨

AI 기반 매일 외국어 학습 콘텐츠 생성 및 Telegram 전송 봇입니다. ES/JA/ZH는 이미지 단어 카드를, EN은 텍스트·회화·쓰기 중심의 fluency 콘텐츠를 제공합니다.

## 🌟 주요 기능
- **스마트 단어 선정**: OpenAI 텍스트 모델로 중복되지 않는 오늘의 단어 9개 선정.
- **AI 일러스트 생성**: `gpt-image-1-mini` medium 품질로 3개 단위 icon sheet를 생성하고 품질 검사 후 사용.
- **전문적인 레이아웃**: Pillow 라이브러리로 텍스트와 이미지를 합성하여 깔끔한 3x3 격자 카드 완성.
- **안전한 발송**: 아이콘 9개가 완전하지 않으면 카드 발송을 중단하고, 정상 카드는 PNG document로 전송.
- **자동화된 배포**: 언어별 상주 봇 scheduler를 통해 매일 오전 5시(KST) 자동 발송.
- **단어 목록 관리**: 언어별 학습 목록(`learned_data_es.json`, `learned_data_ja.json`, `learned_data_zh.json`) 자동 갱신.

## 🛠️ 기술 스택
- **언어**: Python 3.12
- **AI**: OpenAI (`gpt-4.1-nano`, `gpt-image-1-mini`), Google Gemini/Imagen fallback
- **이미지 처리**: Pillow (PIL)
- **배포/자동화**: GitHub Actions, Telegram Bot API

## 📋 사용 가이드

### 1. 주요 환경 변수
- `OPENAI_API_KEY`: 기본 text/image provider API key
- `VOCAB_OPENAI_IMAGE_QUALITY`: 기본값 `medium`
- `VOCAB_TELEGRAM_SEND_MODE`: 기본값 `document`; 호환이 필요하면 `photo`
- `GEMINI_API_KEY`: Gemini fallback 사용 시 API key

운영의 언어별 user service는 `systemd/vocab-image-quality.conf`를 drop-in으로 사용해 과거 `.env`의 `low` 설정보다 `medium`을 우선합니다.
- `VOCAB_BOT_TOKEN`: 텔레그램 봇 토큰
- `VOCAB_CHAT_ID`: 단어 카드를 받을 텔레그램 채팅방 ID

### 2. 학습 목록 수동 업데이트 방법
이미 알고 있는 단어나 추가하고 싶은 단어가 있다면:
1. GitHub Repository의 **Issues** 탭으로 이동.
2. `New Issue`를 클릭하고 제목 작성.
3. Labels에서 `update-words`를 선택.
4. 본문에 한 줄에 하나씩 단어를 입력 후 `Submit`.
5. 봇이 자동으로 단어를 추가하고 Issue를 닫습니다.

## 🤝 기여 및 문의
문의 사항은 Issue 또는 Pull Request를 통해 남겨주세요.
