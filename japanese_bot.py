import asyncio

from telegram import ReplyKeyboardMarkup

from bot_runtime import (
    IKB,
    InlineKeyboardMarkup,
    callback_run,
    cost_summary,
    language_env,
    make_scheduler,
    reply_run,
    run_polling_bot,
    run_script,
    send_more_lang_dialogue,
    stats_summary,
    supplement_keyboard,
    supplement_mark_weak,
    vocab_mark_weak,
    vocab_weak_keyboard,
)

TOKEN_ENVS = ("JAPANESE_BOT_TOKEN", "JA_BOT_TOKEN")
CHAT_ENVS = ("JAPANESE_CHAT_ID", "JA_CHAT_ID")


def _env():
    return language_env(TOKEN_ENVS, CHAT_ENVS)


def menu_inline():
    return InlineKeyboardMarkup([
        [IKB("일본어 카드", callback_data="run:ja")],
        [IKB("JA 규칙", callback_data="run:ja_rules"), IKB("JA 회화", callback_data="run:ja_dialogue")],
        [IKB("통계", callback_data="info:stats"), IKB("비용", callback_data="info:cost")],
    ])


def menu_reply():
    return ReplyKeyboardMarkup([
        ["일본어 카드", "JA 규칙", "JA 회화"],
        ["통계", "비용"],
    ], resize_keyboard=True)


async def handle_text(update, context):
    text = update.message.text
    if text == "일본어 카드":
        await reply_run(update, "ja", _env())
    elif text == "JA 규칙":
        await reply_run(update, "ja_rules", _env())
    elif text == "JA 회화":
        await reply_run(update, "ja_dialogue", _env())
    elif text == "통계":
        await update.message.reply_text(await asyncio.to_thread(stats_summary))
    elif text == "비용":
        await update.message.reply_text(await asyncio.to_thread(cost_summary))


async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("run:"):
        await callback_run(query, data.split(":")[-1], _env(), menu_inline)
    elif data.startswith("ja:vocab:"):
        parts = data.split(":")
        action = parts[2] if len(parts) > 2 else ""
        if action == "ok":
            await query.message.reply_text("일본어 단어 카드 기록했습니다.")
        elif action == "weak_prompt":
            await query.message.reply_text("헷갈리는 일본어 단어를 선택하세요:", reply_markup=await asyncio.to_thread(vocab_weak_keyboard, "ja"))
        elif action == "weak" and len(parts) == 4:
            value, changed = await asyncio.to_thread(vocab_mark_weak, "ja", int(parts[3]))
            await query.message.reply_text(f"취약 단어로 표시했습니다: {value}" if changed else "항목을 찾지 못했습니다.")
    elif data.startswith("ja_rules:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "ok":
            await query.message.reply_text("일본어 규칙 이해로 기록했습니다.")
        elif action == "weak_prompt":
            await query.message.reply_text("헷갈리는 일본어 규칙을 선택하세요:", reply_markup=await asyncio.to_thread(supplement_keyboard, "ja_rules"))
        elif action == "weak" and len(parts) == 3:
            value, changed = await asyncio.to_thread(supplement_mark_weak, "ja_rules", int(parts[2]))
            await query.message.reply_text(f"취약 항목으로 표시했습니다: {value}" if changed else "항목을 찾지 못했습니다.")
    elif data.startswith("ja:dialogue:"):
        action = data.split(":")[2]
        if action == "more":
            ok = await asyncio.to_thread(send_more_lang_dialogue, "ja")
            await query.message.reply_text("비슷한 상황을 추가 생성했습니다." if ok else "오늘은 더 이상 생성할 수 없어요. 3회 제한입니다.")
        elif action == "hard":
            await query.message.reply_text("일본어 회화 어려움으로 기록했습니다.")
        elif action == "ok":
            await query.message.reply_text("일본어 회화 자신 있음으로 기록했습니다.")
    elif data == "info:stats":
        await query.edit_message_text(await asyncio.to_thread(stats_summary), reply_markup=menu_inline())
    elif data == "info:cost":
        await query.edit_message_text(await asyncio.to_thread(cost_summary), reply_markup=menu_inline())


async def post_init(app):
    scheduler = make_scheduler("JAPANESE_BOT_DISABLE_SCHEDULER")
    if not scheduler:
        return
    scheduler.add_job(lambda: run_script("ja", _env()), "cron", hour=5, minute=0, id="japanese_vocab")
    scheduler.add_job(lambda: run_script("ja_rules", _env()), "cron", hour=5, minute=10, id="japanese_rules")
    scheduler.add_job(lambda: run_script("ja_dialogue", _env()), "cron", hour=6, minute=20, id="japanese_dialogue")
    scheduler.start()


if __name__ == "__main__":
    run_polling_bot(
        bot_name="Japanese Bot",
        token_envs=TOKEN_ENVS,
        chat_envs=CHAT_ENVS,
        menu_reply=menu_reply,
        menu_inline=menu_inline,
        handle_text=handle_text,
        handle_callback=handle_callback,
        post_init=post_init,
    )
