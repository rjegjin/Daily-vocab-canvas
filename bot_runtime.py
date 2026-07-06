import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

PROJECT_DIR = Path(__file__).resolve().parent
DOTENV_PATH = PROJECT_DIR.parent / ".secrets" / ".env"
if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)
else:
    load_dotenv()

VENV_PY = sys.executable
RUN_LOG_DIR = PROJECT_DIR / "run_logs"
IKB = InlineKeyboardButton

SCRIPTS = {
    "es": PROJECT_DIR / "spanish.py",
    "ja": PROJECT_DIR / "japanese.py",
    "zh": PROJECT_DIR / "chinese.py",
    "es_patterns": PROJECT_DIR / "main_patterns.py",
    "ja_rules": PROJECT_DIR / "japanese_rules.py",
    "zh_tones": PROJECT_DIR / "chinese_tones.py",
    "ja_dialogue": PROJECT_DIR / "japanese_dialogue.py",
    "zh_dialogue": PROJECT_DIR / "chinese_dialogue.py",
    "en_vocab": PROJECT_DIR / "english_vocab.py",
    "en_phrase": PROJECT_DIR / "english_phrase.py",
    "en_dialogue": PROJECT_DIR / "english_dialogue.py",
    "en_writing": PROJECT_DIR / "english_writing.py",
    "monthly": PROJECT_DIR / "monthly_report.py",
}

LANG_LABEL = {
    "es": "스페인어",
    "ja": "일본어",
    "zh": "중국어",
    "es_patterns": "ES 패턴",
    "ja_rules": "JA 규칙",
    "zh_tones": "ZH 성조",
    "ja_dialogue": "JA 회화",
    "zh_dialogue": "ZH 회화",
    "en_vocab": "EN 단어",
    "en_phrase": "EN 표현",
    "en_dialogue": "EN 회화",
    "en_writing": "EN 글쓰기",
    "monthly": "월간 리포트",
}


def get_token(*env_names: str) -> str | None:
    for name in env_names:
        value = os.getenv(name)
        if value:
            return value
    return os.getenv("VOCAB_BOT_TOKEN") or os.getenv("GEMINI_BOT_TOKEN")


def language_env(token_envs=(), chat_envs=()) -> dict[str, str]:
    env = os.environ.copy()
    token = get_token(*token_envs)
    chat_id = None
    for name in chat_envs:
        if os.getenv(name):
            chat_id = os.getenv(name)
            break
    chat_id = chat_id or os.getenv("VOCAB_CHAT_ID") or os.getenv("GEMINI_CHAT_ID")
    if token:
        env["VOCAB_BOT_TOKEN"] = token
    if chat_id:
        env["VOCAB_CHAT_ID"] = chat_id
    return env


def run_script(lang: str, env: dict[str, str] | None = None) -> str:
    if lang not in SCRIPTS:
        return "알 수 없는 작업입니다."
    extra_args = ["--force"] if lang == "en_writing" else []
    RUN_LOG_DIR.mkdir(exist_ok=True)
    log_path = RUN_LOG_DIR / f"{lang}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [VENV_PY, str(SCRIPTS[lang]), *extra_args],
            cwd=PROJECT_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    return f"{LANG_LABEL.get(lang, lang)} 실행 시작\n로그: {log_path}"


def run_many(langs: list[str] | tuple[str, ...], env: dict[str, str] | None = None) -> str:
    return "\n".join(run_script(lang, env=env) for lang in langs)


def english_daily_jobs() -> list[str]:
    today = datetime.now()
    jobs = ["en_vocab", "en_dialogue"]
    if today.weekday() in (0, 2, 4):
        jobs.append("en_phrase")
    if today.weekday() == 6:
        jobs.append("en_writing")
    return jobs


def cost_summary() -> str:
    try:
        from card_engine import load_budget, monthly_gemini_total, monthly_tts_chars

        today = date.today()
        budget = load_budget()
        used_g = monthly_gemini_total()
        tts_ch = monthly_tts_chars()
        tts_cost = max(0, tts_ch - 1_000_000) / 1_000_000 * 4.0
        total = used_g + tts_cost
        limit = budget["monthly_limit_usd"]
        pct = total / limit * 100 if limit > 0 else 0
        projected = total / today.day * 30 if today.day else 0
        lines = [
            f"{today.year}-{today.month:02d} 비용 현황",
            "",
            f"AI 생성: ${used_g:.4f}",
        ]
        for lang, label in {"es": "ES", "ja": "JA", "zh": "ZH", "en": "EN"}.items():
            enabled = budget["lang_enabled"].get(lang, True)
            lines.append(f"{label}: {'enabled' if enabled else 'disabled'}")
        lines.extend(
            [
                f"TTS: {tts_ch:,} chars / ${tts_cost:.5f}",
                f"합계: ${total:.4f} / 예산 ${limit:.2f} ({pct:.1f}%)",
                f"월말 예상: ${projected:.2f}",
            ]
        )
        return "\n".join(lines)
    except Exception as exc:
        return f"비용 조회 실패: {exc}"


def stats_summary() -> str:
    lines = ["학습 및 단어장 통계", ""]
    today_str = str(date.today())
    this_month = today_str[:7]
    files = {
        "ES": ("learned_data_es.json", "word"),
        "JA": ("learned_data_ja.json", "word"),
        "ZH": ("learned_data_zh.json", "word"),
        "EN vocab": ("learned_data_en.json", "word"),
        "EN phrase": ("learned_data_en_phrase.json", "phrase"),
    }
    for label, (filename, key_name) in files.items():
        path = PROJECT_DIR / filename
        if not path.exists():
            lines.append(f"{label}: 데이터 없음")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            total = len(data) if isinstance(data, list) else 0
            weak = sum(1 for item in data if isinstance(item, dict) and item.get("weak"))
            month_count = sum(
                1 for item in data if isinstance(item, dict) and item.get("date_added", "").startswith(this_month)
            )
            recent = [
                item[key_name]
                for item in sorted(data, key=lambda item: item.get("date_added", "") if isinstance(item, dict) else "")
                if isinstance(item, dict) and key_name in item
            ][-5:]
            lines.append(f"{label}: 총 {total}개 / 이번 달 +{month_count} / 취약 {weak}")
            if recent:
                lines.append(f"최근: {', '.join(recent)}")
        except Exception as exc:
            lines.append(f"{label}: 읽기 실패 ({exc})")
    return "\n".join(lines)


def english_latest_items(kind: str):
    from english_core import get_state

    return get_state().get(f"latest_en_{kind}", {}).get("items", [])


def english_weak_keyboard(kind: str):
    key = "word" if kind == "vocab" else "phrase"
    rows = []
    for idx, item in enumerate(english_latest_items(kind)[:12]):
        rows.append([IKB(str(item.get(key, idx + 1))[:48], callback_data=f"en:{kind}:weak:{idx}")])
    return InlineKeyboardMarkup(rows)


def english_mark_weak(kind: str, index: int):
    from english_core import LEARNED_EN_FILE, LEARNED_EN_PHRASE_FILE, mark_weak

    items = english_latest_items(kind)
    if index < 0 or index >= len(items):
        return None, False
    if kind == "vocab":
        value = items[index].get("word")
        changed = mark_weak(LEARNED_EN_FILE, "word", value)
    else:
        value = items[index].get("phrase")
        changed = mark_weak(LEARNED_EN_PHRASE_FILE, "phrase", value)
    return value, changed


def send_more_english_dialogue():
    from english_dialogue import send_more_dialogue

    return send_more_dialogue()


def send_writing_feedback(text: str):
    from english_writing import send_feedback

    send_feedback(text)


def is_writing_pending():
    from english_core import is_writing_pending as _is_writing_pending

    return _is_writing_pending()


def looks_like_english(text: str) -> bool:
    if not text:
        return False
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    letters = sum(1 for char in text if char.isalpha())
    ascii_letters = sum(1 for char in text if char.isascii() and char.isalpha())
    return ascii_chars / len(text) > 0.6 and ascii_letters / max(letters, 1) > 0.6


def vocab_weak_keyboard(lang: str):
    from vocab_feedback import weak_keyboard

    return weak_keyboard(lang)


def vocab_mark_weak(lang: str, index: int):
    from vocab_feedback import mark_weak

    return mark_weak(lang, index)


def supplement_keyboard(kind: str):
    from vocab_feedback import supplement_keyboard

    return supplement_keyboard(kind)


def supplement_mark_weak(kind: str, index: int):
    from vocab_feedback import mark_supplement_weak

    return mark_supplement_weak(kind, index)


def send_more_lang_dialogue(lang: str):
    from english_core import ENGLISH_STATE_FILE, TODAY, get_state, write_json

    state = get_state()
    today = TODAY()
    state_key = f"{lang}_dialogue_extras"
    extras = state.get(state_key, {})
    if int(extras.get(today, 0)) >= 3:
        return False
    extras[today] = int(extras.get(today, 0)) + 1
    state[state_key] = extras
    write_json(ENGLISH_STATE_FILE, state)
    if lang == "ja":
        from japanese_dialogue import send_more_dialogue
    else:
        from chinese_dialogue import send_more_dialogue
    return bool(send_more_dialogue())


async def reply_run(update: Update, key: str, env: dict[str, str]):
    msg = await asyncio.to_thread(run_script, key, env)
    await update.message.reply_text(msg)


async def callback_run(query, key: str, env: dict[str, str], menu):
    msg = await asyncio.to_thread(run_script, key, env)
    await query.edit_message_text(msg, reply_markup=menu())


def make_scheduler(disable_env: str):
    enabled = os.getenv(disable_env, "0").lower() not in ("1", "true", "yes", "on")
    if not enabled:
        return None
    return AsyncIOScheduler(timezone="Asia/Seoul")


def run_polling_bot(
    *,
    bot_name: str,
    token_envs: tuple[str, ...],
    chat_envs: tuple[str, ...],
    menu_reply,
    menu_inline,
    handle_text,
    handle_callback,
    post_init=None,
    extra_handlers=None,
):
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
    token = get_token(*token_envs)
    if not token:
        print(f"{bot_name}: bot token 환경 변수가 없습니다.")
        return

    async def cmd_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            await update.message.reply_text(f"{bot_name} menu", reply_markup=menu_reply())
            await update.message.reply_text("작업을 선택하세요:", reply_markup=menu_inline())

    app = Application.builder().token(token)
    if post_init:
        app = app.post_init(post_init)
    app = app.build()
    app.add_handler(CommandHandler("start", cmd_manage))
    app.add_handler(CommandHandler("manage", cmd_manage))
    for handler in extra_handlers or []:
        app.add_handler(handler)
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print(f"{bot_name} started")
    app.run_polling(drop_pending_updates=True)
