# Daily Vocab Card Bot 🖋️🎨

AI 기반 매일 단어장 자동 생성 및 전송 봇입니다. Gemini 3.0 Flash와 Imagen 4를 사용하여 고품질의 시각적 단어 카드를 생성합니다.

## 🌟 주요 기능
- **스마트 단어 선정**: Gemini 3.0 Flash를 사용하여 중복되지 않는 오늘의 단어 9개 선정.
- **AI 일러스트 생성**: Imagen 4를 이용해 각 단어에 어울리는 미니멀 벡터 아이콘 생성.
- **전문적인 레이아웃**: Pillow 라이브러리로 텍스트와 이미지를 합성하여 깔끔한 3x3 격자 카드 완성.
- **자동화된 배포**: GitHub Actions를 통해 매일 오전 5시(KST) 텔레그램으로 자동 발송.
- **단어 목록 관리**: GitHub Issue에 `update-words` 라벨을 달아 단어를 입력하면 학습 목록(`learned_words.txt`) 자동 갱신.

## 🛠️ 기술 스택
- **언어**: Python 3.12
- **AI**: Google Generative AI (Gemini 3.0 Flash Preview, Imagen 4)
- **이미지 처리**: Pillow (PIL)
- **배포/자동화**: GitHub Actions, Telegram Bot API

## 📋 사용 가이드

### 1. 환경 변수 설정 (GitHub Secrets)
- `GEMINI_API_KEY`: Google AI Studio API Key
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
