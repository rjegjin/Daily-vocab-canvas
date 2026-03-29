"""
스페인어 단어 카드 생성기
word + IPA + 한국어 의미 + 예문
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
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))
load_dotenv(os.path.join(os.path.dirname(PROJECT_DIR), '.secrets', '.env'))

TOKEN   = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID')   or os.getenv('GEMINI_CHAT_ID')
API_KEY = os.getenv('GEMINI_API_KEY')
LEARNED_FILE = os.path.join(PROJECT_DIR, 'learned_words.txt')

if not API_KEY or not TOKEN or not CHAT_ID:
    print("❌ 환경 변수가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=API_KEY)

# 폰트
_DIR = os.path.dirname(os.path.abspath(__file__))
def load_fonts():
    return {
        'word':    ImageFont.truetype(os.path.join(_DIR, 'NotoSansKR-Bold.ttf'),    36),
        'ipa':     ImageFont.truetype(os.path.join(_DIR, 'NotoSans-Regular.ttf'),   20),
        'meaning': ImageFont.truetype(os.path.join(_DIR, 'NotoSansKR-Bold.ttf'),    26),
        'example': ImageFont.truetype(os.path.join(_DIR, 'NotoSansKR-Regular.ttf'), 15),
    }

def fields_fn(item, fonts):
    return [
        (item['word'],    fonts['word'],    (15, 15, 15),    44, False),
        (item['ipa'],     fonts['ipa'],     (130, 130, 130), 32, False),
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
    print("🧠 스페인어 단어 데이터 생성 중...")
    exclude = f"CRITICAL: DO NOT use any of these words: {', '.join(learned[-300:])}." if learned else ""
    prompt = f"""
    Create a JSON array of 9 Spanish vocabulary words for daily learning.
    Provide a mix of categories (emotions, nature, objects, actions, etc.).
    {exclude}

    For each word, provide:
    - "word": The Spanish word
    - "ipa": The IPA pronunciation
    - "meaning": The English meaning (1-3 words)
    - "example": A short, simple Spanish example sentence (max 8 words).

    Output strictly valid JSON. No markdown formatting, just the raw JSON array.
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
    print(f"=== 🇪🇸 Spanish Vocab Card ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    learned = load_learned()
    print(f"📚 학습한 단어: {len(learned)}개")

    vocab, txt_in, txt_out = generate_vocab(learned)
    if not vocab: exit(1)

    icons = generate_icons(client, vocab, lang='es', lang_hint='Spanish',
                           txt_in_tokens=txt_in, txt_out_tokens=txt_out)

    fonts = load_fonts()
    out = os.path.join(PROJECT_DIR, "final_flashcard.png")
    result = create_flashcard(icons, vocab, fields_fn, fonts, out)

    if result and os.path.exists(result):
        send_to_telegram(result, TOKEN, CHAT_ID)
        save_learned([d['word'] for d in vocab])
        print("💾 9개 단어 저장 완료")
    else:
        print("⚠️ 이미지 생성 실패, 전송 건너뜀")
