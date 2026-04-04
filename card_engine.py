"""
공통 카드 생성 엔진
generate_icons(), create_flashcard(), send_to_telegram() 제공
"""
import io
import os
import json
import textwrap
import concurrent.futures
import requests
import math
from datetime import datetime, date
from PIL import Image, ImageDraw, ImageFont
from google.genai import types
from google.cloud import texttospeech

# 프록시 설정 (환경 변수)
PROXY_URL = os.getenv('TELEGRAM_PROXY_URL')

def save_vocab_to_json(json_file: str, new_vocab: list):
    """
    learned_data_*.json에 신규 단어를 저장

    new_vocab: list of dicts (word, category 포함) 또는 list of str (하위 호환)
    단어가 이미 존재하면 seen_count를 증가시킴
    새로운 단어면 오늘 날짜로 추가
    """
    # 하위 호환: 문자열 리스트면 dict 리스트로 변환
    if new_vocab and isinstance(new_vocab[0], str):
        new_vocab = [{'word': w} for w in new_vocab]

    data = []
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

    word_map = {item['word']: item for item in data}
    today = date.today().isoformat()

    for item in new_vocab:
        word = item['word']
        category = item.get('category', 'unknown')
        if word in word_map:
            word_map[word]['seen_count'] = word_map[word].get('seen_count', 1) + 1
            if word_map[word].get('weak'):
                word_map[word]['weak'] = False
                word_map[word]['weak_date'] = None
            # 카테고리가 unknown이었으면 갱신
            if word_map[word].get('category', 'unknown') == 'unknown' and category != 'unknown':
                word_map[word]['category'] = category
        else:
            word_map[word] = {
                'word': word,
                'date_added': today,
                'category': category,
                'seen_count': 1,
                'weak': False,
                'weak_date': None,
            }

    data = list(word_map.values())

    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 레이아웃 상수
CARD_SIZE    = 1080
GRID         = 3
CELL_SIZE    = CARD_SIZE // GRID   # 360
TEXT_RATIO   = 0.55
TEXT_H       = int(CELL_SIZE * TEXT_RATIO)   # 198
ICON_H       = CELL_SIZE - TEXT_H            # 162
BORDER_COLOR = (220, 220, 220)
PAD          = int(CELL_SIZE * 0.06)         # ~21px

# 언어별 색상 테마
LANG_THEMES = {
    'es': {
        'text_bg': (255, 251, 240),   # 따뜻한 크림
        'border':  (210, 140, 40),    # 황금 오렌지
        'divider': (210, 140, 40),
    },
    'ja': {
        'text_bg': (240, 245, 255),   # 차가운 블루-화이트
        'border':  (70, 115, 195),    # 인디고 블루
        'divider': (70, 115, 195),
    },
    'zh': {
        'text_bg': (255, 242, 242),   # 연한 붉은빛
        'border':  (195, 45, 45),     # 붉은색
        'divider': (195, 45, 45),
    },
    'default': {
        'text_bg': (255, 255, 255),
        'border':  (220, 220, 220),
        'divider': (220, 220, 220),
    },
}

# 비용 단가 ($/1M tokens)
_PRICE = {
    'text_in':  0.25,
    'text_out': 1.50,
    'img_in':   0.50,
    'img_out':  60.0,
}
# TTS 단가: Google Cloud Standard $4/1M chars (1M/월 무료)
_TTS_PRICE_PER_CHAR = 4.0 / 1_000_000

_BUDGET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'budget.json')
_COST_LOG    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cost_log.json')

# -------------------------------------------------------------------
# 예산 읽기/쓰기
# -------------------------------------------------------------------
def load_budget() -> dict:
    defaults = {'monthly_limit_usd': 50.0, 'tts_enabled': True,
                'lang_enabled': {'es': True, 'ja': True, 'zh': True}}
    if not os.path.exists(_BUDGET_FILE):
        return defaults
    with open(_BUDGET_FILE, 'r') as f:
        data = json.load(f)
    # 누락 키 보완
    for k, v in defaults.items():
        data.setdefault(k, v)
    data['lang_enabled'] = {**defaults['lang_enabled'], **data.get('lang_enabled', {})}
    return data

def save_budget(cfg: dict):
    with open(_BUDGET_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

def monthly_gemini_total() -> float:
    """cost_log에서 이번 달 Gemini 합계 반환"""
    if not os.path.exists(_COST_LOG):
        return 0.0
    with open(_COST_LOG, 'r') as f:
        log = json.load(f)
    prefix = date.today().strftime('%Y-%m')
    return sum(
        v.get('_daily_total_usd', 0.0)
        for k, v in log.items()
        if k.startswith(prefix) and isinstance(v, dict)
    )

def monthly_tts_chars() -> int:
    """cost_log에서 이번 달 TTS 글자 수 합계 반환"""
    if not os.path.exists(_COST_LOG):
        return 0
    with open(_COST_LOG, 'r') as f:
        log = json.load(f)
    prefix = date.today().strftime('%Y-%m')
    total = 0
    for k, v in log.items():
        if k.startswith(prefix) and isinstance(v, dict):
            tts = v.get('tts', {})
            total += tts.get('chars', 0)
    return total

def is_lang_enabled(lang: str) -> bool:
    """언어가 budget.json에서 활성화되어 있는지 확인"""
    cfg = load_budget()
    return cfg['lang_enabled'].get(lang, True)

def is_tts_enabled() -> bool:
    return load_budget().get('tts_enabled', True)

def check_budget_exit(lang: str):
    """예산 초과 또는 언어 비활성화 시 sys.exit(0) 호출"""
    import sys
    cfg = load_budget()
    if not cfg['lang_enabled'].get(lang, True):
        print(f"⏭️ {lang} 비활성화 상태 — 건너뜀 (budget.json)")
        sys.exit(0)
    used = monthly_gemini_total()
    limit = cfg['monthly_limit_usd']
    if used >= limit:
        print(f"⛔ 월 예산 초과 (${used:.2f} / ${limit:.2f}) — {lang} 실행 중단")
        sys.exit(0)

def log_tts_chars(char_count: int):
    """TTS 글자 수를 cost_log.json에 기록"""
    log = {}
    if os.path.exists(_COST_LOG):
        with open(_COST_LOG, 'r') as f:
            log = json.load(f)
    today = date.today().isoformat()
    if today not in log:
        log[today] = {}
    tts = log[today].get('tts', {'chars': 0, 'cost_usd': 0.0})
    tts['chars'] += char_count
    # 월 누적 글자 수 (1M 이하 무료)
    month_chars = monthly_tts_chars() + char_count
    billable = max(0, month_chars - 1_000_000)
    tts['cost_usd'] = round(billable * _TTS_PRICE_PER_CHAR, 6)
    log[today]['tts'] = tts
    with open(_COST_LOG, 'w') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

# -------------------------------------------------------------------
# 비용 계산 & 로깅
# -------------------------------------------------------------------
def _calc_cost(img_in, img_out, txt_in=0, txt_out=0):
    return (
        txt_in  / 1e6 * _PRICE['text_in']  +
        txt_out / 1e6 * _PRICE['text_out'] +
        img_in  / 1e6 * _PRICE['img_in']   +
        img_out / 1e6 * _PRICE['img_out']
    )

def log_cost(lang, img_in_tokens, img_out_tokens, txt_in_tokens=0, txt_out_tokens=0):
    cost = _calc_cost(img_in_tokens, img_out_tokens, txt_in_tokens, txt_out_tokens)
    cost_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cost_log.json')

    log = {}
    if os.path.exists(cost_log_path):
        with open(cost_log_path, 'r') as f:
            log = json.load(f)

    today = str(date.today())
    if today not in log:
        log[today] = {}
    log[today][lang] = {
        'img_in': img_in_tokens, 'img_out': img_out_tokens,
        'txt_in': txt_in_tokens, 'txt_out': txt_out_tokens,
        'cost_usd': round(cost, 4),
    }

    # 오늘 전체 합계 (_daily_total_usd는 float이므로 dict만 필터링)
    daily_total = sum(v['cost_usd'] for v in log[today].values() if isinstance(v, dict) and 'cost_usd' in v)
    log[today]['_daily_total_usd'] = round(daily_total, 4)

    with open(cost_log_path, 'w') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"💰 비용 추정: ${cost:.4f} (이미지 {img_out_tokens} output tokens)")
    print(f"💰 오늘 누적: ${daily_total:.4f}")
    return cost

# -------------------------------------------------------------------
# 아이콘 생성 (Gemini, 병렬, 1K 최소 크기)
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
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=types.ImageConfig(
                    image_size='1K',
                    aspect_ratio='1:1',
                )
            )
        )
        u = response.usage_metadata
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                w, h = img.size
                s = min(w, h)
                img = img.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2))
                return img.resize((ICON_H, ICON_H), Image.LANCZOS), u.prompt_token_count, u.candidates_token_count
        return None, 0, 0
    except Exception as e:
        print(f"  ⚠️ '{word}' 아이콘 생성 실패: {e}")
        return None, 0, 0

def generate_icons(client, vocab_data, lang, lang_hint="",
                   txt_in_tokens=0, txt_out_tokens=0):
    """
    lang: 비용 로그용 언어 코드 (예: 'es', 'ja', 'zh')
    txt_in/out_tokens: 단어 생성 토큰 (함께 기록)
    """
    print(f"🎨 Gemini로 아이콘 {len(vocab_data)}개를 병렬 생성 중 (1K 1:1)...")
    words = [item['word'] for item in vocab_data]
    icons   = [None] * len(words)
    total_img_in  = 0
    total_img_out = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
        future_to_idx = {
            executor.submit(generate_single_icon, client, w, lang_hint): i
            for i, w in enumerate(words)
        }
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            icon, in_tok, out_tok = future.result()
            icons[idx] = icon
            total_img_in  += in_tok
            total_img_out += out_tok
            print(f"  {'✅' if icon else '❌'} [{idx+1}/9] {words[idx]}")

    success = sum(1 for ic in icons if ic is not None)
    print(f"🎨 아이콘 생성 완료: {success}/{len(words)}개 성공")

    log_cost(lang, total_img_in, total_img_out, txt_in_tokens, txt_out_tokens)
    return icons

# -------------------------------------------------------------------
# 플래시카드 합성
# -------------------------------------------------------------------
def create_flashcard(icons, vocab_data, fields_fn, fonts, output_path, theme='default'):
    print("🖋️ 플래시카드 합성 중...")
    t = LANG_THEMES.get(theme, LANG_THEMES['default'])
    try:
        canvas = Image.new("RGB", (CARD_SIZE, CARD_SIZE), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        for i, (item, icon) in enumerate(zip(vocab_data, icons)):
            col, row = i % GRID, i // GRID
            x0, y0 = col * CELL_SIZE, row * CELL_SIZE
            icon_y = y0 + TEXT_H

            if icon:
                icon_x = x0 + (CELL_SIZE - ICON_H) // 2
                canvas.paste(icon.convert("RGB"), (icon_x, icon_y), icon)
            else:
                draw.rectangle([x0, icon_y, x0 + CELL_SIZE, y0 + CELL_SIZE], fill=(240, 240, 240))

            draw.rectangle([x0, y0, x0 + CELL_SIZE, icon_y], fill=t['text_bg'])
            draw.rectangle([x0, y0, x0 + CELL_SIZE - 1, y0 + CELL_SIZE - 1], outline=t['border'], width=2)
            draw.line([(x0, icon_y), (x0 + CELL_SIZE, icon_y)], fill=t['divider'], width=2)

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

    # 프록시 설정 (SOCKS5)
    if PROXY_URL:
        print(f"🌐 프록시 활성화: {PROXY_URL}")
        session.proxies = {
            'http': PROXY_URL,
            'https': PROXY_URL,
        }

    try:
        with open(image_path, 'rb') as photo:
            result = session.post(url, data={'chat_id': chat_id}, files={'photo': photo}).json()
        if result.get("ok"):
            print(f"[{datetime.now()}] 🚀 카드를 성공적으로 보냈습니다!")
        else:
            print(f"❌ 전송 실패: {result}")
    except Exception as e:
        print(f"❌ 전송 오류: {e}")

# -------------------------------------------------------------------
# Google Text-to-Speech (음성 생성)
# -------------------------------------------------------------------
def generate_tts(text: str, lang_code: str, output_path: str):
    """
    Google Cloud Text-to-Speech로 음성 파일 생성

    Args:
        text: 음성화할 텍스트
        lang_code: 언어 코드 (예: 'es-ES', 'zh-CN')
        output_path: 저장할 MP3 파일 경로

    Returns:
        성공 시 output_path, 실패 시 None
    """
    try:
        # 서비스 계정 키 설정
        key_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                '.secrets', 'service_key.json')
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = key_path

        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(language_code=lang_code, ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

        with open(output_path, 'wb') as out:
            out.write(response.audio_content)

        log_tts_chars(len(text))
        print(f"✅ 음성 생성 완료: {output_path} ({len(text)}자)")
        return output_path
    except Exception as e:
        print(f"❌ TTS 생성 실패: {e}")
        return None

def send_audio_to_telegram(audio_path: str, token: str, chat_id: str, caption: str = ""):
    """
    오디오 파일을 텔레그램으로 전송
    """
    print("📤 음성을 텔레그램으로 전송 중...")
    url = f"https://api.telegram.org/bot{token}/sendAudio"

    class IPAdapter(requests.adapters.HTTPAdapter):
        def send(self, request, **kwargs):
            request.url = request.url.replace("api.telegram.org", "149.154.167.220")
            request.headers["Host"] = "api.telegram.org"
            return super().send(request, **kwargs)

    session = requests.Session()
    session.mount("https://", IPAdapter())
    session.verify = False

    try:
        with open(audio_path, 'rb') as audio:
            data = {'chat_id': chat_id}
            if caption:
                data['caption'] = caption
            result = session.post(url, data=data, files={'audio': audio}).json()
        if result.get("ok"):
            print(f"[{datetime.now()}] 🚀 음성을 성공적으로 보냈습니다!")
        else:
            print(f"❌ 전송 실패: {result}")
    except Exception as e:
        print(f"❌ 전송 오류: {e}")

def send_text_to_telegram(text: str, token: str, chat_id: str, parse_mode: str = "Markdown"):
    """
    텍스트 메시지를 텔레그램으로 전송

    Args:
        text: 전송할 텍스트
        token: 봇 토큰
        chat_id: 채팅 ID
        parse_mode: "Markdown" 또는 "HTML" (기본값: Markdown)
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    class IPAdapter(requests.adapters.HTTPAdapter):
        def send(self, request, **kwargs):
            request.url = request.url.replace("api.telegram.org", "149.154.167.220")
            request.headers["Host"] = "api.telegram.org"
            return super().send(request, **kwargs)

    session = requests.Session()
    session.mount("https://", IPAdapter())
    session.verify = False

    try:
        data = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
        result = session.post(url, data=data).json()
        if result.get("ok"):
            print(f"[{datetime.now()}] 🚀 메시지를 성공적으로 보냈습니다!")
        else:
            print(f"❌ 전송 실패: {result}")
    except Exception as e:
        print(f"❌ 전송 오류: {e}")

# -------------------------------------------------------------------
# 중국어 성조 곡선 이미지 생성 (2x2 그리드)
# -------------------------------------------------------------------
def generate_tone_chart(output_path: str):
    """
    4개 성조(1,2,3,4)의 곡선을 2x2 그리드로 배치한 이미지 생성

    Args:
        output_path: 저장할 PNG 파일 경로

    Returns:
        성공 시 output_path, 실패 시 None
    """
    try:
        CELL_W, CELL_H = 192, 192
        PADDING = 20
        MARGIN = 10
        TOTAL_W = CELL_W * 2 + PADDING + MARGIN * 2
        TOTAL_H = CELL_H * 2 + PADDING + MARGIN * 2

        # 색상
        BG_COLOR = (240, 240, 240)      # 밝은 회색
        CURVE_COLOR = (0, 102, 204)     # 파란색
        GRID_COLOR = (200, 200, 200)    # 격자선 (밝은 회색)
        AXIS_COLOR = (150, 150, 150)    # 축 (회색)
        TEXT_COLOR = (0, 0, 0)          # 검정

        # 캔버스 생성
        canvas = Image.new("RGB", (TOTAL_W, TOTAL_H), BG_COLOR)
        draw = ImageDraw.Draw(canvas)

        # 성조별 곡선 함수
        def draw_tone_curve(draw_obj, x_offset, y_offset, tone_num):
            """각 성조의 곡선을 그림"""
            # 격자선
            for i in range(1, 5):
                y = y_offset + int(CELL_H * i / 5)
                draw_obj.line([(x_offset, y), (x_offset + CELL_W, y)], fill=GRID_COLOR, width=1)

            # 축
            draw_obj.rectangle([x_offset, y_offset, x_offset + CELL_W, y_offset + CELL_H],
                              outline=AXIS_COLOR, width=2)

            # 성조 곡선 (좌표: 0~1, 변환 후 픽셀)
            points = []

            if tone_num == 1:  # High Flat (수평선, 높은 위치)
                for x in range(0, CELL_W + 1, 2):
                    norm_x = x / CELL_W
                    norm_y = 0.7  # 높은 위치 (반대: y=0이 위, y=1이 아래)
                    px = x_offset + x
                    py = y_offset + int(CELL_H * (1 - norm_y))
                    points.append((px, py))

            elif tone_num == 2:  # Rising (올라가는 곡선)
                for x in range(0, CELL_W + 1, 2):
                    norm_x = x / CELL_W
                    norm_y = 0.2 + norm_x * 0.6  # 0.2에서 0.8로
                    px = x_offset + x
                    py = y_offset + int(CELL_H * (1 - norm_y))
                    points.append((px, py))

            elif tone_num == 3:  # Low Dip (내려갔다 올라옴)
                for x in range(0, CELL_W + 1, 2):
                    norm_x = x / CELL_W
                    # 0에서 0.5까지: 0.7 → 0.2, 0.5에서 1까지: 0.2 → 0.6
                    if norm_x < 0.5:
                        norm_y = 0.7 - (norm_x * 2) * 0.5
                    else:
                        norm_y = 0.2 + ((norm_x - 0.5) * 2) * 0.4
                    px = x_offset + x
                    py = y_offset + int(CELL_H * (1 - norm_y))
                    points.append((px, py))

            elif tone_num == 4:  # Falling (내려가는 직선)
                for x in range(0, CELL_W + 1, 2):
                    norm_x = x / CELL_W
                    norm_y = 0.8 - norm_x * 0.6  # 0.8에서 0.2로
                    px = x_offset + x
                    py = y_offset + int(CELL_H * (1 - norm_y))
                    points.append((px, py))

            # 곡선 그리기
            if len(points) > 1:
                draw_obj.line(points, fill=CURVE_COLOR, width=3)

            # 성조 숫자 라벨
            label = f"{tone_num}声"
            try:
                font = ImageFont.load_default()
                bbox = draw_obj.textbbox((0, 0), label, font=font)
                label_w = bbox[2] - bbox[0]
                label_h = bbox[3] - bbox[1]
                label_x = x_offset + (CELL_W - label_w) // 2
                label_y = y_offset + CELL_H - label_h - 3
                draw_obj.text((label_x, label_y), label, fill=TEXT_COLOR, font=font)
            except:
                pass

        # 2x2 그리드로 배치
        positions = [
            (MARGIN, MARGIN, 1),              # 좌상: 1성
            (MARGIN + CELL_W + PADDING, MARGIN, 2),  # 우상: 2성
            (MARGIN, MARGIN + CELL_H + PADDING, 3),  # 좌하: 3성
            (MARGIN + CELL_W + PADDING, MARGIN + CELL_H + PADDING, 4),  # 우하: 4성
        ]

        for x_off, y_off, tone in positions:
            draw_tone_curve(draw, x_off, y_off, tone)

        canvas.save(output_path, "PNG")
        print(f"✅ 성조 차트 생성 완료: {output_path}")
        return output_path

    except Exception as e:
        print(f"❌ 성조 차트 생성 실패: {e}")
        return None
