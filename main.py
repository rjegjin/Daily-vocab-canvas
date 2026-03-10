import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
import textwrap

# -------------------------------------------------------------------
# 1. 환경 변수 및 설정
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.join(BASE_DIR, 'Daily_Vocab_Card_Bot')
SECRET_PATH = os.path.join(BASE_DIR, '.secrets', '.env')
load_dotenv(SECRET_PATH)

# GitHub Actions 환경 변수 지원 추가
TELEGRAM_TOKEN = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID') or os.getenv('GEMINI_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
LEARNED_WORDS_FILE = os.path.join(PROJECT_DIR, 'learned_words.txt')

if not GEMINI_API_KEY or not TELEGRAM_TOKEN or not CHAT_ID:
    print("❌ API 키 또는 텔레그램 토큰/Chat ID가 설정되지 않았습니다.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# -------------------------------------------------------------------
# 1.5 중복 방지 (기존 학습 단어 로드)
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
# 2. 단어 데이터 (JSON) 생성 (Gemini 3.0 Flash)
# -------------------------------------------------------------------
def generate_vocab_data(learned_words):
    print("🧠 Gemini 모델을 통해 오늘의 단어 데이터를 생성 중...")
    
    exclude_text = ""
    if learned_words:
        # 단어 수가 너무 많을 경우 최근 300개 정도만 프롬프트에 포함하여 토큰 낭비 방지
        recent_learned = learned_words[-300:] 
        exclude_text = f"CRITICAL: DO NOT use any of these words: {', '.join(recent_learned)}."

    prompt = f"""
    Create a JSON array of 9 Spanish vocabulary words for daily learning.
    Provide a mix of categories (emotions, nature, objects, actions, etc.).
    {exclude_text}
    
    For each word, provide:
    - "word": The Spanish word (e.g., "Girasol")
    - "ipa": The IPA pronunciation (e.g., "[xiɾaˈsol]")
    - "meaning": The Korean meaning (e.g., "해바라기")
    - "example": A short, simple Spanish example sentence.
    
    Output strictly valid JSON. No markdown formatting, just the raw JSON array.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.0-flash', # User specified 3.0
            contents=prompt
        )
        
        # Clean up markdown if model still outputs it
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        vocab_list = json.loads(raw_text.strip())
        print(f"✅ 9개의 단어 데이터 생성 완료: {[v['word'] for v in vocab_list]}")
        return vocab_list
    except Exception as e:
        print(f"⚠️ Gemini 3.0 모델 오류 또는 파싱 실패: {e}. 2.0으로 폴백 시도...")
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]
            vocab_list = json.loads(raw_text.strip())
            return vocab_list
        except Exception as e2:
            print(f"❌ Gemini 2.0 폴백도 실패: {e2}")
            return None

# -------------------------------------------------------------------
# 3. 배경 일러스트 생성 (Imagen 4)
# -------------------------------------------------------------------
def generate_background_grid(vocab_data):
    print("🎨 Imagen 4 모델을 통해 텍스트 없는 3x3 일러스트 그리드 생성 중...")
    
    image_path = os.path.join(PROJECT_DIR, "raw_background.png")
    
    # 각 단어에 맞춘 묘사를 포함하여 프롬프트 구성 (단순화 및 일관성 강조)
    illustrations_desc = []
    for i, item in enumerate(vocab_data):
        illustrations_desc.append(f"Cell {i+1}: '{item['word']}'")

    prompt_text = f"""
    Create a strict 3x3 grid of 9 minimalist illustrations.
    Style: Simple, clean, modern 2D vector flat design icons. 
    Aesthetic: Consistent line weight, vibrant but soft colors, isolated subjects on a solid WHITE background.
    Layout: 9 equal square cells. NO TEXT, NO BORDERS, NO WATERMARKS.
    
    Subjects:
    {', '.join(illustrations_desc)}
    
    Instructions: Each subject should be centered within its respective cell. 
    The top half of each cell MUST be left as empty white space for text overlay.
    Maintain high quality and professional layout.
    """
    
    try:
        result = client.models.generate_images(
            model='imagen-4.0-generate-001',
            prompt=prompt_text,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/png",
                aspect_ratio="1:1"
            )
        )
        
        generated_image = result.generated_images[0]
        with open(image_path, 'wb') as f:
            f.write(generated_image.image.image_bytes)
            
        print(f"✅ 배경 이미지 생성 완료: {image_path}")
        return image_path
        
    except Exception as e:
        print(f"❌ 이미지 생성 중 오류 발생: {e}")
        return None

# -------------------------------------------------------------------
# 4. 이미지와 텍스트 합성 (Pillow)
# -------------------------------------------------------------------
def overlay_text_on_image(bg_image_path, vocab_data):
    print("🖋️ 생성된 이미지 위에 텍스트를 합성하는 중...")
    
    try:
        # 배경 로드 (RGBA)
        raw_bg = Image.open(bg_image_path).convert("RGBA")
        img_w, img_h = raw_bg.size
        
        # 완벽한 3x3 그리드를 위한 새로운 레이어 생성
        final_canvas = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(final_canvas)
        
        cell_w = img_w // 3
        cell_h = img_h // 3
        
        # 폰트 설정
        font_dir = os.path.dirname(os.path.abspath(__file__))
        bold_font_path = os.path.join(font_dir, "NotoSansKR-Bold.ttf")
        reg_font_path = os.path.join(font_dir, "NotoSansKR-Regular.ttf")
        ipa_font_path = os.path.join(font_dir, "NotoSans-Regular.ttf")
        
        font_word = ImageFont.truetype(bold_font_path, 40)
        font_ipa = ImageFont.truetype(ipa_font_path, 24)
        font_meaning = ImageFont.truetype(bold_font_path, 28)
        font_example = ImageFont.truetype(reg_font_path, 18)
        
        for i, item in enumerate(vocab_data):
            if i >= 9: break
            
            row = i // 3
            col = i % 3
            x0 = col * cell_w
            y0 = row * cell_h
            
            # 1. 원본 이미지에서 해당 셀의 하단 절반만 추출하여 합성 (위쪽은 화이트박스로 덮음)
            # AI가 그린 그리드가 부정확할 수 있으므로, 각 셀 중앙에서 안전하게 크롭
            icon_area = (x0, y0 + cell_h // 2, x0 + cell_w, y0 + cell_h)
            icon_img = raw_bg.crop(icon_area)
            final_canvas.paste(icon_img, (x0, y0 + cell_h // 2))
            
            # 2. 상단 텍스트 영역 (순백색 고정)
            draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h // 2], fill=(255, 255, 255, 255))
            
            # 3. 셀 테두리 (깔끔한 현대적 느낌의 아주 연한 회색)
            draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=(230, 230, 230, 255), width=1)
            
            # 중앙 정렬 텍스트 함수
            def draw_centered(y_offset, text, font, fill=(0, 0, 0, 255)):
                bbox = draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                draw.text((x0 + (cell_w - w) // 2, y0 + y_offset), text, font=font, fill=fill)
            
            def draw_wrapped_centered(y_offset, text, font, fill=(80, 80, 80, 255)):
                lines = textwrap.wrap(text, width=28)
                curr_y = y_offset
                for line in lines:
                    draw_centered(curr_y, line, font, fill)
                    curr_y += 24
            
            # 텍스트 배치
            draw_centered(25, item['word'], font_word, fill=(0, 0, 0, 255))
            draw_centered(75, item['ipa'], font_ipa, fill=(120, 120, 120, 255))
            draw_centered(105, item['meaning'], font_meaning, fill=(20, 20, 20, 255))
            draw_wrapped_centered(140, item['example'], font_example)
            
        final_path = os.path.join(PROJECT_DIR, "final_flashcard.png")
        final_canvas.convert("RGB").save(final_path, "PNG", quality=95)
        
        print(f"✅ 최종 합성 완료: {final_path}")
        return final_path
        
    except Exception as e:
        print(f"❌ 텍스트 합성 중 오류 발생: {e}")
        return None

# -------------------------------------------------------------------
# 5. 텔레그램으로 전송 (DNS 우회 패치 포함)
# -------------------------------------------------------------------
def send_to_telegram(image_path):
    print("📤 텔레그램으로 이미지를 전송하는 중...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    # DNS 우회 패치 (일부 환경용)
    import urllib3
    from urllib3.util.ssl_ import create_urllib3_context
    class CustomHostAdapter(requests.adapters.HTTPAdapter):
        def send(self, request, **kwargs):
            request.url = request.url.replace("api.telegram.org", "149.154.167.220")
            request.headers["Host"] = "api.telegram.org"
            return super(CustomHostAdapter, self).send(request, **kwargs)
    
    session = requests.Session()
    session.mount("https://", CustomHostAdapter())
    session.verify = False 
    
    try:
        with open(image_path, 'rb') as photo:
            payload = {'chat_id': CHAT_ID}
            files = {'photo': photo}
            response = session.post(url, data=payload, files=files)
            
        result = response.json()
        if result.get("ok"):
            print(f"[{datetime.now()}] 🚀 카드를 성공적으로 보냈습니다!")
        else:
            print(f"❌ 텔레그램 전송 실패: {result}")
    except Exception as e:
        print(f"❌ 텔레그램 전송 중 오류 발생: {e}")

# -------------------------------------------------------------------
# 메인 실행 흐름
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== 🌟 Daily Vocab Card Generator 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    learned_words = load_learned_words()
    print(f"📚 지금까지 학습한 단어 수: {len(learned_words)}개")

    vocab_data = generate_vocab_data(learned_words)
    if not vocab_data: exit(1)
        
    bg_image = generate_background_grid(vocab_data)
    if not bg_image: exit(1)
        
    final_img = overlay_text_on_image(bg_image, vocab_data)
    
    if final_img and os.path.exists(final_img):
        send_to_telegram(final_img)
        save_learned_words([item['word'] for item in vocab_data])
        print("💾 새로운 단어 9개가 저장되었습니다.")
    else:
        print("⚠️ 최종 이미지가 생성되지 않아 전송을 건너뜁니다.")
