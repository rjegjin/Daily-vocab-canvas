"""
중국어 단어 카드 생성기
단어(한자) + 병음(pinyin) + 한국어 의미 + 예문
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from PIL import ImageFont

from card_engine import generate_icons, create_flashcard, send_to_telegram

# -------------------------------------------------------------------
# 환경 변수
# -------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.join(BASE_DIR, 'Daily_Vocab_Card_Bot')
load_dotenv(os.path.join(BASE_DIR, '.secrets', '.env'))

TOKEN   = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID')   or os.getenv('GEMINI_CHAT_ID')
API_KEY = os.getenv('GEMINI_API_KEY')
LEARNED_FILE = os.path.join(PROJECT_DIR, 'learned_zh.txt')

if not API_KEY or not TOKEN or not CHAT_ID:
    print("❌ 환경 변수가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=API_KEY)

# 폰트 경로
TTC_REG  = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
TTC_BOLD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
KR_BOLD  = os.path.join(PROJECT_DIR, 'NotoSansKR-Bold.ttf')
ZH_IDX   = 2   # NotoSansCJK SC (Simplified Chinese) index

def load_fonts():
    return {
        'word':    ImageFont.truetype(TTC_BOLD, 38, index=ZH_IDX),
        'pinyin':  ImageFont.truetype(TTC_REG,  20, index=ZH_IDX),
        'meaning': ImageFont.truetype(KR_BOLD,  26),
        'example': ImageFont.truetype(TTC_REG,  15, index=ZH_IDX),
    }

def fields_fn(item, fonts):
    # (text, font, fill, spacing_to_next, wrap)
    return [
        (item['word'],    fonts['word'],    (15, 15, 15),    44, False),
        (item['pinyin'],  fonts['pinyin'],  (200, 80, 80),   32, False),
        (item['meaning'], fonts['meaning'], (30, 30, 30),    34, False),
        (item['example'], fonts['example'], (90, 90, 90),    20, True),
    ]

# -------------------------------------------------------------------
# 단어 데이터 생성
# -------------------------------------------------------------------
def load_learned():
    if os.path.exists(LEARNED_FILE):
        with open(LEARNED_FILE, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f if l.strip()]
    return []

def save_learned(words):
    with open(LEARNED_FILE, 'a', encoding='utf-8') as f:
        for w in words: f.write(w + '\n')

def generate_vocab(learned):
    print("🧠 중국어 단어 데이터 생성 중...")
    exclude = f"제외 단어: {', '.join(learned[-200:])}." if learned else ""
    prompt = f"""
    중국어(보통화) 어휘 학습용 JSON 배열을 9개 만들어줘. 감정, 자연, 사물, 동작 등 다양하게.
    {exclude}

    각 항목:
    - "word": 간체자 표기 (예: "樱花")
    - "pinyin": 성조 포함 병음 (예: "yīng huā")
    - "meaning": 한국어 뜻 (예: "벚꽃")
    - "example": 짧은 중국어 예문 (10자 이내)

    마크다운 없이 순수 JSON 배열만 출력.
    """
    def parse(r):
        t = r.text.strip()
        if t.startswith("```json"): t = t[7:]
        if t.endswith("```"): t = t[:-3]
        return json.loads(t.strip())

    for model in ['gemini-3.1-flash-lite-preview', 'gemini-2.5-flash']:
        try:
            r = client.models.generate_content(model=model, contents=prompt)
            data = parse(r)
            u = r.usage_metadata
            print(f"✅ 단어 9개 생성 완료 ({model}): {[d['word'] for d in data]}")
            return data, u.prompt_token_count, u.candidates_token_count
        except Exception as e:
            print(f"⚠️ {model} 실패: {e}")
    return None, 0, 0

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== 🇨🇳 Chinese Vocab Card ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    learned = load_learned()
    print(f"📚 학습한 단어: {len(learned)}개")

    vocab, txt_in, txt_out = generate_vocab(learned)
    if not vocab: exit(1)

    icons = generate_icons(client, vocab, lang='zh', lang_hint='Chinese',
                           txt_in_tokens=txt_in, txt_out_tokens=txt_out)

    fonts = load_fonts()
    out = os.path.join(PROJECT_DIR, "flashcard_zh.png")
    result = create_flashcard(icons, vocab, fields_fn, fonts, out)

    if result and os.path.exists(result):
        send_to_telegram(result, TOKEN, CHAT_ID)
        save_learned([d['word'] for d in vocab])
        print("💾 9개 단어 저장 완료")
    else:
        print("⚠️ 이미지 생성 실패, 전송 건너뜀")
