"""
Japanese dialogue simulation with keigo awareness and TTS.
"""
import os
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from card_engine import check_budget_exit
from english_core import (
    JA_DIALOGUE_HISTORY_FILE,
    add_history,
    generate_json,
    generate_lang_tts,
    recent_history_values,
    send_audio,
    send_message,
    update_state,
)

DOMAINS = ["workplace", "service", "social", "travel", "request", "apology", "shopping", "small_talk"]
KEIGO_LEVELS = ["普通体", "丁寧語", "敬語"]

REQUIRED_KEYS = {
    "date",
    "domain",
    "keigo_level",
    "scenario_ko",
    "context_ja",
    "target_expressions",
    "model_dialogue",
    "tts_script",
    "keigo_note",
    "korean_trap",
}


def choose_domain():
    recent = set(recent_history_values(JA_DIALOGUE_HISTORY_FILE, "domain", 3))
    for domain in DOMAINS:
        if domain not in recent:
            return domain
    return DOMAINS[date.today().toordinal() % len(DOMAINS)]


def choose_keigo_level(domain):
    if domain in {"workplace", "service", "request", "apology"}:
        return "敬語" if date.today().weekday() in (1, 4) else "丁寧語"
    return KEIGO_LEVELS[date.today().toordinal() % len(KEIGO_LEVELS)]


def generate_dialogue(domain=None, keigo_level=None):
    selected_domain = domain or choose_domain()
    selected_keigo = keigo_level or choose_keigo_level(selected_domain)
    prompt = f"""
Create one Japanese speaking practice scenario as JSON for a Korean learner.
Domain: {selected_domain}
Keigo level: {selected_keigo}
Date: {date.today().isoformat()}

Required keys:
- date
- domain
- keigo_level: one of 普通体, 丁寧語, 敬語
- scenario_ko: Korean situation description
- context_ja: one short Japanese instruction sentence
- target_expressions: exactly 3 useful Japanese expressions
- model_dialogue: 6 turns, list of objects with role A/B and text
- tts_script: Japanese dialogue text only, suitable for TTS
- keigo_note: Korean explanation of politeness/register
- korean_trap: Korean learner mistake and a natural correction

Keep it practical and concise. Return raw JSON only.
"""
    return generate_json(prompt, REQUIRED_KEYS, expect_list=False, lang="ja")


def format_dialogue(item):
    lines = [
        f"🎬 *일본어 회화 시뮬레이션* — {item['domain']} · {item['keigo_level']}",
        "",
        f"*상황:* {item['scenario_ko']}",
        f"`{item['context_ja']}`",
        "",
        "💬 *모범 대화*",
    ]
    for turn in item["model_dialogue"]:
        lines.append(f"*{turn['role']}:* {turn['text']}")
    lines.extend(["", "🔑 *핵심 표현*"])
    for expression in item["target_expressions"]:
        lines.append(f"• `{expression}`")
    lines.extend([
        "",
        f"🎩 *경어 노트:* {item['keigo_note']}",
        f"⚠️ *한국식 함정:* {item['korean_trap']}",
    ])
    return "\n".join(lines)


def send_dialogue(domain=None, keigo_level=None):
    check_budget_exit("ja")
    item = generate_dialogue(domain=domain, keigo_level=keigo_level)
    update_state(latest_ja_dialogue={"date": date.today().isoformat(), "item": item})
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 비슷한 상황", callback_data="ja:dialogue:more"),
            InlineKeyboardButton("💪 어려웠어", callback_data="ja:dialogue:hard"),
            InlineKeyboardButton("✅ 자신 있어", callback_data="ja:dialogue:ok"),
        ]
    ]).to_dict()
    send_message(format_dialogue(item), reply_markup=reply_markup)

    audio_path = generate_lang_tts(item["tts_script"], "ja-JP", "japanese_dialogue.mp3", "ja")
    tts_sent = False
    if audio_path and os.path.exists(audio_path):
        send_audio(audio_path, caption="🎧 일본어 모범 발화 — 따라 말해보세요")
        tts_sent = True
        os.remove(audio_path)
    add_history(JA_DIALOGUE_HISTORY_FILE, {
        "date": date.today().isoformat(),
        "domain": item["domain"],
        "keigo_level": item["keigo_level"],
        "scenario_ko": item["scenario_ko"],
        "target_expressions": item["target_expressions"],
        "tts_sent": tts_sent,
    })
    print("✅ 일본어 회화 시뮬레이션 발송 완료")


def send_more_dialogue():
    from english_core import get_state
    latest = get_state().get("latest_ja_dialogue", {}).get("item", {})
    send_dialogue(domain=latest.get("domain"), keigo_level=latest.get("keigo_level"))
    return True


if __name__ == "__main__":
    send_dialogue()
