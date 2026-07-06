import asyncio

from telegram import ReplyKeyboardMarkup

from bot_runtime import IKB, InlineKeyboardMarkup, callback_run, cost_summary, language_env, make_scheduler, reply_run, run_polling_bot, run_script, stats_summary

TOKEN_ENVS = ("SPANISH_BOT_TOKEN", "ES_BOT_TOKEN")
CHAT_ENVS = ("SPANISH_CHAT_ID", "ES_CHAT_ID")


def _env():
    return language_env(TOKEN_ENVS, CHAT_ENVS)


def menu_inline():
    return InlineKeyboardMarkup([
        [IKB("스페인어 카드", callback_data="run:es")],
        [IKB("ES 패턴", callback_data="run:es_patterns")],
        [IKB("통계", callback_data="info:stats"), IKB("비용", callback_data="info:cost")],
    ])


def menu_reply():
    return ReplyKeyboardMarkup([
        ["스페인어 카드", "ES 패턴"],
        ["통계", "비용"],
    ], resize_keyboard=True)


async def handle_text(update, context):
    text = update.message.text
    if text == "스페인어 카드":
        await reply_run(update, "es", _env())
    elif text == "ES 패턴":
        await reply_run(update, "es_patterns", _env())
    elif text == "통계":
        await update.message.reply_text(await asyncio.to_thread(stats_summary))
    elif text == "비용":
        await update.message.reply_text(await asyncio.to_thread(cost_summary))


async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "run:es":
        await callback_run(query, "es", _env(), menu_inline)
    elif data == "run:es_patterns":
        await callback_run(query, "es_patterns", _env(), menu_inline)
    elif data == "info:stats":
        await query.edit_message_text(await asyncio.to_thread(stats_summary), reply_markup=menu_inline())
    elif data == "info:cost":
        await query.edit_message_text(await asyncio.to_thread(cost_summary), reply_markup=menu_inline())


async def post_init(app):
    scheduler = make_scheduler("SPANISH_BOT_DISABLE_SCHEDULER")
    if not scheduler:
        return
    scheduler.add_job(lambda: run_script("es", _env()), "cron", hour=5, minute=0, id="spanish_vocab")
    scheduler.add_job(lambda: run_script("es_patterns", _env()), "cron", hour=5, minute=10, id="spanish_patterns")
    scheduler.start()


if __name__ == "__main__":
    run_polling_bot(
        bot_name="Spanish Bot",
        token_envs=TOKEN_ENVS,
        chat_envs=CHAT_ENVS,
        menu_reply=menu_reply,
        menu_inline=menu_inline,
        handle_text=handle_text,
        handle_callback=handle_callback,
        post_init=post_init,
    )
