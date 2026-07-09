"""
스페인어 단어 카드 생성기
word + IPA + English meaning + example
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from PIL import ImageFont

from card_engine import generate_icons, create_flashcard, send_to_telegram, check_budget_exit, generate_vocab_openai

# -------------------------------------------------------------------
# 환경 변수
# -------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))
load_dotenv(os.path.join(os.path.dirname(PROJECT_DIR), '.secrets', '.env'))

TOKEN   = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID')   or os.getenv('GEMINI_CHAT_ID')
API_KEY = os.getenv('GEMINI_API_KEY')
TEXT_PROVIDER = os.getenv('VOCAB_TEXT_PROVIDER', 'openai').lower()
LEARNED_FILE = os.path.join(PROJECT_DIR, 'learned_words.txt')

if (TEXT_PROVIDER != 'openai' and not API_KEY) or not TOKEN or not CHAT_ID:
    print("❌ 환경 변수가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=API_KEY) if API_KEY else None

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
# 단어 데이터 생성 (JSON 기반)
# -------------------------------------------------------------------
LEARNED_JSON_FILE = os.path.join(PROJECT_DIR, 'learned_data_es.json')
REQUIRED_KEYS = {'word', 'ipa', 'meaning', 'example', 'category', 'visual'}

def load_learned_json():
    """learned_data_es.json에서 단어 목록 로드"""
    if os.path.exists(LEARNED_JSON_FILE):
        with open(LEARNED_JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [item['word'] for item in data]
    return []

def load_weak_words():
    """weak=True인 단어들 로드"""
    if os.path.exists(LEARNED_JSON_FILE):
        with open(LEARNED_JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [item['word'] for item in data if item.get('weak')]
    return []

def load_learned():
    """Fallback: TXT 파일에서 로드 (마이그레이션 전)"""
    if os.path.exists(LEARNED_FILE):
        with open(LEARNED_FILE, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f if l.strip()]
    return []

def generate_vocab(learned, weak_words=None):
    print("🧠 스페인어 단어 데이터 생성 중...")

    exclude = f"CRITICAL: DO NOT use any of these words: {', '.join(learned[-300:])}." if learned else ""

    # weak 단어 우선 포함 (복습 목표)
    weak_instruction = ""
    if weak_words:
        weak_instruction = f"\n⚠️ IMPORTANT: Try to include 2-3 of these weak words for review: {', '.join(weak_words[:5])}"

    prompt = f"""
    Create a JSON array of 9 Spanish vocabulary words for daily learning.
    Provide a mix of categories (emotions, nature, objects, actions, etc.).
    {exclude}
    {weak_instruction}

    For each word, provide:
    - "word": The Spanish word
    - "ipa": The IPA pronunciation
    - "meaning": English meaning (1-3 words, e.g. "joy", "cold wind")
    - "example": A short, simple Spanish example sentence (max 8 words)
    - "category": One of: emotion, nature, object, action, food, animal, body, concept, place, time
    - "visual": A concrete English visual phrase for drawing an icon (2-5 words, no Spanish text).
      Use visible objects/actions only, e.g. "bright spark", "walking feet", "wooden cabin".

    Output strictly valid JSON. No markdown formatting, just the raw JSON array.
    """
    def parse(r):
        t = r.text.strip()
        if t.startswith("```json"): t = t[7:]
        if t.endswith("```"): t = t[:-3]
        data = json.loads(t.strip())
        if not isinstance(data, list) or len(data) != 9:
            raise ValueError("Gemini 응답이 9개 JSON 배열이 아닙니다.")
        for idx, item in enumerate(data, start=1):
            missing = REQUIRED_KEYS - set(item)
            if missing:
                raise ValueError(f"{idx}번째 항목 필수 필드 누락: {sorted(missing)}")
        return data

    if TEXT_PROVIDER == 'openai':
        try:
            data, txt_in, txt_out = generate_vocab_openai(prompt, REQUIRED_KEYS, 'es')
            return data, txt_in, txt_out
        except Exception as e:
            print(f"⚠️ OpenAI 단어 생성 실패: {e}")
            return None, 0, 0

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
    check_budget_exit('es')
    print(f"=== 🇪🇸 Spanish Vocab Card ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    # JSON 파일 기반 로드 (마이그레이션 후) 또는 TXT 파일 (마이그레이션 전)
    learned = load_learned_json() if os.path.exists(LEARNED_JSON_FILE) else load_learned()
    weak_words = load_weak_words() if os.path.exists(LEARNED_JSON_FILE) else []

    print(f"📚 학습한 단어: {len(learned)}개")
    if weak_words:
        print(f"⚠️ 취약 단어: {len(weak_words)}개 (복습 대상)")

    vocab, txt_in, txt_out = generate_vocab(learned, weak_words)
    if not vocab: exit(1)

    icons = generate_icons(client, vocab, lang='es', lang_hint='Spanish',
                           txt_in_tokens=txt_in, txt_out_tokens=txt_out)

    fonts = load_fonts()
    out = os.path.join(PROJECT_DIR, "final_flashcard.png")
    result = create_flashcard(icons, vocab, fields_fn, fonts, out, theme='es')

    if result and os.path.exists(result):
        send_to_telegram(result, TOKEN, CHAT_ID)

        from card_engine import save_vocab_to_json
        save_vocab_to_json(LEARNED_JSON_FILE, vocab)
        print("💾 9개 단어 JSON 저장 완료")
    else:
        print("⚠️ 이미지 생성 실패, 전송 건너뜀")
