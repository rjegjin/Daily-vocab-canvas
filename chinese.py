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

from card_engine import generate_icons, create_flashcard, send_to_telegram, check_budget_exit, generate_tts, send_audio_to_telegram, generate_vocab_openai
from vocab_feedback import save_latest_vocab, send_feedback_buttons

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
LEARNED_FILE = os.path.join(PROJECT_DIR, 'learned_zh.txt')

if (TEXT_PROVIDER != 'openai' and not API_KEY) or not TOKEN or not CHAT_ID:
    print("❌ 환경 변수가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=API_KEY) if API_KEY else None

# 폰트 경로
TTC_REG  = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
TTC_BOLD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
KR_BOLD  = os.path.join(PROJECT_DIR, 'NotoSansKR-Bold.ttf')
ZH_IDX   = 2   # NotoSansCJK SC (Simplified Chinese) index
ZH_TC_IDX = 3  # NotoSansCJK TC (Traditional Chinese) index

def load_fonts():
    return {
        'word':    ImageFont.truetype(TTC_BOLD, 38, index=ZH_IDX),
        'traditional': ImageFont.truetype(TTC_REG, 18, index=ZH_TC_IDX),
        'pinyin':  ImageFont.truetype(TTC_REG,  20, index=ZH_IDX),
        'meaning': ImageFont.truetype(KR_BOLD,  26),
        'example': ImageFont.truetype(TTC_REG,  15, index=ZH_IDX),
    }

def fields_fn(item, fonts):
    # (text, font, fill, spacing_to_next, wrap)
    traditional = item.get('traditional', '')
    if traditional == item.get('word'):
        traditional = ''
    return [
        (item['word'],    fonts['word'],    (15, 15, 15),    48, False),
        (traditional, fonts['traditional'], (130, 105, 105), 20, False),
        (item['pinyin'],  fonts['pinyin'],  (200, 80, 80),   28, False),
        (item['meaning'], fonts['meaning'], (30, 30, 30),    32, False),
        (item['example'], fonts['example'], (90, 90, 90),    18, True),
    ]

# -------------------------------------------------------------------
# 단어 데이터 생성 (JSON 기반)
# -------------------------------------------------------------------
LEARNED_JSON_FILE = os.path.join(PROJECT_DIR, 'learned_data_zh.json')
REQUIRED_KEYS = {'word', 'traditional', 'pinyin', 'meaning', 'example', 'category', 'visual'}

def extract_json_array(text):
    """Gemini sometimes wraps JSON in markdown or appends explanations."""
    t = text.strip()
    if t.startswith("```json"):
        t = t[7:]
    elif t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()

    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        start = t.find("[")
        end = t.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(t[start:end + 1])

    if isinstance(data, dict):
        for key in ("words", "items", "vocab", "vocabulary", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        lists = [value for value in data.values() if isinstance(value, list)]
        if len(lists) == 1:
            return lists[0]
    return data

def load_learned_json():
    """learned_data_zh.json에서 단어 목록 로드"""
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
    print("🧠 중국어 단어 데이터 생성 중...")
    exclude = f"제외 단어: {', '.join(learned[-200:])}." if learned else ""

    weak_instruction = ""
    if weak_words:
        weak_instruction = f"\n⚠️ 중요: 다음 복습 단어들을 2-3개 포함해줘: {', '.join(weak_words[:5])}"

    prompt = f"""
    중국어(보통화) 어휘 학습용 JSON 배열을 9개 만들어줘. 감정, 자연, 사물, 동작 등 다양하게.
    {exclude}
    {weak_instruction}

    각 항목:
    - "word": 간체자 표기 (예: "樱花")
    - "traditional": 번체자 표기 (예: "櫻花"). 간체자와 같아도 반드시 적어줘.
    - "pinyin": 성조 포함 병음 (예: "yīng huā")
    - "meaning": 한국어 의미 1~3단어 (예: "벚꽃")
    - "example": 짧은 중국어 예문 (10자 이내)
    - "category": emotion, nature, object, action, food, animal, body, concept, place, time 중 하나
    - "visual": 아이콘으로 그릴 구체적인 영어 시각 힌트 2~5단어.
      반드시 눈에 보이는 사물/동작만 영어로 써줘. 예: "sleepy face", "iceberg", "theater masks".
      중국어 문자, 한자, 병음, 숫자는 절대 넣지 마.

    마크다운 없이 순수 JSON 배열만 출력.
    """
    def parse(r):
        data = extract_json_array(r.text)
        if not isinstance(data, list) or len(data) != 9:
            raise ValueError("Gemini 응답이 9개 JSON 배열이 아닙니다.")
        for idx, item in enumerate(data, start=1):
            missing = REQUIRED_KEYS - set(item)
            if missing:
                raise ValueError(f"{idx}번째 항목 필수 필드 누락: {sorted(missing)}")
        return data

    if TEXT_PROVIDER == 'openai':
        try:
            data, txt_in, txt_out = generate_vocab_openai(prompt, REQUIRED_KEYS, 'zh')
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

def send_vocab_tts(vocab, weak_words):
    weak_set = set(weak_words or [])
    priority = [item for item in vocab if item.get('word') in weak_set]
    selected = priority + [item for item in vocab if item.get('word') not in weak_set]
    selected = selected[:9]
    if not selected:
        return
    script = "。 ".join(
        f"{item['word']}，{item['example']}"
        for item in selected
        if item.get('word') and item.get('example')
    )
    if not script:
        return
    audio_path = os.path.join(PROJECT_DIR, "vocab_zh_pronunciation.mp3")
    if generate_tts(script, 'cmn-CN', audio_path):
        caption = "🎧 중국어 예문 발음 — 오늘의 9개 전체"
        send_audio_to_telegram(audio_path, TOKEN, CHAT_ID, caption=caption)
        if os.path.exists(audio_path):
            os.remove(audio_path)

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
if __name__ == "__main__":
    check_budget_exit('zh')
    print(f"=== 🇨🇳 Chinese Vocab Card ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    # JSON 파일 기반 로드 (마이그레이션 후) 또는 TXT 파일 (마이그레이션 전)
    learned = load_learned_json() if os.path.exists(LEARNED_JSON_FILE) else load_learned()
    weak_words = load_weak_words() if os.path.exists(LEARNED_JSON_FILE) else []

    print(f"📚 학습한 단어: {len(learned)}개")
    if weak_words:
        print(f"⚠️ 취약 단어: {len(weak_words)}개 (복습 대상)")

    vocab, txt_in, txt_out = generate_vocab(learned, weak_words)
    if not vocab: exit(1)

    icons = generate_icons(client, vocab, lang='zh', lang_hint='Chinese',
                           txt_in_tokens=txt_in, txt_out_tokens=txt_out)

    fonts = load_fonts()
    out = os.path.join(PROJECT_DIR, "flashcard_zh.png")
    result = create_flashcard(icons, vocab, fields_fn, fonts, out, theme='zh')

    if result and os.path.exists(result):
        send_to_telegram(result, TOKEN, CHAT_ID)

        from card_engine import save_vocab_to_json
        save_vocab_to_json(LEARNED_JSON_FILE, vocab)
        save_latest_vocab('zh', vocab)
        send_feedback_buttons('zh')
        send_vocab_tts(vocab, weak_words)
        print("💾 9개 단어 JSON 저장 완료")
    else:
        print("⚠️ 이미지 생성 실패, 전송 건너뜀")
