# Daily Vocab Card Bot 🖋️🎨

AI 기반 매일 단어장 자동 생성 및 전송 봇입니다. OpenAI, Gemini 등 다양한 AI 제공자를 지원하며, 텍스트 기반 및 시각적 단어 카드를 자동으로 생성합니다.

## 🌟 주요 기능
- **스마트 단어 선정**: OpenAI(기본) 또는 Gemini를 사용하여 중복되지 않는 오늘의 단어 9개 선정.
- **AI 일러스트 생성**: OpenAI DALL-E(기본) 또는 Imagen을 이용해 각 단어에 어울리는 미니멀 벡터 아이콘 생성.
- **전문적인 레이아웃**: Pillow 라이브러리로 텍스트와 이미지를 합성하여 깔끔한 3x3 격자 카드 완성.
- **자동화된 배포**: 상주 manager bot의 scheduler 또는 GitHub Actions를 통해 매일 정해진 시간에 텔레그램으로 자동 발송.
- **다국어 지원**: 스페인어(ES), 일본어(JA), 중국어(ZH), 영어(EN) 네 가지 언어의 학습 콘텐츠 제공.
- **단어 목록 관리**: 언어별 학습 목록(`learned_data_*.json`) 자동 갱신 및 약점 단어 추적.

## 🛠️ 기술 스택
- **언어**: Python 3.12
- **AI**: OpenAI (기본), Google Generative AI Gemini (대체 가능)
- **텍스트음성변환**: Google Cloud Text-to-Speech (영어 회화/중국어 음성)
- **이미지 처리**: Pillow (PIL)
- **자동화**: Telegram Bot API, APScheduler, GitHub Actions

## 📋 사용 가이드

### 1. 환경 변수 설정

원격 서버(mh_bot@100.103.20.9) 또는 로컬 개발 환경에서 `~/.secrets/.env`에 다음을 설정하세요:

**필수**:
- `VOCAB_BOT_TOKEN`: 텔레그램 봇 토큰
- `VOCAB_CHAT_ID`: 단어 카드를 받을 텔레그램 채팅방 ID

**텍스트 생성 (기본 OpenAI)**:
- `OPENAI_API_KEY`: OpenAI API Key

**텍스트 생성 (대체 Gemini)**:
- `GEMINI_API_KEY`: Google AI Studio API Key
- `VOCAB_TEXT_PROVIDER=gemini` 설정하여 활성화

**이미지 생성 (기본 OpenAI DALL-E)**:
- OPENAI_API_KEY 사용

**이미지 생성 (대체 Imagen)**:
- `GEMINI_API_KEY` 사용
- `VOCAB_IMAGE_PROVIDER=imagen` 설정하여 활성화

**음성 합성** (선택, 영어 회화/중국어):
- `GOOGLE_APPLICATION_CREDENTIALS`: Google Cloud 서비스 계정 JSON 경로

### 2. 로컬 실행

```bash
# 스페인어 카드 즉시 생성
python spanish.py

# 일본어 카드 즉시 생성
python japanese.py

# 중국어 카드 즉시 생성
python chinese.py

# 영어 플루언시 전체 (단어+회화+선택)
python english_vocab.py
python english_dialogue.py

# Manager bot 상주 실행 (scheduler 포함)
python manager_bot.py
```

### 3. Manager Bot 사용

Manager bot은 `manager_bot.py`로 실행되며, 다음 기능을 제공합니다:

- `/start` 또는 `/manage`: 메뉴 표시
- `/run_es`, `/run_ja`, `/run_zh`: 언어별 즉시 실행
- 자동 스케줄:
  - 05:00 KST: 스페인어/일본어/중국어 카드
  - 05:10 KST: 각 언어별 보조 학습 콘텐츠
  - 06:00 KST: 영어 플루언시 (매일 vocab/dialogue + 월/수/금 phrase + 일요일 writing)

### 4. 학습 목록 수동 업데이트 방법

GitHub Issue 연동 업데이트 (선택사항):
1. GitHub Repository의 **Issues** 탭으로 이동.
2. `New Issue`를 클릭하고 제목 작성.
3. Labels에서 `update-words`를 선택.
4. 본문에 한 줄에 하나씩 단어를 입력 후 `Submit`.
5. 봇이 자동으로 단어를 추가하고 Issue를 닫습니다.

## 🤝 기여 및 문의
문의 사항은 Issue 또는 Pull Request를 통해 남겨주세요.
