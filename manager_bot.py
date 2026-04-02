"""
Vocab Card Bot — 자체 관리 봇
VOCAB_BOT_TOKEN으로 상시 실행, 자기 채팅방 직접 관리.
- /start, /manage : 인라인 키보드 (세련된 레이아웃 적용) + 상주 메뉴(ReplyKeyboard)
- /run_es /run_ja /run_zh : 언어별 즉시 실행
- 매일 05:00/06:00/07:00 KST 자동 발송
"""
import asyncio
import logging
import os
import subprocess
import json
from datetime import datetime, date
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
VENV_PY = "/home/rjegj/projects/unified_venv/bin/python"

SCRIPTS = {
    "es": os.path.join(PROJECT_DIR, "main.py"),
    "ja": os.path.join(PROJECT_DIR, "japanese.py"),
    "zh": os.path.join(PROJECT_DIR, "chinese.py"),
    "es_patterns": os.path.join(PROJECT_DIR, "main_patterns.py"),
    "ja_rules": os.path.join(PROJECT_DIR, "japanese_rules.py"),
    "zh_tones": os.path.join(PROJECT_DIR, "chinese_tones.py"),
}
LANG_LABEL = {"es": "🇪🇸 스페인어", "ja": "🇯🇵 일본어", "zh": "🇨🇳 중국어"}

# 로깅 설정
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

IKB = InlineKeyboardButton

# -------------------------------------------------------------------
# 보조 함수
# -------------------------------------------------------------------
def _run(lang: str) -> str:
    if lang not in SCRIPTS:
        return "❌ 알 수 없는 언어입니다."
    subprocess.Popen([VENV_PY, SCRIPTS[lang]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"{LANG_LABEL[lang]} 카드 생성 시작 (백그라운드 진행, 완료 시 전송)"

def _run_all() -> str:
    for lang in SCRIPTS.keys():
        subprocess.Popen([VENV_PY, SCRIPTS[lang]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "🌍 전체 언어(스페인어, 일본어, 중국어) 카드 생성을 백그라운드에서 시작했습니다!"

def _get_stats() -> str:
    stats_msg = "📈 *학습 및 단어장 통계*\n\n"
    files = {"es": "learned_words.txt", "ja": "learned_ja.txt", "zh": "learned_zh.txt"}

    for lang, fname in files.items():
        filepath = os.path.join(PROJECT_DIR, fname)
        count = 0
        recent_words = []
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                count = len(lines)
                recent_words = lines[-5:] # 최근 추가된 단어 5개
        
        stats_msg += f"- {LANG_LABEL.get(lang, lang)}: 총 {count}개 마스터\n"
        if recent_words:
            stats_msg += f"  > 최근 추가: {', '.join(recent_words)}\n"
        stats_msg += "\n"

    # API 비용 확인
    stats_msg += "💰 *오늘의 API 비용*\n"
    cost_path = os.path.join(PROJECT_DIR, 'cost_log.json')
    if os.path.exists(cost_path):
        try:
            with open(cost_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            today = str(date.today())
            if today in log_data and '_daily_total_usd' in log_data[today]:
                stats_msg += f"- 누적 금액: ${log_data[today]['_daily_total_usd']:.4f}\n"
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
        ]
    ])

def _menu_reply() -> ReplyKeyboardMarkup:
    """하단에 항상 상주하는 메뉴 키보드"""
    return ReplyKeyboardMarkup([
        ["🇪🇸 스페인어", "🇯🇵 일본어", "🇨🇳 중국어"],
        ["📝 ES 패턴", "📐 JA 규칙", "🎵 ZH 성조"],
        ["🔄 전체 일괄 생성", "📊 통계 및 비용 조회"]
    ], resize_keyboard=True)

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
    elif text == "🔄 전체 일괄 생성":
        msg = await asyncio.to_thread(_run_all)
        await update.message.reply_text(msg)
    elif text == "📊 통계 및 비용 조회":
        msg = await asyncio.to_thread(_get_stats)
        await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "run:all":
        msg = await asyncio.to_thread(_run_all)
        await query.edit_message_text(f"📚 *Vocab Card Bot*\n\n{msg}", parse_mode="Markdown", reply_markup=_menu_inline())
    elif data.startswith("run:"):
        lang = data.split(":")[-1]
        msg = await asyncio.to_thread(_run, lang)
        await query.edit_message_text(f"📚 *Vocab Card Bot*\n\n{msg}", parse_mode="Markdown", reply_markup=_menu_inline())
    elif data == "info:stats":
        msg = await asyncio.to_thread(_get_stats)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=_menu_inline())

# -------------------------------------------------------------------
# 스케줄러 및 앱 초기화
# -------------------------------------------------------------------
async def daily_run(lang: str, app: Application):
    log.info("일정 발송: %s", lang)
    await asyncio.to_thread(_run, lang)

async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    # 기존 카드 발송
    scheduler.add_job(daily_run, "cron", hour=5, minute=0, args=["es", app], id="vocab_es")
    scheduler.add_job(daily_run, "cron", hour=6, minute=0, args=["ja", app], id="vocab_ja")
    scheduler.add_job(daily_run, "cron", hour=7, minute=0, args=["zh", app], id="vocab_zh")
    # 추가 자료 발송 (5분 뒤)
    scheduler.add_job(daily_run, "cron", hour=5, minute=5, args=["es_patterns", app], id="pattern_es")
    scheduler.add_job(daily_run, "cron", hour=6, minute=5, args=["ja_rules", app], id="rules_ja")
    scheduler.add_job(daily_run, "cron", hour=7, minute=5, args=["zh_tones", app], id="tones_zh")
    scheduler.start()
    log.info("스케줄러 시작 — 05:00 ES / 05:05 Pattern / 06:00 JA / 06:05 Rules / 07:00 ZH / 07:05 Tones")

def main():
    if not TOKEN:
        print("❌ VOCAB_BOT_TOKEN 환경 변수가 없습니다.")
        return
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",  cmd_manage))
    app.add_handler(CommandHandler("manage", cmd_manage))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # 텍스트 메뉴 핸들러 추가
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))
    
    print("🚀 Vocab Manager Bot Started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
