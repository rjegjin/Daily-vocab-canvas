"""
Inline feedback helpers for non-English vocab cards.
"""
import json
import os
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR.parent / ".secrets" / ".env")

TOKEN = os.getenv("VOCAB_BOT_TOKEN") or os.getenv("GEMINI_BOT_TOKEN")
CHAT_ID = os.getenv("VOCAB_CHAT_ID") or os.getenv("GEMINI_CHAT_ID")
PROXY_URL = os.getenv("TELEGRAM_PROXY_URL")

STATE_FILE = PROJECT_DIR / "vocab_feedback_state.json"
LEARNED_FILES = {
    "ja": PROJECT_DIR / "learned_data_ja.json",
    "zh": PROJECT_DIR / "learned_data_zh.json",
}
SUPPLEMENT_FILES = {
    "ja_rules": PROJECT_DIR / "learned_data_ja_rules.json",
    "zh_tones": PROJECT_DIR / "learned_data_zh_tones.json",
}
LANG_LABELS = {
    "ja": "일본어",
    "zh": "중국어",
    "ja_rules": "일본어 규칙",
    "zh_tones": "중국어 성조",
}


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


def send_message(text: str, reply_markup=None):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("VOCAB_BOT_TOKEN/VOCAB_CHAT_ID 환경 변수가 필요합니다.")
    data = {"chat_id": CHAT_ID, "text": text}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    result = telegram_session().post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=data,
        timeout=30,
    ).json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendMessage 실패: {result}")
    return result


def save_latest_vocab(lang: str, items: list):
    state = read_json(STATE_FILE, {})
    state[f"latest_{lang}_vocab"] = {
        "date": date.today().isoformat(),
        "items": items,
    }
    write_json(STATE_FILE, state)


def latest_vocab(lang: str):
    state = read_json(STATE_FILE, {})
    return state.get(f"latest_{lang}_vocab", {}).get("items", [])


def item_label(lang: str, item: dict):
    if lang == "ja":
        reading = item.get("furigana", "")
    elif lang == "zh":
        reading = item.get("pinyin", "")
    else:
        reading = ""
    word = item.get("word", "")
    meaning = item.get("meaning", "")
    pieces = [word]
    if reading:
        pieces.append(f"({reading})")
    if meaning:
        pieces.append(f"- {meaning}")
    return " ".join(pieces)[:48]


def mark_weak(lang: str, index: int):
    items = latest_vocab(lang)
    if index < 0 or index >= len(items):
        return None, False
    word = items[index].get("word")
    path = LEARNED_FILES.get(lang)
    if not word or not path:
        return word, False

    data = read_json(path, [])
    changed = False
    for item in data:
        if item.get("word") == word:
            item["weak"] = True
            item["weak_date"] = date.today().isoformat()
            changed = True
            break
    if changed:
        write_json(path, data)
    return word, changed


def weak_keyboard(lang: str):
    rows = []
    for idx, item in enumerate(latest_vocab(lang)[:12]):
        rows.append([
            InlineKeyboardButton(
                item_label(lang, item),
                callback_data=f"{lang}:vocab:weak:{idx}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def send_feedback_buttons(lang: str):
    label = LANG_LABELS.get(lang, lang)
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 다 알아", callback_data=f"{lang}:vocab:ok"),
            InlineKeyboardButton("⚠️ 모르는 거 있어", callback_data=f"{lang}:vocab:weak_prompt"),
        ]
    ]).to_dict()
    send_message(f"{label} 단어 카드 피드백을 선택하세요.", reply_markup=reply_markup)


def merge_supplement_items(kind: str, items: list, id_key="id"):
    path = SUPPLEMENT_FILES[kind]
    data = read_json(path, [])
    existing = {item[id_key]: item for item in data if id_key in item}
    today = date.today().isoformat()
    for item in items:
        item_id = item[id_key]
        if item_id in existing:
            existing[item_id]["seen_count"] = existing[item_id].get("seen_count", 1) + 1
            existing[item_id]["last_seen"] = today
            if existing[item_id].get("weak"):
                existing[item_id]["weak"] = False
                existing[item_id]["weak_date"] = None
        else:
            existing[item_id] = {
                **item,
                "date_added": today,
                "last_seen": today,
                "seen_count": 1,
                "weak": False,
                "weak_date": None,
            }
    write_json(path, list(existing.values()))


def load_supplement_seen(kind: str, id_key="id"):
    return [item[id_key] for item in read_json(SUPPLEMENT_FILES[kind], []) if id_key in item]


def load_supplement_weak(kind: str, id_key="id"):
    return [item[id_key] for item in read_json(SUPPLEMENT_FILES[kind], []) if item.get("weak") and id_key in item]


def save_latest_supplement(kind: str, items: list):
    state = read_json(STATE_FILE, {})
    state[f"latest_{kind}"] = {
        "date": date.today().isoformat(),
        "items": items,
    }
    write_json(STATE_FILE, state)


def latest_supplement(kind: str):
    state = read_json(STATE_FILE, {})
    return state.get(f"latest_{kind}", {}).get("items", [])


def supplement_label(item: dict):
    return (
        item.get("title")
        or item.get("label")
        or item.get("base_syllable")
        or item.get("id")
        or "item"
    )[:48]


def supplement_keyboard(kind: str):
    rows = []
    for idx, item in enumerate(latest_supplement(kind)[:12]):
        rows.append([
            InlineKeyboardButton(
                supplement_label(item),
                callback_data=f"{kind}:weak:{idx}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def mark_supplement_weak(kind: str, index: int, id_key="id"):
    items = latest_supplement(kind)
    if index < 0 or index >= len(items):
        return None, False
    item_id = items[index].get(id_key)
    path = SUPPLEMENT_FILES.get(kind)
    if not item_id or not path:
        return item_id, False
    data = read_json(path, [])
    changed = False
    for item in data:
        if item.get(id_key) == item_id:
            item["weak"] = True
            item["weak_date"] = date.today().isoformat()
            changed = True
            break
    if changed:
        write_json(path, data)
    return supplement_label(items[index]), changed


def send_supplement_feedback_buttons(kind: str):
    label = LANG_LABELS.get(kind, kind)
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 이해했어", callback_data=f"{kind}:ok"),
            InlineKeyboardButton("⚠️ 헷갈려", callback_data=f"{kind}:weak_prompt"),
        ]
    ]).to_dict()
    send_message(f"{label} 피드백을 선택하세요.", reply_markup=reply_markup)
