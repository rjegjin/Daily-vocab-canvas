import os
import io
import json
import requests
import textwrap
import concurrent.futures
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

# -------------------------------------------------------------------
# 1. 환경 변수 및 설정
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.join(BASE_DIR, 'Daily_Vocab_Card_Bot')
SECRET_PATH = os.path.join(BASE_DIR, '.secrets', '.env')
load_dotenv(SECRET_PATH)

TELEGRAM_TOKEN = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID') or os.getenv('GEMINI_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
LEARNED_WORDS_FILE = os.path.join(PROJECT_DIR, 'learned_words.txt')

if not GEMINI_API_KEY or not TELEGRAM_TOKEN or not CHAT_ID:
    print("❌ API 키 또는 텔레그램 토큰/Chat ID가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# 카드 레이아웃 상수
CARD_SIZE   = 1080          # 전체 카드 크기 (정사각형)
GRID        = 3             # 3x3
CELL_SIZE   = CARD_SIZE // GRID   # 360px
TEXT_RATIO  = 0.55          # 텍스트 영역 비율
TEXT_H      = int(CELL_SIZE * TEXT_RATIO)   # 198px
ICON_H      = CELL_SIZE - TEXT_H            # 162px

# -------------------------------------------------------------------
# 1.5 중복 방지
# -------------------------------------------------------------------
def load_learned_words():
    if os.path.exists(LEARNED_WORDS_FILE):
        with open(LEARNED_WORDS_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_learned_words(new_words):
    with open(LEARNED_WORDS_FILE, 'a', encoding='utf-8') as f:
        for w in new_words:
            f.write(w + '\n')

# -------------------------------------------------------------------
# 2. 단어 데이터 생성 (Gemini)
# -------------------------------------------------------------------
def generate_vocab_data(learned_words):
    print("🧠 Gemini로 오늘의 단어 데이터를 생성 중...")

    exclude_text = ""
    if learned_words:
        recent = learned_words[-300:]
        exclude_text = f"CRITICAL: DO NOT use any of these words: {', '.join(recent)}."

    prompt = f"""
    Create a JSON array of 9 Spanish vocabulary words for daily learning.
    Provide a mix of categories (emotions, nature, objects, actions, etc.).
    {exclude_text}

    For each word, provide:
    - "word": The Spanish word (e.g., "Girasol")
    - "ipa": The IPA pronunciation (e.g., "[xiɾaˈsol]")
    - "meaning": The Korean meaning (e.g., "해바라기")
    - "example": A short, simple Spanish example sentence (max 8 words).

    Output strictly valid JSON. No markdown formatting, just the raw JSON array.
    """

    def parse_response(response):
        raw = response.text.strip()
        if raw.startswith("```json"): raw = raw[7:]
        if raw.endswith("```"): raw = raw[:-3]
        return json.loads(raw.strip())

    for model in ['gemini-3.1-flash-lite-preview', 'gemini-2.5-flash']:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            vocab_list = parse_response(response)
            print(f"✅ 단어 9개 생성 완료 ({model}): {[v['word'] for v in vocab_list]}")
            return vocab_list
        except Exception as e:
            print(f"⚠️ {model} 실패: {e}")
    print("❌ 단어 생성 실패")
    return None

# -------------------------------------------------------------------
# 3. 아이콘 개별 생성 (Imagen 4, 병렬)
# -------------------------------------------------------------------
def generate_single_icon(word):
    prompt = (
        f"A single minimalist flat design icon representing '{word}'. "
        "Clean vector art style, soft pastel colors, centered on a pure white background. "
        "NO TEXT, NO LETTERS, NO LABELS, NO NUMBERS."
    )
    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-image-preview',
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=['IMAGE'])
        )
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                # 중앙 정사각형 크롭 후 ICON_H x ICON_H 리사이즈 (비율 유지)
                w, h = img.size
                s = min(w, h)
                left, top = (w - s) // 2, (h - s) // 2
                img = img.crop((left, top, left + s, top + s))
                return img.resize((ICON_H, ICON_H), Image.LANCZOS)
        return None
    except Exception as e:
        print(f"  ⚠️ '{word}' 아이콘 생성 실패: {e}")
        return None

def generate_icons(vocab_data):
    print(f"🎨 Gemini로 아이콘 {len(vocab_data)}개를 병렬 생성 중...")
    words = [item['word'] for item in vocab_data]
    icons = [None] * len(words)

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
        future_to_idx = {executor.submit(generate_single_icon, w): i for i, w in enumerate(words)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            icons[idx] = future.result()
            status = "✅" if icons[idx] else "❌"
            print(f"  {status} [{idx+1}/9] {words[idx]}")

    success = sum(1 for ic in icons if ic is not None)
    print(f"🎨 아이콘 생성 완료: {success}/{len(words)}개 성공")
    return icons

# -------------------------------------------------------------------
# 4. 플래시카드 합성 (Pillow)
# -------------------------------------------------------------------
def create_flashcard(icons, vocab_data):
    print("🖋️ 플래시카드 합성 중...")
    try:
        canvas = Image.new("RGB", (CARD_SIZE, CARD_SIZE), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        font_dir = os.path.dirname(os.path.abspath(__file__))
        font_word    = ImageFont.truetype(os.path.join(font_dir, "NotoSansKR-Bold.ttf"),    36)
        font_ipa     = ImageFont.truetype(os.path.join(font_dir, "NotoSans-Regular.ttf"),   20)
        font_meaning = ImageFont.truetype(os.path.join(font_dir, "NotoSansKR-Bold.ttf"),    26)
        font_example = ImageFont.truetype(os.path.join(font_dir, "NotoSansKR-Regular.ttf"), 15)

        BORDER_COLOR = (220, 220, 220)
        PAD = int(CELL_SIZE * 0.06)   # 상단 여백 ~21px

        for i, (item, icon) in enumerate(zip(vocab_data, icons)):
            col = i % GRID
            row = i // GRID
            x0  = col * CELL_SIZE
            y0  = row * CELL_SIZE

            # --- 아이콘 영역 ---
            icon_y = y0 + TEXT_H
            if icon:
                # ICON_H x ICON_H 정사각형 아이콘을 셀 가로 중앙에 배치
                icon_x = x0 + (CELL_SIZE - ICON_H) // 2
                icon_top = icon_y + (ICON_H - ICON_H) // 2  # 수직 중앙 (여백 있으면 조정)
                canvas.paste(icon.convert("RGB"), (icon_x, icon_top), icon)
            else:
                # 생성 실패 시 회색 플레이스홀더
                draw.rectangle([x0, icon_y, x0 + CELL_SIZE, y0 + CELL_SIZE], fill=(240, 240, 240))

            # --- 텍스트 영역 흰색 ---
            draw.rectangle([x0, y0, x0 + CELL_SIZE, icon_y], fill=(255, 255, 255))

            # --- 셀 경계선 ---
            draw.rectangle([x0, y0, x0 + CELL_SIZE - 1, y0 + CELL_SIZE - 1], outline=BORDER_COLOR, width=1)
            # 텍스트/아이콘 구분선
            draw.line([(x0, icon_y), (x0 + CELL_SIZE, icon_y)], fill=BORDER_COLOR, width=1)

            # --- 텍스트 렌더링 헬퍼 ---
            def draw_centered(abs_y, text, font, fill=(20, 20, 20)):
                if abs_y + 4 >= y0 + TEXT_H:
                    return
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                draw.text((x0 + (CELL_SIZE - tw) // 2, abs_y), text, font=font, fill=fill)

            def draw_wrapped(abs_y, text, font, line_h, fill=(90, 90, 90)):
                for line in textwrap.wrap(text, width=24):
                    if abs_y + 4 >= y0 + TEXT_H:
                        break
                    draw_centered(abs_y, line, font, fill)
                    abs_y += line_h

            # --- 텍스트 배치 ---
            draw_centered(y0 + PAD,            item['word'],    font_word,    fill=(15, 15, 15))
            draw_centered(y0 + PAD + 44,       item['ipa'],     font_ipa,     fill=(140, 140, 140))
            draw_centered(y0 + PAD + 70,       item['meaning'], font_meaning, fill=(30, 30, 30))
            draw_wrapped (y0 + PAD + 104,      item['example'], font_example, line_h=20)

        final_path = os.path.join(PROJECT_DIR, "final_flashcard.png")
        canvas.save(final_path, "PNG", quality=95)
        print(f"✅ 최종 합성 완료: {final_path}")
        return final_path

    except Exception as e:
        print(f"❌ 합성 중 오류: {e}")
        return None

# -------------------------------------------------------------------
# 5. 텔레그램 전송
# -------------------------------------------------------------------
def send_to_telegram(image_path):
    print("📤 텔레그램으로 전송 중...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

    class IPAdapter(requests.adapters.HTTPAdapter):
        def send(self, request, **kwargs):
            request.url = request.url.replace("api.telegram.org", "149.154.167.220")
            request.headers["Host"] = "api.telegram.org"
            return super().send(request, **kwargs)

    session = requests.Session()
    session.mount("https://", IPAdapter())
    session.verify = False

    try:
        with open(image_path, 'rb') as photo:
            response = session.post(url, data={'chat_id': CHAT_ID}, files={'photo': photo})
        result = response.json()
        if result.get("ok"):
            print(f"[{datetime.now()}] 🚀 카드를 성공적으로 보냈습니다!")
        else:
            print(f"❌ 전송 실패: {result}")
    except Exception as e:
        print(f"❌ 전송 오류: {e}")

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== 🌟 Daily Vocab Card Generator 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    learned_words = load_learned_words()
    print(f"📚 지금까지 학습한 단어 수: {len(learned_words)}개")

    vocab_data = generate_vocab_data(learned_words)
    if not vocab_data: exit(1)

    icons = generate_icons(vocab_data)

    final_img = create_flashcard(icons, vocab_data)

    if final_img and os.path.exists(final_img):
        send_to_telegram(final_img)
        save_learned_words([item['word'] for item in vocab_data])
        print("💾 새로운 단어 9개가 저장되었습니다.")
    else:
        print("⚠️ 최종 이미지가 생성되지 않아 전송을 건너뜁니다.")
