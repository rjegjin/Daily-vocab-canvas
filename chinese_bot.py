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

TOKEN_ENVS = ("CHINESE_BOT_TOKEN", "ZH_BOT_TOKEN")
CHAT_ENVS = ("CHINESE_CHAT_ID", "ZH_CHAT_ID")


def _env():
    return language_env(TOKEN_ENVS, CHAT_ENVS)


def menu_inline():
    return InlineKeyboardMarkup([
        [IKB("중국어 카드", callback_data="run:zh")],
        [IKB("ZH 성조", callback_data="run:zh_tones"), IKB("ZH 회화", callback_data="run:zh_dialogue")],
        [IKB("통계", callback_data="info:stats"), IKB("비용", callback_data="info:cost")],
    ])


def menu_reply():
    return ReplyKeyboardMarkup([
        ["중국어 카드", "ZH 성조", "ZH 회화"],
        ["통계", "비용"],
    ], resize_keyboard=True)


async def handle_text(update, context):
    text = update.message.text
    if text == "중국어 카드":
        await reply_run(update, "zh", _env())
    elif text == "ZH 성조":
        await reply_run(update, "zh_tones", _env())
    elif text == "ZH 회화":
        await reply_run(update, "zh_dialogue", _env())
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
    elif data.startswith("zh:vocab:"):
        parts = data.split(":")
        action = parts[2] if len(parts) > 2 else ""
        if action == "ok":
            await query.message.reply_text("중국어 단어 카드 기록했습니다.")
        elif action == "weak_prompt":
            await query.message.reply_text("헷갈리는 중국어 단어를 선택하세요:", reply_markup=await asyncio.to_thread(vocab_weak_keyboard, "zh"))
        elif action == "weak" and len(parts) == 4:
            value, changed = await asyncio.to_thread(vocab_mark_weak, "zh", int(parts[3]))
            await query.message.reply_text(f"취약 단어로 표시했습니다: {value}" if changed else "항목을 찾지 못했습니다.")
    elif data.startswith("zh_tones:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "ok":
            await query.message.reply_text("중국어 성조 이해로 기록했습니다.")
        elif action == "weak_prompt":
            await query.message.reply_text("헷갈리는 중국어 성조 항목을 선택하세요:", reply_markup=await asyncio.to_thread(supplement_keyboard, "zh_tones"))
        elif action == "weak" and len(parts) == 3:
            value, changed = await asyncio.to_thread(supplement_mark_weak, "zh_tones", int(parts[2]))
            await query.message.reply_text(f"취약 항목으로 표시했습니다: {value}" if changed else "항목을 찾지 못했습니다.")
    elif data.startswith("zh:dialogue:"):
        action = data.split(":")[2]
        if action == "more":
            ok = await asyncio.to_thread(send_more_lang_dialogue, "zh")
            await query.message.reply_text("비슷한 상황을 추가 생성했습니다." if ok else "오늘은 더 이상 생성할 수 없어요. 3회 제한입니다.")
        elif action == "hard":
            await query.message.reply_text("중국어 회화 어려움으로 기록했습니다.")
        elif action == "ok":
            await query.message.reply_text("중국어 회화 자신 있음으로 기록했습니다.")
    elif data == "info:stats":
        await query.edit_message_text(await asyncio.to_thread(stats_summary), reply_markup=menu_inline())
    elif data == "info:cost":
        await query.edit_message_text(await asyncio.to_thread(cost_summary), reply_markup=menu_inline())


async def post_init(app):
    scheduler = make_scheduler("CHINESE_BOT_DISABLE_SCHEDULER")
    if not scheduler:
        return
    scheduler.add_job(lambda: run_script("zh", _env()), "cron", hour=5, minute=0, id="chinese_vocab")
    scheduler.add_job(lambda: run_script("zh_tones", _env()), "cron", hour=5, minute=10, id="chinese_tones")
    scheduler.add_job(lambda: run_script("zh_dialogue", _env()), "cron", hour=6, minute=20, id="chinese_dialogue")
    scheduler.start()


if __name__ == "__main__":
    run_polling_bot(
        bot_name="Chinese Bot",
        token_envs=TOKEN_ENVS,
        chat_envs=CHAT_ENVS,
        menu_reply=menu_reply,
        menu_inline=menu_inline,
        handle_text=handle_text,
        handle_callback=handle_callback,
        post_init=post_init,
    )
