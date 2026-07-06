"""
공통 카드 생성 엔진
generate_icons(), create_flashcard(), send_to_telegram() 제공
"""
import io
import os
import json
import textwrap
import requests
import math
import fcntl
import hashlib
import time
import tempfile
import base64
from datetime import datetime, date
from PIL import Image, ImageDraw, ImageFont
from google.genai import types
from google.oauth2 import service_account
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

# 비용 단가
_PRICE = {
    'text_in':   0.25,   # $/1M tokens
    'text_out':  1.50,   # $/1M tokens
    'img_per':   0.02,   # $/image (Imagen 4 Fast 고정 단가)
}

# Vertex AI Imagen4 설정
_VERTEX_PROJECT  = "gen-lang-client-0367740438"
_VERTEX_LOCATION = "us-central1"
_KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         '.secrets', 'service_key.json')
_imagen_client = None
_IMAGEN_MODEL = "imagen-4.0-fast-generate-001"
_ICON_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon_cache')
_SERVICE_ACCOUNT_JSON_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
_OPENAI_TEXT_MODEL_DEFAULT = "gpt-4.1-nano"
_OPENAI_IMAGE_MODEL_DEFAULT = "gpt-image-1-mini"
_OPENAI_IMAGE_QUALITY_DEFAULT = "low"

_OPENAI_TEXT_PRICE = {
    "input": 0.10,
    "output": 0.40,
}
_OPENAI_IMAGE_PRICE_LOW_1024 = {
    "gpt-image-1-mini": 0.005,
    "gpt-image-1": 0.011,
    "gpt-image-1.5": 0.009,
    "gpt-image-2": 0.006,
}

def _service_account_path() -> str:
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        if os.path.exists(env_path):
            return env_path
        raise FileNotFoundError(f"GOOGLE_APPLICATION_CREDENTIALS points to missing file: {env_path}")

    raw_json = os.getenv(_SERVICE_ACCOUNT_JSON_ENV)
    if raw_json:
        tmp_path = os.path.join(tempfile.gettempdir(), "vocab_service_key.json")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_path
        return tmp_path

    if os.path.exists(_KEY_PATH):
        return _KEY_PATH

    raise FileNotFoundError(
        "Vertex service account key not found. Set GOOGLE_APPLICATION_CREDENTIALS "
        f"or {_SERVICE_ACCOUNT_JSON_ENV}, or create {_KEY_PATH}."
    )

def _get_imagen_client():
    global _imagen_client
    if _imagen_client is not None:
        return _imagen_client
    import google.genai as genai
    credentials = service_account.Credentials.from_service_account_file(
        _service_account_path(),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    _imagen_client = genai.Client(
        vertexai=True,
        project=_VERTEX_PROJECT,
        location=_VERTEX_LOCATION,
        credentials=credentials,
    )
    return _imagen_client
# TTS 단가: Google Cloud Standard $4/1M chars (1M/월 무료)
_TTS_PRICE_PER_CHAR = 4.0 / 1_000_000

_BUDGET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'budget.json')
_COST_LOG    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cost_log.json')
_COST_LOCK   = f"{_COST_LOG}.lock"

def _update_cost_log(mutator):
    """cost_log.json 갱신을 프로세스 간 직렬화한다."""
    with open(_COST_LOCK, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            log = {}
            if os.path.exists(_COST_LOG):
                with open(_COST_LOG, 'r') as f:
                    log = json.load(f)
            result = mutator(log)
            tmp_path = f"{_COST_LOG}.tmp"
            with open(tmp_path, 'w') as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, _COST_LOG)
            return result
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

# -------------------------------------------------------------------
# 예산 읽기/쓰기
# -------------------------------------------------------------------
def load_budget() -> dict:
    defaults = {'monthly_limit_usd': 10.0, 'tts_enabled': True,
                'lang_enabled': {'es': True, 'ja': True, 'zh': True, 'en': True}}
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
    """cost_log에서 이번 달 이미지+텍스트 합계 반환"""
    if not os.path.exists(_COST_LOG):
        return 0.0
    with open(_COST_LOG, 'r') as f:
        log = json.load(f)
    prefix = date.today().strftime('%Y-%m')
    total = 0.0
    for k, v in log.items():
        if not k.startswith(prefix) or not isinstance(v, dict):
            continue
        daily = v.get('_daily_total_usd')
        if daily is not None:
            total += daily
        else:
            # 하위 호환: 언어별 dict 합산
            total += sum(lv['cost_usd'] for lv in v.values()
                         if isinstance(lv, dict) and 'cost_usd' in lv)
    return total

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
    def mutator(log):
        today = date.today().isoformat()
        if today not in log:
            log[today] = {}
        tts = log[today].get('tts', {'chars': 0, 'cost_usd': 0.0})
        tts['chars'] += char_count

        prefix = date.today().strftime('%Y-%m')
        month_chars = 0
        for k, v in log.items():
            if k.startswith(prefix) and isinstance(v, dict):
                month_chars += v.get('tts', {}).get('chars', 0)
        billable = max(0, month_chars - 1_000_000)
        tts['cost_usd'] = round(billable * _TTS_PRICE_PER_CHAR, 6)
        log[today]['tts'] = tts
        return tts

    return _update_cost_log(mutator)

# -------------------------------------------------------------------
# 비용 계산 & 로깅
# -------------------------------------------------------------------
def log_cost(lang, img_count, txt_in_tokens=0, txt_out_tokens=0):
    """Legacy Gemini/Imagen 비용 기록."""
    img_cost = img_count * _PRICE['img_per']
    txt_cost = (txt_in_tokens / 1e6 * _PRICE['text_in'] +
                txt_out_tokens / 1e6 * _PRICE['text_out'])
    cost = round(img_cost + txt_cost, 4)

    def mutator(log):
        today = str(date.today())
        if today not in log:
            log[today] = {}
        log[today][lang] = {
            'img_count': img_count,
            'txt_in': txt_in_tokens, 'txt_out': txt_out_tokens,
            'cost_usd': cost,
        }

        daily_total = sum(v['cost_usd'] for v in log[today].values() if isinstance(v, dict) and 'cost_usd' in v)
        log[today]['_daily_total_usd'] = round(daily_total, 4)
        return daily_total

    daily_total = _update_cost_log(mutator)

    print(f"💰 비용: ${cost:.4f} (img={img_count}, txt_in={txt_in_tokens}, txt_out={txt_out_tokens})")
    print(f"💰 오늘 누적: ${daily_total:.4f}")
    return cost

def log_provider_cost(lang: str, provider: str, cost_usd: float, **details):
    """Provider-specific cost entry. Multiple calls for one lang/day are accumulated."""
    cost = round(cost_usd, 6)

    def mutator(log):
        today = str(date.today())
        if today not in log:
            log[today] = {}
        entry = log[today].get(lang, {})
        if not isinstance(entry, dict):
            entry = {}
        providers = entry.get("providers", [])
        providers.append({"provider": provider, "cost_usd": cost, **details})
        entry["providers"] = providers
        entry["cost_usd"] = round(sum(p.get("cost_usd", 0.0) for p in providers), 6)
        entry["img_count"] = entry.get("img_count", 0) + int(details.get("img_count", 0))
        entry["txt_in"] = entry.get("txt_in", 0) + int(details.get("txt_in", 0))
        entry["txt_out"] = entry.get("txt_out", 0) + int(details.get("txt_out", 0))
        log[today][lang] = entry
        daily_total = sum(v['cost_usd'] for v in log[today].values() if isinstance(v, dict) and 'cost_usd' in v)
        log[today]['_daily_total_usd'] = round(daily_total, 6)
        return daily_total

    daily_total = _update_cost_log(mutator)
    print(f"💰 {provider} 비용: ${cost:.6f}")
    print(f"💰 오늘 누적: ${daily_total:.6f}")
    return cost

def _strip_json_text(text: str):
    raw = text.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        arr_start = raw.find("[")
        if arr_start != -1 and (start == -1 or arr_start < start):
            start = arr_start
        end = max(raw.rfind("}"), raw.rfind("]"))
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(raw[start:end + 1])

def _response_text(response):
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    return "\n".join(chunks)

def _usage_tokens(response):
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0
    in_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
    out_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
    return int(in_tokens), int(out_tokens)

def generate_vocab_openai(prompt: str, required_keys: set, lang: str):
    """Generate vocab JSON array through a low-cost OpenAI text model."""
    from openai import OpenAI

    model = os.getenv("VOCAB_OPENAI_TEXT_MODEL", _OPENAI_TEXT_MODEL_DEFAULT)
    client = OpenAI()
    wrapped_prompt = f"""
{prompt}

Return a JSON object with exactly one key "items".
"items" must be the requested JSON array. Do not include markdown.
"""
    response = client.responses.create(
        model=model,
        input=wrapped_prompt,
    )
    data = _strip_json_text(_response_text(response))
    if isinstance(data, dict):
        data = data.get("items") or data.get("words") or data.get("data")
    if not isinstance(data, list) or len(data) != 9:
        raise ValueError("OpenAI 응답이 9개 JSON 배열이 아닙니다.")
    for idx, item in enumerate(data, start=1):
        missing = required_keys - set(item)
        if missing:
            raise ValueError(f"{idx}번째 항목 필수 필드 누락: {sorted(missing)}")
    in_tokens, out_tokens = _usage_tokens(response)
    cost = (in_tokens / 1_000_000 * _OPENAI_TEXT_PRICE["input"] +
            out_tokens / 1_000_000 * _OPENAI_TEXT_PRICE["output"])
    log_provider_cost(
        lang,
        "openai_text",
        cost,
        model=model,
        txt_in=in_tokens,
        txt_out=out_tokens,
    )
    print(f"✅ OpenAI 단어 9개 생성 완료 ({model}): {[d['word'] for d in data]}")
    return data, in_tokens, out_tokens

# -------------------------------------------------------------------
# 아이콘 생성 (Imagen 4 Fast 3x3 sheet via Vertex AI)
# -------------------------------------------------------------------
def _icon_cache_path(lang: str, word: str) -> str:
    os.makedirs(_ICON_CACHE_DIR, exist_ok=True)
    digest = hashlib.sha1(f"{lang}:{word}".encode("utf-8")).hexdigest()[:16]
    return os.path.join(_ICON_CACHE_DIR, f"{lang}_{digest}.png")

def _load_cached_icon(lang: str, word: str):
    path = _icon_cache_path(lang, word)
    if not os.path.exists(path):
        return None
    try:
        icon = Image.open(path).convert("RGBA").resize((ICON_H, ICON_H), Image.LANCZOS)
        return _remove_sheet_artifacts(icon)
    except Exception as e:
        print(f"  ⚠️ 캐시 로드 실패 '{word}': {e}")
        return None

def _save_cached_icon(lang: str, word: str, icon: Image.Image):
    try:
        icon.save(_icon_cache_path(lang, word), "PNG")
    except Exception as e:
        print(f"  ⚠️ 캐시 저장 실패 '{word}': {e}")

def _icon_concept(item: dict) -> str:
    return (
        item.get('visual')
        or item.get('visual_hint')
        or item.get('meaning')
        or item.get('word')
        or 'simple object'
    )

def _build_sheet_prompt(concepts, lang_hint: str) -> str:
    concept_line = " | ".join(concepts)
    return f"""
Create one square image containing exactly {len(concepts)} large minimalist flat pictogram icons for vocabulary flashcards.
Arrange them in one horizontal row from left to right, matching these visual concepts:
{concept_line}

Important:
- Draw only pictures of the visual concepts.
- The final image must contain pictures only.
- No text, no letters, no numbers, no labels, no captions, no signs, no watermarks, no writing systems.
- No divider lines, no dashed guide lines, no crop marks, no frames.
- Do not make a worksheet, contact sheet, template, chart, or grid.
- Use three equal invisible columns, one icon per column.
- Each icon should be large, centered, isolated, and easy to recognize after cropping.
- If a concept is abstract, use a simple object metaphor instead of writing a word.
- Leave wide empty white margins around each icon, especially near column boundaries.
- Pure white background, soft pastel colors, clean educational flashcard style.
- No borders, no panels, no drop shadows, no perspective.
"""

def _build_grid_prompt(concepts, lang_hint: str) -> str:
    concept_lines = "\n".join(f"{idx + 1}. {concept}" for idx, concept in enumerate(concepts))
    return f"""
Create one square image containing exactly 9 large minimalist flat pictogram icons for vocabulary flashcards.
Arrange them in a clean 3x3 grid in reading order, matching these visual concepts:
{concept_lines}

Important:
- Draw only pictures of the visual concepts.
- The final image must contain pictures only.
- No text, no letters, no numbers, no labels, no captions, no signs, no watermarks, no writing systems.
- No visible grid lines, divider lines, dashed guide lines, crop marks, frames, or panels.
- Use nine equal invisible cells, one icon per cell.
- Each icon should be large, centered, isolated, and easy to recognize after cropping.
- If a concept is abstract, use a simple object metaphor instead of writing a word.
- Leave wide empty white margins around each icon and near cell boundaries.
- Pure white background, soft pastel colors, clean educational flashcard style.
- No borders, no drop shadows, no perspective.
"""

def generate_icon_sheet_imagen(concepts, lang_hint=""):
    prompt = _build_sheet_prompt(concepts, lang_hint)
    delays = [0, 8, 20]

    for attempt, delay in enumerate(delays, start=1):
        if delay:
            print(f"  ⏳ Imagen 재시도 대기 {delay}s ({attempt}/{len(delays)})")
            time.sleep(delay)
        try:
            client = _get_imagen_client()
            response = client.models.generate_images(
                model=_IMAGEN_MODEL,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                ),
            )
            if not response.generated_images:
                raise RuntimeError("이미지 응답이 비어 있습니다.")
            return Image.open(io.BytesIO(response.generated_images[0].image.image_bytes)).convert("RGBA")
        except Exception as e:
            print(f"  ⚠️ Imagen sheet 생성 실패 ({attempt}/{len(delays)}): {e}")

    return None

def generate_icon_sheet_openai(concepts, lang_hint=""):
    from openai import OpenAI

    prompt = _build_grid_prompt(concepts, lang_hint)
    model = os.getenv("VOCAB_OPENAI_IMAGE_MODEL", _OPENAI_IMAGE_MODEL_DEFAULT)
    quality = os.getenv("VOCAB_OPENAI_IMAGE_QUALITY", _OPENAI_IMAGE_QUALITY_DEFAULT)
    try:
        client = OpenAI()
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size="1024x1024",
            quality=quality,
            n=1,
        )
        image_b64 = response.data[0].b64_json
        if not image_b64:
            raise RuntimeError("OpenAI image 응답에 b64_json이 없습니다.")
        return Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGBA")
    except Exception as e:
        print(f"  ⚠️ OpenAI icon sheet 생성 실패: {e}")
        return None

def split_icon_sheet(sheet: Image.Image, count: int):
    sheet_size = ICON_H * GRID
    sheet = sheet.resize((sheet_size, sheet_size), Image.LANCZOS)
    trim = max(6, ICON_H // 24)
    icons = []

    def _crop_cell(x0, y0):
        crop = sheet.crop((x0 + trim, y0 + trim, x0 + ICON_H - trim, y0 + ICON_H - trim))
        icon = crop.convert("RGBA").resize((ICON_H, ICON_H), Image.LANCZOS)
        icon = _remove_sheet_artifacts(icon)
        return _fit_icon_content(icon)

    if count <= GRID:
        y0 = (sheet_size - ICON_H) // 2
        for i in range(count):
            icons.append(_crop_cell(i * ICON_H, y0))
        return icons

    for i in range(count):
        col, row = i % GRID, i // GRID
        icons.append(_crop_cell(col * ICON_H, row * ICON_H))
    return icons

def _remove_sheet_artifacts(icon: Image.Image) -> Image.Image:
    """Imagen이 그린 얇은 sheet guide line만 흰색으로 지운다."""
    img = icon.convert("RGBA")
    px = img.load()
    w, h = img.size

    def is_gray_guide(pixel):
        r, g, b, a = pixel
        if a < 20:
            return False
        return 130 <= r <= 245 and abs(r - g) <= 10 and abs(g - b) <= 10

    guide_cols = [
        x for x in range(w)
        if sum(1 for y in range(h) if is_gray_guide(px[x, y])) > h * 0.45
    ]
    guide_rows = [
        y for y in range(h)
        if sum(1 for x in range(w) if is_gray_guide(px[x, y])) > w * 0.45
    ]

    for x in guide_cols:
        for xx in range(max(0, x - 1), min(w, x + 2)):
            for y in range(h):
                px[xx, y] = (255, 255, 255, 255)
    for y in guide_rows:
        for yy in range(max(0, y - 1), min(h, y + 2)):
            for x in range(w):
                px[x, yy] = (255, 255, 255, 255)

    margin = max(12, h // 8)
    for y in list(range(margin)) + list(range(h - margin, h)):
        dark_xs = []
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 20 and max(r, g, b) < 190:
                dark_xs.append(x)
        if 8 <= len(dark_xs) <= w * 0.45 and max(dark_xs) - min(dark_xs) <= w * 0.55:
            for yy in range(max(0, y - 1), min(h, y + 2)):
                for x in range(w):
                    r, g, b, a = px[x, yy]
                    if a > 20 and max(r, g, b) < 210:
                        px[x, yy] = (255, 255, 255, 255)

    return img

def _fit_icon_content(icon: Image.Image) -> Image.Image:
    img = icon.convert("RGBA")
    px = img.load()
    w, h = img.size
    xs = []
    ys = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 20 and min(r, g, b) < 245:
                xs.append(x)
                ys.append(y)

    if not xs or not ys:
        return img

    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    content_w = x1 - x0 + 1
    content_h = y1 - y0 + 1
    if content_w < 8 or content_h < 8:
        return img

    side = int(max(content_w, content_h) * 1.35)
    side = max(side, ICON_H // 2)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2

    crop = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    left = cx - side // 2
    top = cy - side // 2
    src_box = (
        max(0, left),
        max(0, top),
        min(w, left + side),
        min(h, top + side),
    )
    paste_x = src_box[0] - left
    paste_y = src_box[1] - top
    crop.paste(img.crop(src_box), (paste_x, paste_y))
    return crop.resize((ICON_H, ICON_H), Image.LANCZOS)

def generate_icons(client, vocab_data, lang, lang_hint="",
                   txt_in_tokens=0, txt_out_tokens=0):
    """
    client: Gemini 텍스트 클라이언트 (단어 생성용, 아이콘엔 미사용)
    lang: 비용 로그용 언어 코드 (예: 'es', 'ja', 'zh')
    txt_in/out_tokens: 단어 생성 토큰 (함께 기록)
    """
    if os.getenv("VOCAB_IMAGE_PROVIDER", "openai").lower() == "openai":
        return generate_icons_openai(vocab_data, lang, lang_hint)
    return generate_icons_imagen(client, vocab_data, lang, lang_hint, txt_in_tokens, txt_out_tokens)

def generate_icons_openai(vocab_data, lang, lang_hint=""):
    words = [item['word'] for item in vocab_data]
    concepts = [_icon_concept(item) for item in vocab_data]
    model = os.getenv("VOCAB_OPENAI_IMAGE_MODEL", _OPENAI_IMAGE_MODEL_DEFAULT)
    quality = os.getenv("VOCAB_OPENAI_IMAGE_QUALITY", _OPENAI_IMAGE_QUALITY_DEFAULT)
    print(f"🎨 {model}({quality})로 3x3 icon sheet 1장을 생성 중...")

    sheet = generate_icon_sheet_openai(concepts, lang_hint)
    icons = []
    billable_images = 0
    if sheet:
        icons = split_icon_sheet(sheet, len(words))
        for word, icon in zip(words, icons):
            _save_cached_icon(lang, word, icon)
        billable_images = 1
        print(f"🎨 OpenAI 3x3 sheet 생성 완료 → 아이콘 {len(icons)}개 crop")
    else:
        print("⚠️ OpenAI sheet 생성 실패, 기존 아이콘 캐시를 사용합니다.")
        icons = [_load_cached_icon(lang, word) for word in words]

    success = sum(1 for ic in icons if ic is not None)
    for idx, word in enumerate(words):
        print(f"  {'✅' if icons[idx] else '❌'} [{idx+1}/9] {word}")

    print(f"🎨 아이콘 준비 완료: {success}/{len(words)}개 사용 가능")
    if billable_images:
        image_cost = _OPENAI_IMAGE_PRICE_LOW_1024.get(model, 0.005)
        log_provider_cost(
            lang,
            "openai_image",
            image_cost,
            model=model,
            quality=quality,
            img_count=billable_images,
        )
    return icons

def generate_icons_imagen(client, vocab_data, lang, lang_hint="",
                          txt_in_tokens=0, txt_out_tokens=0):
    words = [item['word'] for item in vocab_data]
    concepts = [_icon_concept(item) for item in vocab_data]
    print(f"🎨 {_IMAGEN_MODEL}로 3-icon sheet 3장을 생성 중...")

    billable_images = 0
    icons = []

    for batch_start in range(0, len(words), GRID):
        batch_words = words[batch_start:batch_start + GRID]
        batch_concepts = concepts[batch_start:batch_start + GRID]
        sheet = generate_icon_sheet_imagen(batch_concepts, lang_hint)

        if sheet:
            batch_icons = split_icon_sheet(sheet, len(batch_words))
            for word, icon in zip(batch_words, batch_icons):
                _save_cached_icon(lang, word, icon)
            icons.extend(batch_icons)
            billable_images += 1
            print(f"🎨 sheet 생성 완료: {batch_start // GRID + 1}/3 → 아이콘 {len(batch_icons)}개 crop")
        else:
            print(f"⚠️ sheet 생성 실패: {batch_start // GRID + 1}/3, 기존 아이콘 캐시를 사용합니다.")
            icons.extend([_load_cached_icon(lang, word) for word in batch_words])

    success = sum(1 for ic in icons if ic is not None)
    for idx, word in enumerate(words):
        print(f"  {'✅' if icons[idx] else '❌'} [{idx+1}/9] {word}")

    print(f"🎨 아이콘 준비 완료: {success}/{len(words)}개 사용 가능")
    log_cost(lang, billable_images, txt_in_tokens, txt_out_tokens)
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
                if not text:
                    continue
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
def generate_tts(text: str, lang_code: str, output_path: str, voice_name: str = None):
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
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = _service_account_path()

        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_kwargs = {
            "language_code": lang_code,
            "ssml_gender": texttospeech.SsmlVoiceGender.NEUTRAL,
        }
        if voice_name:
            if not voice_name.startswith(f"{lang_code}-"):
                raise ValueError(f"voice_name language mismatch: {voice_name} vs {lang_code}")
            voice_kwargs["name"] = voice_name
        voice = texttospeech.VoiceSelectionParams(**voice_kwargs)
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
