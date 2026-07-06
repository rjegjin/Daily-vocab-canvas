"""
English dialogue simulation with TTS.
"""
import os
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from card_engine import check_budget_exit
from english_core import (
    add_dialogue_history,
    generate_english_tts_voice,
    generate_json,
    increment_dialogue_extra_count,
    dialogue_extra_count,
    recent_dialogue_domains,
    send_audio,
    send_message,
    update_state,
)

VOICE_A = os.getenv("EN_DIALOGUE_VOICE_A", "en-US-Neural2-D")
VOICE_B = os.getenv("EN_DIALOGUE_VOICE_B", "en-US-Neural2-F")

SCENARIO_DOMAINS = [
    "workplace",
    "social",
    "service",
    "travel",
    "academic",
    "conflict",
    "negotiation",
    "small_talk",
]

REQUIRED_KEYS = {
    "date",
    "domain",
    "scenario_ko",
    "context_en",
    "target_expressions",
    "model_dialogue",
    "tts_script",
    "cultural_note",
    "korean_trap",
}


def choose_domain(preferred=None):
    if preferred in SCENARIO_DOMAINS:
        return preferred
    recent = set(recent_dialogue_domains(3))
    for domain in SCENARIO_DOMAINS:
        if domain not in recent:
            return domain
    return SCENARIO_DOMAINS[date.today().toordinal() % len(SCENARIO_DOMAINS)]


def generate_dialogue(domain=None, variant=False):
    selected_domain = choose_domain(domain)
    prompt = f"""
Create one fresh English speaking practice scenario as JSON for a Korean learner.
Domain: {selected_domain}
Variant request: {"Make it a similar but different situation from today's previous dialogue." if variant else "Make it a new daily scenario."}

Required keys:
- date: "{date.today().isoformat()}"
- domain
- scenario_ko: Korean description of the situation
- context_en: one English instruction sentence
- target_expressions: exactly 3 natural English expressions
- model_dialogue: 6 turns, list of objects with role A/B and text
- tts_script: dialogue text only, suitable for TTS
- cultural_note: Korean note about pragmatic/cultural usage
- korean_trap: Korean learner mistake and a better expression

Make the dialogue natural, concise, and useful. Return raw JSON only.
"""
    return generate_json(prompt, REQUIRED_KEYS, expect_list=False)


def format_dialogue(item):
    lines = [
        f"🎬 *영어 회화 시뮬레이션* — {item['domain']}",
        "",
        f"*상황:* {item['scenario_ko']}",
        f"`{item['context_en']}`",
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
        f"🌐 *문화 노트:* {item['cultural_note']}",
        f"⚠️ *한국식 함정:* {item['korean_trap']}",
    ])
    return "\n".join(lines)


def dialogue_script_by_role(item, role):
    lines = [
        turn["text"]
        for turn in item.get("model_dialogue", [])
        if turn.get("role") == role and turn.get("text")
    ]
    return "\n".join(lines)


def send_dialogue(domain=None, variant=False):
    check_budget_exit("en")
    item = generate_dialogue(domain=domain, variant=variant)
    update_state(latest_en_dialogue={"date": date.today().isoformat(), "item": item})
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 비슷한 상황 하나 더", callback_data="en:dialogue:more"),
            InlineKeyboardButton("💪 어려웠어", callback_data="en:dialogue:hard"),
            InlineKeyboardButton("✅ 자신 있어", callback_data="en:dialogue:ok"),
        ]
    ]).to_dict()
    send_message(format_dialogue(item), reply_markup=reply_markup)

    tts_sent = False
    for role, voice_name in (("A", VOICE_A), ("B", VOICE_B)):
        role_script = dialogue_script_by_role(item, role)
        if not role_script:
            continue
        audio_path = generate_english_tts_voice(role_script, f"english_dialogue_{role}.mp3", voice_name)
        if audio_path and os.path.exists(audio_path):
            send_audio(audio_path, caption=f"🎧 모범 발화 {role} — 따라 말해보세요")
            tts_sent = True
            os.remove(audio_path)
    add_dialogue_history({
        "date": date.today().isoformat(),
        "domain": item["domain"],
        "scenario_ko": item["scenario_ko"],
        "target_expressions": item["target_expressions"],
        "tts_sent": tts_sent,
    })
    print("✅ 영어 회화 시뮬레이션 발송 완료")


def send_more_dialogue():
    if dialogue_extra_count() >= 3:
        return False
    increment_dialogue_extra_count()
    from english_core import get_state
    latest = get_state().get("latest_en_dialogue", {}).get("item", {})
    send_dialogue(domain=latest.get("domain"), variant=True)
    return True


if __name__ == "__main__":
    send_dialogue()
