"""
Shared helpers for the English fluency practice modules.
"""
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai

from card_engine import check_budget_exit, generate_tts, log_cost, log_provider_cost

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR.parent / ".secrets" / ".env")

TOKEN = os.getenv("VOCAB_BOT_TOKEN") or os.getenv("GEMINI_BOT_TOKEN")
CHAT_ID = os.getenv("VOCAB_CHAT_ID") or os.getenv("GEMINI_CHAT_ID")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
PROXY_URL = os.getenv("TELEGRAM_PROXY_URL")
TEXT_PROVIDER = os.getenv("VOCAB_TEXT_PROVIDER", "openai").lower()
OPENAI_TEXT_MODEL = os.getenv("VOCAB_OPENAI_TEXT_MODEL", "gpt-4.1-nano")

MODEL_CANDIDATES = ["gemini-3.1-flash-lite-preview", "gemini-2.5-flash"]


def TODAY() -> str:
    return date.today().isoformat()

LEARNED_EN_FILE = PROJECT_DIR / "learned_data_en.json"
LEARNED_EN_PHRASE_FILE = PROJECT_DIR / "learned_data_en_phrase.json"
DIALOGUE_HISTORY_FILE = PROJECT_DIR / "dialogue_history.json"
JA_DIALOGUE_HISTORY_FILE = PROJECT_DIR / "dialogue_history_ja.json"
ZH_DIALOGUE_HISTORY_FILE = PROJECT_DIR / "dialogue_history_zh.json"
WRITING_SESSIONS_FILE = PROJECT_DIR / "writing_sessions.json"
WRITING_SUBMISSIONS_FILE = PROJECT_DIR / "writing_submissions.json"
ENGLISH_STATE_FILE = PROJECT_DIR / "english_state.json"


def require_env():
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("VOCAB_BOT_TOKEN/VOCAB_CHAT_ID 환경 변수가 필요합니다.")
    if TEXT_PROVIDER != "openai" and not API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경 변수가 필요합니다.")


def get_client():
    require_env()
    return genai.Client(api_key=API_KEY)


def read_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def strip_json_text(text: str):
    raw = text.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", raw)
        if not match:
            raise
        return json.loads(match.group(1))


def generate_json(prompt: str, required_keys=None, expect_list=True, lang="en"):
    if TEXT_PROVIDER == "openai":
        return generate_json_openai(prompt, required_keys=required_keys, expect_list=expect_list, lang=lang)

    client = get_client()
    last_error = None
    for model in MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            data = strip_json_text(response.text or "")
            if expect_list and not isinstance(data, list):
                for key in ("items", "words", "phrases", "data"):
                    if isinstance(data, dict) and isinstance(data.get(key), list):
                        data = data[key]
                        break
            if expect_list and not isinstance(data, list):
                raise ValueError("JSON list 응답이 아닙니다.")
            if required_keys:
                items = data if isinstance(data, list) else [data]
                for idx, item in enumerate(items, start=1):
                    missing = set(required_keys) - set(item)
                    if missing:
                        raise ValueError(f"{idx}번째 항목 필수 필드 누락: {sorted(missing)}")
            usage = response.usage_metadata
            log_cost(lang, 0, usage.prompt_token_count, usage.candidates_token_count)
            return data
        except Exception as exc:
            last_error = exc
            print(f"⚠️ {model} 실패: {exc}")
    raise RuntimeError(f"영어 콘텐츠 생성 실패: {last_error}")


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


def generate_json_openai(prompt: str, required_keys=None, expect_list=True, lang="en"):
    from openai import OpenAI

    require_env()
    client = OpenAI()
    shape = "a JSON object" if not expect_list else 'a JSON object with exactly one key "items" containing the requested JSON array'
    response = client.responses.create(
        model=OPENAI_TEXT_MODEL,
        input=f"{prompt}\n\nReturn {shape}. Do not include markdown.",
    )
    data = strip_json_text(_response_text(response))
    if expect_list and not isinstance(data, list):
        for key in ("items", "words", "phrases", "data"):
            if isinstance(data, dict) and isinstance(data.get(key), list):
                data = data[key]
                break
    if expect_list and not isinstance(data, list):
        raise ValueError("JSON list 응답이 아닙니다.")
    if required_keys:
        items = data if isinstance(data, list) else [data]
        for idx, item in enumerate(items, start=1):
            missing = set(required_keys) - set(item)
            if missing:
                raise ValueError(f"{idx}번째 항목 필수 필드 누락: {sorted(missing)}")
    in_tokens, out_tokens = _usage_tokens(response)
    cost = (in_tokens / 1_000_000 * 0.10) + (out_tokens / 1_000_000 * 0.40)
    log_provider_cost(
        lang,
        "openai_text",
        cost,
        model=OPENAI_TEXT_MODEL,
        txt_in=in_tokens,
        txt_out=out_tokens,
    )
    return data


def telegram_session():
    session = requests.Session()

    class IPAdapter(requests.adapters.HTTPAdapter):
        def send(self, request, **kwargs):
            request.url = request.url.replace("api.telegram.org", "149.154.167.220")
            request.headers["Host"] = "api.telegram.org"
            return super().send(request, **kwargs)

    session.mount("https://", IPAdapter())
    session.verify = False
    if PROXY_URL:
        session.proxies = {"http": PROXY_URL, "https": PROXY_URL}
    return session


def send_message(text: str, reply_markup=None, parse_mode="Markdown"):
    require_env()
    data = {"chat_id": CHAT_ID, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    result = telegram_session().post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=data,
        timeout=30,
    ).json()
    if not result.get("ok") and parse_mode:
        data.pop("parse_mode", None)
        result = telegram_session().post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=data,
            timeout=30,
        ).json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendMessage 실패: {result}")
    return result


def send_audio(audio_path: str, caption: str = ""):
    require_env()
    data = {"chat_id": CHAT_ID}
    if caption:
        data["caption"] = caption
    with open(audio_path, "rb") as audio:
        result = telegram_session().post(
            f"https://api.telegram.org/bot{TOKEN}/sendAudio",
            data=data,
            files={"audio": audio},
            timeout=60,
        ).json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendAudio 실패: {result}")
    return result


def update_state(**kwargs):
    state = read_json(ENGLISH_STATE_FILE, {})
    state.update(kwargs)
    write_json(ENGLISH_STATE_FILE, state)
    return state


def get_state():
    return read_json(ENGLISH_STATE_FILE, {})


def merge_learned(path: Path, items, key_name: str):
    data = read_json(path, [])
    existing = {item[key_name]: item for item in data if key_name in item}
    today = TODAY()
    for item in items:
        key = item[key_name]
        if key in existing:
            existing[key]["seen_count"] = existing[key].get("seen_count", 1) + 1
            if existing[key].get("weak"):
                existing[key]["weak"] = False
                existing[key]["weak_date"] = None
        else:
            record = {
                key_name: key,
                "date_added": today,
                "category": item.get("category", "unknown"),
                "seen_count": 1,
                "weak": False,
                "weak_date": None,
            }
            for extra in ("pos", "register"):
                if extra in item:
                    record[extra] = item[extra]
            existing[key] = record
    write_json(path, list(existing.values()))


def mark_weak(path: Path, key_name: str, value: str):
    data = read_json(path, [])
    changed = False
    for item in data:
        if item.get(key_name) == value:
            item["weak"] = True
            item["weak_date"] = TODAY()
            changed = True
            break
    if changed:
        write_json(path, data)
    return changed


def load_learned_words(path: Path, key_name: str):
    return [item[key_name] for item in read_json(path, []) if key_name in item]


def load_weak_items(path: Path, key_name: str):
    return [item[key_name] for item in read_json(path, []) if item.get("weak") and key_name in item]


def add_dialogue_history(item: dict):
    add_history(DIALOGUE_HISTORY_FILE, item, limit=90)


def add_history(path: Path, item: dict, limit=90):
    history = read_json(path, [])
    history.append(item)
    write_json(path, history[-limit:])


def recent_history_values(path: Path, key: str, days=3):
    history = read_json(path, [])
    return [item.get(key) for item in history[-days:] if item.get(key)]


def recent_dialogue_domains(days=3):
    history = read_json(DIALOGUE_HISTORY_FILE, [])
    return [item.get("domain") for item in history[-days:] if item.get("domain")]


def dialogue_extra_count():
    state = get_state()
    today = TODAY()
    extras = state.get("dialogue_extras", {})
    return int(extras.get(today, 0))


def increment_dialogue_extra_count():
    state = get_state()
    today = TODAY()
    extras = state.get("dialogue_extras", {})
    extras[today] = int(extras.get(today, 0)) + 1
    state["dialogue_extras"] = extras
    write_json(ENGLISH_STATE_FILE, state)
    return extras[today]


def set_writing_pending(topic_ko: str):
    state = get_state()
    state["writing_pending"] = {"date": TODAY(), "topic_ko": topic_ko}
    write_json(ENGLISH_STATE_FILE, state)


def clear_writing_pending():
    state = get_state()
    state.pop("writing_pending", None)
    write_json(ENGLISH_STATE_FILE, state)


def is_writing_pending():
    return bool(get_state().get("writing_pending"))


def generate_english_tts(text: str, output_name: str):
    check_budget_exit("en")
    output_path = str(PROJECT_DIR / output_name)
    return generate_tts(text, "en-US", output_path)


def generate_english_tts_voice(text: str, output_name: str, voice_name: str):
    check_budget_exit("en")
    output_path = str(PROJECT_DIR / output_name)
    if voice_name and not voice_name.startswith("en-"):
        raise ValueError(f"English TTS voice must start with 'en-': {voice_name}")
    return generate_tts(text, "en-US", output_path, voice_name=voice_name)


def generate_lang_tts(text: str, lang_code: str, output_name: str, budget_lang: str):
    check_budget_exit(budget_lang)
    output_path = str(PROJECT_DIR / output_name)
    return generate_tts(text, lang_code, output_path)
