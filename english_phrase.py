"""
English phrase/collocation text card.
"""
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from card_engine import check_budget_exit
from english_core import (
    LEARNED_EN_PHRASE_FILE,
    generate_json,
    load_learned_words,
    load_weak_items,
    merge_learned,
    send_message,
    update_state,
)

REQUIRED_KEYS = {"phrase", "meaning_ko", "example", "register", "trap", "category"}


def should_send_today():
    return datetime.now().weekday() in (0, 2, 4)


def generate_phrases():
    learned = load_learned_words(LEARNED_EN_PHRASE_FILE, "phrase")
    weak = load_weak_items(LEARNED_EN_PHRASE_FILE, "phrase")
    exclude = f"Do not use these learned phrases: {', '.join(learned[-200:])}." if learned else ""
    weak_instruction = f"Include 1-2 weak review phrases if natural: {', '.join(weak[:6])}." if weak else ""
    prompt = f"""
Create a JSON array of exactly 6 useful English phrases, idioms, or collocations for a Korean learner.
Focus on phrases that improve speaking and writing fluency.
{exclude}
{weak_instruction}

Required keys:
- phrase
- meaning_ko
- example
- register: formal, informal, neutral, slang
- trap: a Korean learner error warning in Korean
- category: emotion, work, academic, social, service, travel, conflict, concept

Return raw JSON only. No markdown.
"""
    return generate_json(prompt, REQUIRED_KEYS)


def format_message(items):
    weekday = ["월", "화", "수", "목", "금", "토", "일"][datetime.now().weekday()]
    lines = [f"💬 *오늘의 영어 표현* ({weekday}요일)", "", "━━━━━━━━━━━━━━━━━━"]
    for item in items:
        lines.extend([
            f"🔹 *{item['phrase']}* · {item['register']}",
            f"   뜻: {item['meaning_ko']}",
            f"   예: {item['example']}",
            f"   ⚠️ 주의: {item['trap']}",
            "",
        ])
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def send_phrase(force=False):
    if not force and not should_send_today():
        print("⏭️ 영어 표현 카드는 월/수/금만 발송합니다.")
        return
    check_budget_exit("en")
    items = generate_phrases()
    merge_learned(LEARNED_EN_PHRASE_FILE, items, "phrase")
    update_state(latest_en_phrase={"date": date.today().isoformat(), "items": items})
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 알겠어", callback_data="en:phrase:ok"),
            InlineKeyboardButton("⚠️ 헷갈려", callback_data="en:phrase:weak_prompt"),
        ]
    ]).to_dict()
    send_message(format_message(items), reply_markup=reply_markup)
    print("✅ 영어 표현 카드 발송 완료")


if __name__ == "__main__":
    send_phrase()
