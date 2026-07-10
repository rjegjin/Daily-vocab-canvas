import asyncio
import os
from datetime import datetime
from pathlib import Path

from telegram import ReplyKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters

from bot_runtime import (
    IKB,
    InlineKeyboardMarkup,
    callback_run,
    cost_summary,
    english_daily_jobs,
    english_mark_weak,
    english_weak_keyboard,
    is_writing_pending,
    language_env,
    looks_like_english,
    make_scheduler,
    reply_run,
    run_many,
    run_polling_bot,
    run_script,
    send_more_english_dialogue,
    send_writing_feedback,
    stats_summary,
)
from english_speaking import start_speaking_session, start_shadowing_session, handle_voice_message, finalize_session

PROJECT_DIR = Path(__file__).resolve().parent

TOKEN_ENVS = ("ENGLISH_BOT_TOKEN", "EN_BOT_TOKEN")
CHAT_ENVS = ("ENGLISH_CHAT_ID", "EN_CHAT_ID")


def _env():
    return language_env(TOKEN_ENVS, CHAT_ENVS)


def menu_inline():
    return InlineKeyboardMarkup([
        [IKB("EN 단어", callback_data="run:en_vocab"), IKB("EN 표현", callback_data="run:en_phrase")],
        [IKB("EN 회화", callback_data="run:en_dialogue"), IKB("EN 글쓰기", callback_data="run:en_writing")],
        [IKB("EN 오늘 전체", callback_data="run:english_daily")],
        [IKB("🎙️ EN 말하기", callback_data="en:speaking:start"), IKB("🗣️ 따라 읽기", callback_data="en:speaking:shadow")],
        [IKB("⏹ 세션 종료", callback_data="en:speaking:end")],
        [IKB("통계", callback_data="info:stats"), IKB("비용", callback_data="info:cost")],
    ])


def menu_reply():
    return ReplyKeyboardMarkup([
        ["EN 단어", "EN 표현", "EN 회화"],
        ["EN 글쓰기", "EN 오늘 전체"],
        ["🎙️ EN 말하기", "🗣️ 따라 읽기", "⏹ 세션 종료"],
        ["통계", "비용"],
    ], resize_keyboard=True)


async def run_english_daily(update):
    msg = await asyncio.to_thread(run_many, english_daily_jobs(), _env())
    await update.message.reply_text("영어 플루언시 실행 시작\n\n" + msg)


async def handle_text(update, context):
    text = update.message.text
    if text == "EN 단어":
        await reply_run(update, "en_vocab", _env())
    elif text == "EN 표현":
        await reply_run(update, "en_phrase", _env())
    elif text == "EN 회화":
        await reply_run(update, "en_dialogue", _env())
    elif text == "EN 글쓰기":
        await reply_run(update, "en_writing", _env())
    elif text == "EN 오늘 전체":
        await run_english_daily(update)
    elif text == "통계":
        await update.message.reply_text(await asyncio.to_thread(stats_summary))
    elif text == "비용":
        await update.message.reply_text(await asyncio.to_thread(cost_summary))
    elif await asyncio.to_thread(is_writing_pending) and len(text.split()) >= 40 and looks_like_english(text):
        await update.message.reply_text("글쓰기 피드백을 생성 중입니다. 완료되면 별도 메시지로 전송됩니다.")
        await asyncio.to_thread(send_writing_feedback, text)


async def cmd_writing_feedback(update, context):
    if update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
    else:
        text = " ".join(context.args)
    if len(text.split()) < 20:
        await update.message.reply_text("피드백할 영어 글을 명령 뒤에 붙이거나, 글 메시지에 답장으로 /writing_feedback 을 보내세요.")
        return
    await update.message.reply_text("글쓰기 피드백을 생성 중입니다. 완료되면 별도 메시지로 전송됩니다.")
    await asyncio.to_thread(send_writing_feedback, text)


async def handle_voice(update, context):
    """Handle voice messages for speaking sessions."""
    voice = update.message.voice
    if not voice:
        return
    duration_sec = voice.duration or 0
    file_path = None
    try:
        # Download voice with retry logic (1 retry)
        file_path = os.path.join(str(PROJECT_DIR), f"voice_{int(datetime.now().timestamp())}.ogg")
        try:
            file = await voice.get_file()
            await file.download_to_drive(file_path)
        except Exception:
            # Retry once
            try:
                file = await voice.get_file()
                await file.download_to_drive(file_path)
            except Exception:
                await update.message.reply_text("❌ 음성 다운로드 실패. 텍스트로 답장해 주세요.")
                return

        success, user_text, audio_path_response, message = await asyncio.to_thread(
            handle_voice_message, file_path, duration_sec
        )

        if success:
            await update.message.reply_text(f"👤 당신: {user_text}\n\n🤖 봇: {message}")
            if audio_path_response and os.path.exists(audio_path_response):
                await update.message.reply_voice(voice=open(audio_path_response, 'rb'), caption="🎤 봇 응답")
                os.remove(audio_path_response)
        else:
            await update.message.reply_text(message)

        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        await update.message.reply_text(f"❌ 음성 처리 실패: {e}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "run:english_daily":
        msg = await asyncio.to_thread(run_many, english_daily_jobs(), _env())
        await query.edit_message_text("영어 플루언시 실행 시작\n\n" + msg, reply_markup=menu_inline())
    elif data.startswith("run:"):
        await callback_run(query, data.split(":")[-1], _env(), menu_inline)
    elif data.startswith("en:"):
        parts = data.split(":")
        kind = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        if kind in ("vocab", "phrase") and action == "ok":
            await query.message.reply_text("기록했습니다.")
        elif kind in ("vocab", "phrase") and action == "weak_prompt":
            label = "단어" if kind == "vocab" else "표현"
            await query.message.reply_text(f"헷갈리는 {label}를 선택하세요:", reply_markup=await asyncio.to_thread(english_weak_keyboard, kind))
        elif kind in ("vocab", "phrase") and action == "weak" and len(parts) == 4:
            value, changed = await asyncio.to_thread(english_mark_weak, kind, int(parts[3]))
            await query.message.reply_text(f"취약 항목으로 표시했습니다: {value}" if changed else "항목을 찾지 못했습니다.")
        elif kind == "dialogue" and action == "more":
            ok = await asyncio.to_thread(send_more_english_dialogue)
            await query.message.reply_text("비슷한 상황을 추가 생성했습니다." if ok else "오늘은 더 이상 생성할 수 없어요. 3회 제한입니다.")
        elif kind == "dialogue" and action == "hard":
            await query.message.reply_text("어려움으로 기록했습니다.")
        elif kind == "dialogue" and action == "ok":
            await query.message.reply_text("자신 있음으로 기록했습니다.")
        elif kind == "speaking" and action == "start":
            success, bot_utterance, audio_path, guide_message = await asyncio.to_thread(start_speaking_session)
            if success:
                await query.message.reply_text(guide_message, parse_mode="Markdown")
                if audio_path and os.path.exists(audio_path):
                    await query.message.reply_voice(voice=open(audio_path, 'rb'), caption="🎤 봇 발화 — 답해주세요")
                    os.remove(audio_path)
                await query.message.reply_text(f"🤖 봇: {bot_utterance}")
            else:
                await query.message.reply_text(guide_message)
        elif kind == "speaking" and action == "shadow":
            success, guide_message = await asyncio.to_thread(start_shadowing_session)
            await query.message.reply_text(guide_message)
        elif kind == "speaking" and action == "end":
            feedback_message = await asyncio.to_thread(finalize_session)
            # finalize_session returns (turns_data, feedback_message)
            _, feedback_text = feedback_message if isinstance(feedback_message, tuple) else (None, feedback_message)
            await query.message.reply_text(feedback_text, parse_mode="Markdown")
    elif data == "info:stats":
        await query.edit_message_text(await asyncio.to_thread(stats_summary), reply_markup=menu_inline())
    elif data == "info:cost":
        await query.edit_message_text(await asyncio.to_thread(cost_summary), reply_markup=menu_inline())


async def post_init(app):
    scheduler = make_scheduler("ENGLISH_BOT_DISABLE_SCHEDULER")
    if not scheduler:
        return
    scheduler.add_job(lambda: run_many(english_daily_jobs(), _env()), "cron", hour=6, minute=0, id="english_daily")
    scheduler.start()


if __name__ == "__main__":
    run_polling_bot(
        bot_name="Vocab EN Bot",
        token_envs=TOKEN_ENVS,
        chat_envs=CHAT_ENVS,
        menu_reply=menu_reply,
        menu_inline=menu_inline,
        handle_text=handle_text,
        handle_callback=handle_callback,
        post_init=post_init,
        extra_handlers=[
            CommandHandler("writing_feedback", cmd_writing_feedback),
            MessageHandler(filters.VOICE, handle_voice),
        ],
    )
