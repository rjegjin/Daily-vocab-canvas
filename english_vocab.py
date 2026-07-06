"""
English vocabulary text card.
"""
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from card_engine import check_budget_exit
from english_core import (
    LEARNED_EN_FILE,
    load_learned_words,
    load_weak_items,
    merge_learned,
    send_message,
    update_state,
    generate_json,
)

REQUIRED_KEYS = {"word", "ipa", "pos", "definition_en", "collocation", "example", "category", "register"}


def generate_vocab():
    learned = load_learned_words(LEARNED_EN_FILE, "word")
    weak = load_weak_items(LEARNED_EN_FILE, "word")
    exclude = f"Do not use these recently learned words: {', '.join(learned[-300:])}." if learned else ""
    weak_instruction = f"Include 2-3 of these weak review words if natural: {', '.join(weak[:8])}." if weak else ""
    prompt = f"""
Create a JSON array of exactly 9 English vocabulary items for a Korean learner at B1-C1 range.
Mix concrete and abstract vocabulary. Avoid obscure SAT-only words.
{exclude}
{weak_instruction}

Required keys:
- word
- ipa
- pos
- definition_en: a concise English-English dictionary definition, 8-18 words, no Korean
- collocation: one string containing 1-2 natural collocations separated by " / "
- example: one natural English sentence
- category: emotion, nature, object, action, food, animal, body, concept, place, time
- register: formal, informal, neutral, slang

Return raw JSON only. No markdown.
"""
    return generate_json(prompt, REQUIRED_KEYS)


def format_message(items):
    today = date.today().isoformat()
    lines = [f"📚 *오늘의 영어 단어* — {today}", "", "━━━━━━━━━━━━━━━━━━"]
    for idx, item in enumerate(items, start=1):
        lines.extend([
            f"{idx}. *{item['word']}* {item['ipa']} `{item['pos']}` · {item['register']}",
            f"   Def: {item['definition_en']}",
            f"   연어: _{item['collocation']}_",
            f"   예문: {item['example']}",
            "",
        ])
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def send_vocab():
    check_budget_exit("en")
    items = generate_vocab()
    merge_learned(LEARNED_EN_FILE, items, "word")
    update_state(latest_en_vocab={"date": date.today().isoformat(), "items": items})
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 다 알아", callback_data="en:vocab:ok"),
            InlineKeyboardButton("⚠️ 모르는 거 있어", callback_data="en:vocab:weak_prompt"),
        ]
    ]).to_dict()
    send_message(format_message(items), reply_markup=reply_markup)
    print("✅ 영어 단어 카드 발송 완료")


if __name__ == "__main__":
    send_vocab()
