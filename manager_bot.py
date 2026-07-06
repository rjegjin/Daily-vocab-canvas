"""
Vocab Card Bot — 자체 관리 봇
VOCAB_BOT_TOKEN으로 상시 실행, 자기 채팅방 직접 관리.
- /start, /manage : 인라인 키보드 (세련된 레이아웃 적용) + 상주 메뉴(ReplyKeyboard)
- /run_es /run_ja /run_zh : 언어별 즉시 실행
- 매일 05:00 KST 3개 국어 카드, 05:10 KST 부가 학습 시리즈, 06:00 영어 플루언시 자동 발송
"""
import asyncio
import logging
import os
import subprocess
import json
import sys
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# -------------------------------------------------------------------
# 경로 및 환경 변수 설정
# -------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# .secrets/.env 우선 로드
dotenv_path = os.path.join(os.path.dirname(PROJECT_DIR), ".secrets", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

TOKEN   = os.getenv("VOCAB_BOT_TOKEN")
VENV_PY = sys.executable

SCRIPTS = {
    "es": os.path.join(PROJECT_DIR, "spanish.py"),
    "ja": os.path.join(PROJECT_DIR, "japanese.py"),
    "zh": os.path.join(PROJECT_DIR, "chinese.py"),
    "es_patterns": os.path.join(PROJECT_DIR, "main_patterns.py"),
    "ja_rules": os.path.join(PROJECT_DIR, "japanese_rules.py"),
    "zh_tones": os.path.join(PROJECT_DIR, "chinese_tones.py"),
    "ja_dialogue": os.path.join(PROJECT_DIR, "japanese_dialogue.py"),
    "zh_dialogue": os.path.join(PROJECT_DIR, "chinese_dialogue.py"),
    "en_vocab": os.path.join(PROJECT_DIR, "english_vocab.py"),
    "en_phrase": os.path.join(PROJECT_DIR, "english_phrase.py"),
    "en_dialogue": os.path.join(PROJECT_DIR, "english_dialogue.py"),
    "en_writing": os.path.join(PROJECT_DIR, "english_writing.py"),
    "monthly": os.path.join(PROJECT_DIR, "monthly_report.py"),
}
LANG_LABEL = {
    "es": "🇪🇸 스페인어",
    "ja": "🇯🇵 일본어",
    "zh": "🇨🇳 중국어",
    "en_vocab": "🇬🇧 EN 단어",
    "en_phrase": "💬 EN 표현",
    "en_dialogue": "🎬 EN 회화",
    "en_writing": "✍️ EN 글쓰기",
    "ja_dialogue": "🎬 JA 회화",
    "zh_dialogue": "🎬 ZH 회화",
}
DAILY_LANGS = ("es", "ja", "zh")
SUPPLEMENT_LANGS = ("es_patterns", "ja_rules", "zh_tones")
ENGLISH_DAILY_LANGS = ("en_vocab", "en_dialogue")
ASIAN_DIALOGUE_LANGS = ("ja_dialogue", "zh_dialogue")
RUN_LOG_DIR = Path(PROJECT_DIR) / "run_logs"

# 로깅 설정
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

IKB = InlineKeyboardButton
SCHEDULER_ENABLED = os.getenv("VOCAB_MANAGER_DISABLE_SCHEDULER", "0") not in ("1", "true", "yes", "on")

# -------------------------------------------------------------------
# 보조 함수
# -------------------------------------------------------------------
def _run(lang: str) -> str:
    if lang not in SCRIPTS:
        return "❌ 알 수 없는 언어입니다."
    extra_args = []
    if lang == "en_writing":
        extra_args.append("--force")
    RUN_LOG_DIR.mkdir(exist_ok=True)
    log_path = RUN_LOG_DIR / f"{lang}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_path, "a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [VENV_PY, SCRIPTS[lang], *extra_args],
            cwd=PROJECT_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    label = LANG_LABEL.get(lang, lang)
    return f"{label} 카드 생성 시작 (백그라운드 진행, 완료 시 전송)\n로그: {log_path}"

def _run_all() -> str:
    messages = [_run(lang) for lang in DAILY_LANGS]
    return "🌍 전체 언어 카드 생성을 백그라운드에서 시작했습니다!\n\n" + "\n".join(messages)

def _run_supplements() -> str:
    messages = [_run(lang) for lang in SUPPLEMENT_LANGS]
    return "📚 부가 학습 시리즈를 백그라운드에서 시작했습니다!\n\n" + "\n".join(messages)

def _run_english_daily() -> str:
    today = datetime.now()
    scripts = list(ENGLISH_DAILY_LANGS)
    if today.weekday() in (0, 2, 4):
        scripts.append("en_phrase")
    if today.weekday() == 6:
        scripts.append("en_writing")
    messages = [_run(lang) for lang in scripts]
    return "🇬🇧 영어 플루언시 시리즈를 백그라운드에서 시작했습니다!\n\n" + "\n".join(messages)

def _run_asian_dialogues() -> str:
    messages = [_run(lang) for lang in ASIAN_DIALOGUE_LANGS]
    return "🎬 일본어/중국어 회화 시리즈를 백그라운드에서 시작했습니다!\n\n" + "\n".join(messages)

def _get_cost_summary() -> str:
    """cost.py 로직을 인라인으로 실행해 텔레그램용 텍스트 반환"""
    try:
        from card_engine import monthly_gemini_total, monthly_tts_chars, load_budget
        from datetime import date

        today  = date.today()
        budget = load_budget()
        used_g = monthly_gemini_total()
        tts_ch = monthly_tts_chars()
        billable = max(0, tts_ch - 1_000_000)
        tts_cost = billable / 1_000_000 * 4.0
        total  = used_g + tts_cost
        limit  = budget['monthly_limit_usd']
        pct    = total / limit * 100 if limit > 0 else 0
        projected = total / today.day * 30 if today.day > 0 else 0

        LANG_LABEL = {'es': '🇪🇸', 'ja': '🇯🇵', 'zh': '🇨🇳', 'en': '🇬🇧'}

        lines = [
            f"💰 *{today.year}년 {today.month}월 비용 현황*",
            "",
            f"AI 생성: *${used_g:.4f}*",
        ]
        # 언어별 비활성 표시
        for lang, lbl in LANG_LABEL.items():
            enabled = budget['lang_enabled'].get(lang, True)
            lines.append(f"  {lbl} {'✅' if enabled else '🔴 비활성'}")

        tts_status = '✅' if budget['tts_enabled'] else '🔴 비활성'
        lines.append(f"TTS: {tts_ch:,}자  ${tts_cost:.5f}  {tts_status}")
        lines.append(f"")
        lines.append(f"합계: *${total:.4f}*  /  예산 ${limit:.2f}  ({pct:.1f}%)")
        lines.append(f"월말 예상: *${projected:.2f}*{'  ⚠️' if projected > limit else ''}")
        return '\n'.join(lines)
    except Exception as e:
        return f"❌ 비용 조회 실패: {e}"

def _get_stats() -> str:
    stats_msg = "📈 *학습 및 단어장 통계*\n\n"
    json_files = {
        "es": ("learned_data_es.json", "word"),
        "ja": ("learned_data_ja.json", "word"),
        "zh": ("learned_data_zh.json", "word"),
        "en_vocab": ("learned_data_en.json", "word"),
        "en_phrase": ("learned_data_en_phrase.json", "phrase"),
    }
    today_str = str(date.today())
    this_month = today_str[:7]  # "YYYY-MM"

    for lang, (fname, key_name) in json_files.items():
        filepath = os.path.join(PROJECT_DIR, fname)
        if not os.path.exists(filepath):
            stats_msg += f"- {LANG_LABEL.get(lang, lang)}: 데이터 없음\n\n"
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        total = len(data)
        weak  = sum(1 for d in data if d.get('weak'))
        this_month_count = sum(1 for d in data if d.get('date_added', '').startswith(this_month))
        recent = [d[key_name] for d in sorted(data, key=lambda x: x.get('date_added', ''))[-5:] if key_name in d]
        stats_msg += f"*{LANG_LABEL.get(lang, lang)}*\n"
        stats_msg += f"  총 {total}개 · 이번 달 +{this_month_count}개 · 취약 {weak}개\n"
        stats_msg += f"  최근: {', '.join(recent)}\n\n"

    history_files = {
        "🎬 EN 회화": ("dialogue_history.json", "scenario_ko"),
        "🎬 JA 회화": ("dialogue_history_ja.json", "scenario_ko"),
        "🎬 ZH 회화": ("dialogue_history_zh.json", "scenario_ko"),
        "✍️ EN 글쓰기": ("writing_sessions.json", "topic_ko"),
    }
    stats_msg += "*회화/글쓰기 이력*\n"
    for label, (fname, key_name) in history_files.items():
        filepath = os.path.join(PROJECT_DIR, fname)
        if not os.path.exists(filepath):
            stats_msg += f"  {label}: 데이터 없음\n"
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
            total = len(data)
            this_month_count = sum(1 for d in data if isinstance(d, dict) and d.get('date', '').startswith(this_month))
            latest = ""
            for item in reversed(data[-5:]):
                if isinstance(item, dict) and item.get(key_name):
                    latest = item[key_name]
                    break
            stats_msg += f"  {label}: 총 {total}개 · 이번 달 +{this_month_count}개"
            if latest:
                stats_msg += f" · 최근: {latest[:32]}"
            stats_msg += "\n"
        except Exception as e:
            stats_msg += f"  {label}: 읽기 실패 ({e})\n"
    stats_msg += "\n"

    # API 비용 확인
    stats_msg += "💰 *오늘의 API 비용*\n"
    cost_path = os.path.join(PROJECT_DIR, 'cost_log.json')
    if os.path.exists(cost_path):
        try:
            with open(cost_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            if today_str in log_data and '_daily_total_usd' in log_data[today_str]:
                stats_msg += f"- 누적 금액: ${log_data[today_str]['_daily_total_usd']:.4f}\n"
            else:
                stats_msg += "- 오늘 발생한 과금 없음\n"
        except Exception as e:
            stats_msg += f"- 로그 읽기 실패: {e}\n"
    else:
        stats_msg += "- 비용 로그 파일이 없습니다.\n"

    return stats_msg

# -------------------------------------------------------------------
# 키보드 빌더
# -------------------------------------------------------------------
def _menu_inline() -> InlineKeyboardMarkup:
    """세련된 2열/1열 혼합 레이아웃 메뉴"""
    return InlineKeyboardMarkup([
        [
            IKB("🇪🇸 스페인어", callback_data="run:es"),
            IKB("🇯🇵 일본어", callback_data="run:ja")
        ],
        [
            IKB("🇨🇳 중국어", callback_data="run:zh"),
            IKB("🔄 전체 일괄 생성", callback_data="run:all")
        ],
        [
            IKB("📝 ES 패턴", callback_data="run:es_patterns"),
            IKB("📐 JA 규칙", callback_data="run:ja_rules")
        ],
        [
            IKB("🎵 ZH 성조", callback_data="run:zh_tones"),
            IKB("📊 학습량 및 비용", callback_data="info:stats")
        ],
        [
            IKB("💰 비용 현황", callback_data="info:cost"),
            IKB("📅 월간 성취 리포트", callback_data="run:monthly")
        ],
        [
            IKB("🇬🇧 EN 단어", callback_data="run:en_vocab"),
            IKB("💬 EN 표현", callback_data="run:en_phrase")
        ],
        [
            IKB("🎬 EN 회화", callback_data="run:en_dialogue"),
            IKB("✍️ EN 글쓰기", callback_data="run:en_writing")
        ],
        [
            IKB("🇬🇧 EN 오늘 전체", callback_data="run:english_daily")
        ],
        [
            IKB("🎬 JA 회화", callback_data="run:ja_dialogue"),
            IKB("🎬 ZH 회화", callback_data="run:zh_dialogue")
        ],
        [
            IKB("🎬 JA/ZH 회화", callback_data="run:asian_dialogues")
        ]
    ])

def _menu_reply() -> ReplyKeyboardMarkup:
    """하단에 항상 상주하는 메뉴 키보드"""
    return ReplyKeyboardMarkup([
        ["🇪🇸 스페인어", "🇯🇵 일본어", "🇨🇳 중국어"],
        ["📝 ES 패턴", "📐 JA 규칙", "🎵 ZH 성조"],
        ["🇬🇧 EN 단어", "💬 EN 표현", "🎬 EN 회화"],
        ["✍️ EN 글쓰기", "🇬🇧 EN 오늘 전체"],
        ["🎬 JA 회화", "🎬 ZH 회화", "🎬 JA/ZH 회화"],
        ["🔄 전체 일괄 생성", "📊 통계 및 비용 조회"],
        ["💰 비용 현황", "📅 월간 성취 리포트"]
    ], resize_keyboard=True)

def _english_latest_items(kind: str):
    from english_core import get_state
    state_key = f"latest_en_{kind}"
    return get_state().get(state_key, {}).get("items", [])

def _english_mark_weak(kind: str, index: int):
    from english_core import LEARNED_EN_FILE, LEARNED_EN_PHRASE_FILE, mark_weak
    items = _english_latest_items(kind)
    if index < 0 or index >= len(items):
        return None, False
    if kind == "vocab":
        value = items[index].get("word")
        changed = mark_weak(LEARNED_EN_FILE, "word", value)
    else:
        value = items[index].get("phrase")
        changed = mark_weak(LEARNED_EN_PHRASE_FILE, "phrase", value)
    return value, changed

def _english_weak_keyboard(kind: str):
    items = _english_latest_items(kind)
    key = "word" if kind == "vocab" else "phrase"
    rows = []
    for idx, item in enumerate(items[:12]):
        label = item.get(key, f"{idx + 1}")
        rows.append([IKB(label[:48], callback_data=f"en:{kind}:weak:{idx}")])
    return InlineKeyboardMarkup(rows)

def _send_more_dialogue():
    from english_dialogue import send_more_dialogue
    return send_more_dialogue()

def _send_writing_feedback(text: str):
    from english_writing import send_feedback
    send_feedback(text)

def _is_writing_pending():
    from english_core import is_writing_pending
    return is_writing_pending()

def _looks_like_english(text: str) -> bool:
    if not text:
        return False
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    letters = sum(1 for c in text if c.isalpha())
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    return ascii_chars / len(text) > 0.6 and ascii_letters / max(letters, 1) > 0.6

def _vocab_weak_keyboard(lang: str):
    from vocab_feedback import weak_keyboard
    return weak_keyboard(lang)

def _vocab_mark_weak(lang: str, index: int):
    from vocab_feedback import mark_weak
    return mark_weak(lang, index)

def _supplement_keyboard(kind: str):
    from vocab_feedback import supplement_keyboard
    return supplement_keyboard(kind)

def _supplement_mark_weak(kind: str, index: int):
    from vocab_feedback import mark_supplement_weak
    return mark_supplement_weak(kind, index)

def _send_more_lang_dialogue(lang: str):
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

# -------------------------------------------------------------------
# 핸들러
# -------------------------------------------------------------------
async def cmd_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "📚 *Vocab Card Bot Manager*\n메뉴를 선택하세요:",
            parse_mode="Markdown",
            reply_markup=_menu_reply() # 하단 메뉴 활성화
        )
        # 인라인 메뉴도 함께 발송
        await update.message.reply_text(
            "원하시는 작업을 선택하세요:",
            reply_markup=_menu_inline()
        )

async def handle_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """하단 상주 메뉴 버튼 클릭 처리"""
    text = update.message.text

    if text == "🇪🇸 스페인어":
        msg = await asyncio.to_thread(_run, "es")
        await update.message.reply_text(msg)
    elif text == "🇯🇵 일본어":
        msg = await asyncio.to_thread(_run, "ja")
        await update.message.reply_text(msg)
    elif text == "🇨🇳 중국어":
        msg = await asyncio.to_thread(_run, "zh")
        await update.message.reply_text(msg)
    elif text == "📝 ES 패턴":
        msg = await asyncio.to_thread(_run, "es_patterns")
        await update.message.reply_text(msg)
    elif text == "📐 JA 규칙":
        msg = await asyncio.to_thread(_run, "ja_rules")
        await update.message.reply_text(msg)
    elif text == "🎵 ZH 성조":
        msg = await asyncio.to_thread(_run, "zh_tones")
        await update.message.reply_text(msg)
    elif text == "🎬 JA 회화":
        msg = await asyncio.to_thread(_run, "ja_dialogue")
        await update.message.reply_text(msg)
    elif text == "🎬 ZH 회화":
        msg = await asyncio.to_thread(_run, "zh_dialogue")
        await update.message.reply_text(msg)
    elif text == "🎬 JA/ZH 회화":
        msg = await asyncio.to_thread(_run_asian_dialogues)
        await update.message.reply_text(msg)
    elif text == "🇬🇧 EN 단어":
        msg = await asyncio.to_thread(_run, "en_vocab")
        await update.message.reply_text(msg)
    elif text == "💬 EN 표현":
        msg = await asyncio.to_thread(_run, "en_phrase")
        await update.message.reply_text(msg)
    elif text == "🎬 EN 회화":
        msg = await asyncio.to_thread(_run, "en_dialogue")
        await update.message.reply_text(msg)
    elif text == "✍️ EN 글쓰기":
        msg = await asyncio.to_thread(_run, "en_writing")
        await update.message.reply_text(msg)
    elif text == "🇬🇧 EN 오늘 전체":
        msg = await asyncio.to_thread(_run_english_daily)
        await update.message.reply_text(msg)
    elif text == "🔄 전체 일괄 생성":
        msg = await asyncio.to_thread(_run_all)
        await update.message.reply_text(msg)
    elif text == "📊 통계 및 비용 조회":
        msg = await asyncio.to_thread(_get_stats)
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif text == "💰 비용 현황":
        msg = await asyncio.to_thread(_get_cost_summary)
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif text == "📅 월간 성취 리포트":
        msg = await asyncio.to_thread(_run, "monthly")
        await update.message.reply_text(msg)
    elif (
        await asyncio.to_thread(_is_writing_pending)
        and len(text.split()) >= 40
        and _looks_like_english(text)
    ):
        await update.message.reply_text("✍️ 글쓰기 피드백을 생성 중입니다. 완료되면 별도 메시지로 전송됩니다.")
        await asyncio.to_thread(_send_writing_feedback, text)

async def cmd_writing_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
    else:
        text = " ".join(context.args)
    if len(text.split()) < 20:
        await update.message.reply_text("피드백할 영어 글을 이 명령 뒤에 붙이거나, 글 메시지에 답장으로 /writing_feedback 을 보내세요.")
        return
    await update.message.reply_text("✍️ 글쓰기 피드백을 생성 중입니다. 완료되면 별도 메시지로 전송됩니다.")
    await asyncio.to_thread(_send_writing_feedback, text)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "run:all":
        msg = await asyncio.to_thread(_run_all)
        await query.edit_message_text(f"📚 *Vocab Card Bot*\n\n{msg}", parse_mode="Markdown", reply_markup=_menu_inline())
    elif data == "run:english_daily":
        msg = await asyncio.to_thread(_run_english_daily)
        await query.edit_message_text(f"📚 *Vocab Card Bot*\n\n{msg}", parse_mode="Markdown", reply_markup=_menu_inline())
    elif data == "run:asian_dialogues":
        msg = await asyncio.to_thread(_run_asian_dialogues)
        await query.edit_message_text(f"📚 *Vocab Card Bot*\n\n{msg}", parse_mode="Markdown", reply_markup=_menu_inline())
    elif data.startswith("run:"):
        lang = data.split(":")[-1]
        msg = await asyncio.to_thread(_run, lang)
        await query.edit_message_text(f"📚 *Vocab Card Bot*\n\n{msg}", parse_mode="Markdown", reply_markup=_menu_inline())
    elif data.startswith("en:"):
        parts = data.split(":")
        kind = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        if kind in ("vocab", "phrase") and action == "ok":
            await query.message.reply_text("✅ 기록했습니다.")
        elif kind in ("vocab", "phrase") and action == "weak_prompt":
            label = "단어" if kind == "vocab" else "표현"
            await query.message.reply_text(f"헷갈리는 {label}를 선택하세요:", reply_markup=await asyncio.to_thread(_english_weak_keyboard, kind))
        elif kind in ("vocab", "phrase") and action == "weak" and len(parts) == 4:
            value, changed = await asyncio.to_thread(_english_mark_weak, kind, int(parts[3]))
            if changed:
                await query.message.reply_text(f"⚠️ 취약 항목으로 표시했습니다: {value}")
            else:
                await query.message.reply_text("⚠️ 항목을 찾지 못했습니다.")
        elif kind == "dialogue" and action == "more":
            ok = await asyncio.to_thread(_send_more_dialogue)
            if ok:
                await query.message.reply_text("🔁 비슷한 상황을 추가 생성했습니다.")
            else:
                await query.message.reply_text("오늘은 더 이상 생성할 수 없어요. 3회 제한입니다.")
        elif kind == "dialogue" and action == "hard":
            await query.message.reply_text("💪 기록했습니다. 다음 회화에서 비슷한 난이도 표현을 더 보강하겠습니다.")
        elif kind == "dialogue" and action == "ok":
            await query.message.reply_text("✅ 자신 있음으로 기록했습니다.")
    elif data.startswith(("ja_rules:", "zh_tones:")):
        parts = data.split(":")
        kind = parts[0]
        action = parts[1] if len(parts) > 1 else ""
        label = "일본어 규칙" if kind == "ja_rules" else "중국어 성조"
        if action == "ok":
            await query.message.reply_text(f"✅ {label} 이해로 기록했습니다.")
        elif action == "weak_prompt":
            await query.message.reply_text(
                f"헷갈리는 {label} 항목을 선택하세요:",
                reply_markup=await asyncio.to_thread(_supplement_keyboard, kind),
            )
        elif action == "weak" and len(parts) == 3:
            value, changed = await asyncio.to_thread(_supplement_mark_weak, kind, int(parts[2]))
            if changed:
                await query.message.reply_text(f"⚠️ 취약 항목으로 표시했습니다: {value}")
            else:
                await query.message.reply_text("⚠️ 항목을 찾지 못했습니다.")
    elif data.startswith(("ja:dialogue:", "zh:dialogue:")):
        parts = data.split(":")
        lang = parts[0]
        action = parts[2] if len(parts) > 2 else ""
        label = "일본어" if lang == "ja" else "중국어"
        if action == "more":
            ok = await asyncio.to_thread(_send_more_lang_dialogue, lang)
            if ok:
                await query.message.reply_text(f"🔁 {label} 비슷한 상황을 추가 생성했습니다.")
            else:
                await query.message.reply_text(f"오늘은 더 이상 생성할 수 없어요. 3회 제한입니다.")
        elif action == "hard":
            await query.message.reply_text(f"💪 {label} 회화 어려움으로 기록했습니다.")
        elif action == "ok":
            await query.message.reply_text(f"✅ {label} 회화 자신 있음으로 기록했습니다.")
    elif data.startswith(("ja:vocab:", "zh:vocab:")):
        parts = data.split(":")
        lang = parts[0]
        action = parts[2] if len(parts) > 2 else ""
        lang_label = "일본어" if lang == "ja" else "중국어"
        if action == "ok":
            await query.message.reply_text(f"✅ {lang_label} 단어 카드 기록했습니다.")
        elif action == "weak_prompt":
            await query.message.reply_text(
                f"헷갈리는 {lang_label} 단어를 선택하세요:",
                reply_markup=await asyncio.to_thread(_vocab_weak_keyboard, lang),
            )
        elif action == "weak" and len(parts) == 4:
            value, changed = await asyncio.to_thread(_vocab_mark_weak, lang, int(parts[3]))
            if changed:
                await query.message.reply_text(f"⚠️ 취약 단어로 표시했습니다: {value}")
            else:
                await query.message.reply_text("⚠️ 항목을 찾지 못했습니다.")
    elif data == "info:stats":
        msg = await asyncio.to_thread(_get_stats)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=_menu_inline())
    elif data == "info:cost":
        msg = await asyncio.to_thread(_get_cost_summary)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=_menu_inline())

# -------------------------------------------------------------------
# 스케줄러 및 앱 초기화
# -------------------------------------------------------------------
async def daily_run(lang: str, app: Application):
    log.info("일정 발송: %s", lang)
    await asyncio.to_thread(_run, lang)

async def daily_run_all(app: Application):
    log.info("일정 발송: 전체 언어")
    await asyncio.to_thread(_run_all)

async def daily_run_supplements(app: Application):
    log.info("일정 발송: 부가 학습 시리즈")
    await asyncio.to_thread(_run_supplements)

async def daily_run_english(app: Application):
    log.info("일정 발송: 영어 플루언시 시리즈")
    await asyncio.to_thread(_run_english_daily)

async def daily_run_asian_dialogues(app: Application):
    log.info("일정 발송: 일본어/중국어 회화 시리즈")
    await asyncio.to_thread(_run_asian_dialogues)

async def post_init(app: Application):
    if not SCHEDULER_ENABLED:
        log.info("스케줄러 비활성화 — VOCAB_MANAGER_DISABLE_SCHEDULER=1")
        return
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(daily_run_all, "cron", hour=5, minute=0, args=[app], id="vocab_all")
    scheduler.add_job(daily_run_supplements, "cron", hour=5, minute=10, args=[app], id="vocab_supplements")
    scheduler.add_job(daily_run_english, "cron", hour=6, minute=0, args=[app], id="english_fluency")
    scheduler.add_job(daily_run_asian_dialogues, "cron", hour=6, minute=20, args=[app], id="asian_dialogues")
    scheduler.start()
    log.info("스케줄러 시작 — 05:00 ES/JA/ZH 카드, 05:10 부가 학습 시리즈, 06:00 영어 플루언시, 06:20 JA/ZH 회화")

def main():
    if not TOKEN:
        print("❌ VOCAB_BOT_TOKEN 환경 변수가 없습니다.")
        return
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",  cmd_manage))
    app.add_handler(CommandHandler("manage", cmd_manage))
    app.add_handler(CommandHandler("writing_feedback", cmd_writing_feedback))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # 텍스트 메뉴 핸들러 추가
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))
    
    print("🚀 Vocab Manager Bot Started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
