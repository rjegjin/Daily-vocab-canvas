"""
공통 카드 생성 엔진
generate_icons(), create_flashcard(), send_to_telegram() 제공
"""
import io
import os
import textwrap
import concurrent.futures
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

# 레이아웃 상수
CARD_SIZE  = 1080
GRID       = 3
CELL_SIZE  = CARD_SIZE // GRID   # 360
TEXT_RATIO = 0.55
TEXT_H     = int(CELL_SIZE * TEXT_RATIO)   # 198
ICON_H     = CELL_SIZE - TEXT_H            # 162
BORDER_COLOR = (220, 220, 220)
PAD = int(CELL_SIZE * 0.06)               # ~21px

# -------------------------------------------------------------------
# 아이콘 생성 (Gemini, 병렬)
# -------------------------------------------------------------------
def generate_single_icon(client, word, lang_hint=""):
    prompt = (
        f"A single minimalist flat design icon representing '{word}' ({lang_hint}). "
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
                w, h = img.size
                s = min(w, h)
                img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
                return img.resize((ICON_H, ICON_H), Image.LANCZOS)
        return None
    except Exception as e:
        print(f"  ⚠️ '{word}' 아이콘 생성 실패: {e}")
        return None

def generate_icons(client, vocab_data, lang_hint=""):
    print(f"🎨 Gemini로 아이콘 {len(vocab_data)}개를 병렬 생성 중...")
    words = [item['word'] for item in vocab_data]
    icons = [None] * len(words)
    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
        future_to_idx = {
            executor.submit(generate_single_icon, client, w, lang_hint): i
            for i, w in enumerate(words)
        }
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            icons[idx] = future.result()
            print(f"  {'✅' if icons[idx] else '❌'} [{idx+1}/9] {words[idx]}")
    print(f"🎨 아이콘 생성 완료: {sum(1 for ic in icons if ic)}/{len(words)}개 성공")
    return icons

# -------------------------------------------------------------------
# 플래시카드 합성
# fields: list of (text, font, fill) — 셀 상단에 순서대로 배치
# vocab_data 각 항목은 'word' 키 필수, 나머지는 fields_fn이 처리
# -------------------------------------------------------------------
def create_flashcard(icons, vocab_data, fields_fn, fonts, output_path):
    """
    fields_fn(item, fonts) -> list of (text, font, fill, line_h)
        텍스트 행 정의. line_h는 다음 행까지 픽셀 간격.
    fonts: dict (임의 키 → ImageFont)
    """
    print("🖋️ 플래시카드 합성 중...")
    try:
        canvas = Image.new("RGB", (CARD_SIZE, CARD_SIZE), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        for i, (item, icon) in enumerate(zip(vocab_data, icons)):
            col, row = i % GRID, i // GRID
            x0, y0 = col * CELL_SIZE, row * CELL_SIZE
            icon_y = y0 + TEXT_H

            # 아이콘
            if icon:
                icon_x = x0 + (CELL_SIZE - ICON_H) // 2
                canvas.paste(icon.convert("RGB"), (icon_x, icon_y), icon)
            else:
                draw.rectangle([x0, icon_y, x0 + CELL_SIZE, y0 + CELL_SIZE], fill=(240, 240, 240))

            # 텍스트 영역 흰색
            draw.rectangle([x0, y0, x0 + CELL_SIZE, icon_y], fill=(255, 255, 255))
            # 셀 경계 + 구분선
            draw.rectangle([x0, y0, x0 + CELL_SIZE - 1, y0 + CELL_SIZE - 1], outline=BORDER_COLOR, width=1)
            draw.line([(x0, icon_y), (x0 + CELL_SIZE, icon_y)], fill=BORDER_COLOR, width=1)

            def draw_centered(abs_y, text, font, fill):
                if abs_y + 4 >= y0 + TEXT_H:
                    return
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                draw.text((x0 + (CELL_SIZE - tw) // 2, abs_y), text, font=font, fill=fill)

            def draw_wrapped(abs_y, text, font, line_h, fill):
                for line in textwrap.wrap(text, width=22):
                    if abs_y + 4 >= y0 + TEXT_H:
                        break
                    draw_centered(abs_y, line, font, fill)
                    abs_y += line_h

            # 필드 렌더링
            cursor_y = y0 + PAD
            for field in fields_fn(item, fonts):
                text, font, fill, spacing, wrap = field
                if wrap:
                    draw_wrapped(cursor_y, text, font, spacing, fill)
                else:
                    draw_centered(cursor_y, text, font, fill)
                cursor_y += spacing

        canvas.save(output_path, "PNG", quality=95)
        print(f"✅ 최종 합성 완료: {output_path}")
        return output_path
    except Exception as e:
        print(f"❌ 합성 오류: {e}")
        return None

# -------------------------------------------------------------------
# 텔레그램 전송
# -------------------------------------------------------------------
def send_to_telegram(image_path, token, chat_id):
    print("📤 텔레그램으로 전송 중...")
    url = f"https://api.telegram.org/bot{token}/sendPhoto"

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
            result = session.post(url, data={'chat_id': chat_id}, files={'photo': photo}).json()
        if result.get("ok"):
            print(f"[{datetime.now()}] 🚀 카드를 성공적으로 보냈습니다!")
        else:
            print(f"❌ 전송 실패: {result}")
    except Exception as e:
        print(f"❌ 전송 오류: {e}")
