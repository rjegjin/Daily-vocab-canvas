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
# 2. 단어 데이터 (JSON) 생성 (Gemini 2.5 Flash)
# -------------------------------------------------------------------
def generate_vocab_data(learned_words):
    print("🧠 Gemini 모델을 통해 오늘의 단어 데이터를 생성 중...")
    
    exclude_text = ""
    if learned_words:
        # 단어 수가 너무 많을 경우 최근 300개 정도만 프롬프트에 포함하여 토큰 낭비 방지
        recent_learned = learned_words[-300:] 
        exclude_text = f"CRITICAL: DO NOT use any of these words: {', '.join(recent_learned)}."

    prompt = f"""
    Create a JSON array of 9 Spanish vocabulary words related to 'emotions' or 'personality traits'.
    {exclude_text}
    
    For each word, provide:
    - "word": The Spanish word (e.g., "Feliz")
    - "ipa": The IPA pronunciation (e.g., "[feˈlis]")
    - "meaning": The Korean meaning (e.g., "행복한")
    - "example": A short, simple Spanish example sentence.
    
    Output strictly valid JSON. No markdown formatting, just the raw JSON array.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    
    # Clean up markdown if model still outputs it
    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
        
    try:
        vocab_list = json.loads(raw_text.strip())
        print(f"✅ 9개의 단어 데이터 생성 완료: {[v['word'] for v in vocab_list]}")
        return vocab_list
    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 오류: {e}\n{raw_text}")
        return None

# -------------------------------------------------------------------
# 3. 배경 일러스트 생성 (Imagen 4)
# -------------------------------------------------------------------
def generate_background_grid():
    print("🎨 Imagen 4 모델을 통해 텍스트 없는 3x3 일러스트 그리드 생성 중...")
    
    image_path = "raw_background.png"
    
    prompt_text = """
    Create a strictly separated 3x3 grid image (square aspect ratio, exactly 1080x1080).
    There should be NO TEXT, NO LETTERS, NO WORDS in the image.
    
    Layout rules:
    - Strict 3x3 grid layout dividing the image into 9 equal square cells.
    - Each cell must have a clean, solid white area at the top half for later text placement.
    - The bottom half of each cell must contain a beautiful, high-quality illustration representing a different emotion.
    - The 9 illustrations must be very diverse in style: mix photorealistic, cinematic, 3D render, high-quality digital art, anime, pop art, watercolor, claymation, etc.
    - Solid, clean separation lines between the cells. No external borders.
    
    Remember: Absolutely NO text or typography. Just the layout and the diverse illustrations at the bottom of each cell.
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
        img = Image.open(bg_image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        
        # 폰트 설정 (OTF 파일 로드)
        font_dir = os.path.dirname(os.path.abspath(__file__))
        bold_font_path = os.path.join(font_dir, "NotoSansKR-Bold.ttf")
        reg_font_path = os.path.join(font_dir, "NotoSansKR-Regular.ttf")
        ipa_font_path = os.path.join(font_dir, "NotoSans-Regular.ttf") # IPA 특수문자 지원 폰트
        
        font_word = ImageFont.truetype(bold_font_path, 42)
        font_ipa = ImageFont.truetype(ipa_font_path, 26) # IPA 전용 폰트 적용
        font_meaning = ImageFont.truetype(bold_font_path, 28)
        font_example = ImageFont.truetype(reg_font_path, 20)
        
        img_w, img_h = img.size
        cell_w = img_w // 3
        cell_h = img_h // 3
        
        # 각 셀에 텍스트 그리기
        for i, item in enumerate(vocab_data):
            if i >= 9: break
            
            row = i // 3
            col = i % 3
            
            # 셀의 시작 좌표 (좌상단)
            x0 = col * cell_w
            y0 = row * cell_h
            
            # 중앙 정렬을 위한 헬퍼 함수
            def draw_centered_text(y_offset, text, font, fill_color=(0, 0, 0, 255)):
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
                x_pos = x0 + (cell_w - text_w) // 2
                y_pos = y0 + y_offset
                draw.text((x_pos, y_pos), text, font=font, fill=fill_color)
            
            # 긴 예문 자동 줄바꿈 헬퍼 함수
            def draw_wrapped_centered_text(y_offset, text, font, fill_color=(0, 0, 0, 255), max_width_chars=30):
                lines = textwrap.wrap(text, width=max_width_chars)
                current_y = y_offset
                for line in lines:
                    draw_centered_text(current_y, line, font, fill_color)
                    # 행간 계산
                    bbox = draw.textbbox((0, 0), line, font=font)
                    line_h = bbox[3] - bbox[1]
                    current_y += line_h + 5
            
            # 텍스트 배치 (위쪽 하얀 여백에 촘촘하게 배치되도록 Y 좌표 조정)
            # 셀 하나의 높이(cell_h)는 360px. 절반(180px)까지가 하얀 여백이라 가정.
            draw_centered_text(15, f"[{item['word']}]", font_word)
            draw_centered_text(70, item['ipa'], font_ipa, fill_color=(100, 100, 100, 255))
            draw_centered_text(110, item['meaning'], font_meaning)
            
            # 예문은 흰 배경의 하단부(그림 바로 위)에 위치하도록.
            draw_wrapped_centered_text(145, item['example'], font_example, fill_color=(50, 50, 50, 255), max_width_chars=32)
            
        final_path = "final_flashcard.png"
        
        # 합성된 이미지를 하얀색 배경으로 저장 (RGBA -> RGB)
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3]) # alpha 채널을 마스크로 사용
        background.save(final_path, "PNG")
        
        print(f"✅ 최종 합성 완료: {final_path}")
        return final_path
        
    except Exception as e:
        print(f"❌ 텍스트 합성 중 오류 발생: {e}")
        return None

# -------------------------------------------------------------------
# 5. 텔레그램으로 전송
# -------------------------------------------------------------------
def send_to_telegram(image_path):
    print("📤 텔레그램으로 이미지를 전송하는 중...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    try:
        with open(image_path, 'rb') as photo:
            payload = {'chat_id': CHAT_ID}
            files = {'photo': photo}
            response = requests.post(url, data=payload, files=files)
            
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
    print(f"=== 🌟 Daily Vocab Card Generator (Pipeline Mode) 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    # 0. 기존 학습 단어 로드
    learned_words = load_learned_words()
    print(f"📚 지금까지 학습한 단어 수: {len(learned_words)}개")

    # 1. 단어 데이터 (JSON) 생성
    vocab_data = generate_vocab_data(learned_words)
    if not vocab_data:
        exit(1)
        
    # 2. 텍스트 없는 배경 일러스트 생성
    bg_image = generate_background_grid()
    if not bg_image:
        exit(1)
        
    # 3. 이미지 위에 완벽한 폰트로 텍스트 타이핑
    final_img = overlay_text_on_image(bg_image, vocab_data)
    
    # 4. 전송
    if final_img and os.path.exists(final_img):
        send_to_telegram(final_img)
        
        # 성공적으로 전송된 단어를 DB에 기록
        new_words = [item['word'] for item in vocab_data]
        save_learned_words(new_words)
        print("💾 새로운 단어 9개가 learned_words.txt에 저장되었습니다.")
    else:
        print("⚠️ 최종 이미지가 생성되지 않아 전송을 건너뜁니다.")
