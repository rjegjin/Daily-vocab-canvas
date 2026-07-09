"""
Chinese dialogue simulation with complement-pattern focus and TTS.
"""
import os
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from card_engine import check_budget_exit
from english_core import (
    ZH_DIALOGUE_HISTORY_FILE,
    add_history,
    generate_json,
    generate_lang_tts,
    recent_history_values,
    send_audio,
    send_message,
    update_state,
)

DOMAINS = ["workplace", "service", "social", "travel", "shopping", "request", "problem_solving", "small_talk"]
COMPLEMENT_FOCUS = ["结果补语", "方向补语", "程度补语", "可能补语"]

REQUIRED_KEYS = {
    "date",
    "domain",
    "formality",
    "complement_focus",
    "scenario_ko",
    "context_zh",
    "target_patterns",
    "model_dialogue",
    "tts_script",
    "grammar_note",
    "korean_trap",
}


def choose_domain():
    recent = set(recent_history_values(ZH_DIALOGUE_HISTORY_FILE, "domain", 3))
    for domain in DOMAINS:
        if domain not in recent:
            return domain
    return DOMAINS[date.today().toordinal() % len(DOMAINS)]


def choose_complement():
    return COMPLEMENT_FOCUS[date.today().toordinal() % len(COMPLEMENT_FOCUS)]


def generate_dialogue(domain=None, complement_focus=None):
    selected_domain = domain or choose_domain()
    selected_complement = complement_focus or choose_complement()
    prompt = f"""
Create one Mandarin Chinese speaking practice scenario as JSON for a Korean learner.
Domain: {selected_domain}
Complement focus: {selected_complement}
Date: {date.today().isoformat()}

Required keys:
- date
- domain
- formality: casual, neutral, polite
- complement_focus: one Chinese complement type such as 结果补语, 方向补语, 程度补语, 可能补语
- scenario_ko: Korean situation description
- context_zh: one short Chinese instruction sentence
- target_patterns: exactly 3 useful Chinese expressions or grammar patterns
- model_dialogue: 6 turns, list of objects with role A/B and text
- tts_script: Chinese dialogue text only, suitable for TTS
- grammar_note: Korean explanation of word order/complement use
- korean_trap: Korean learner mistake and a natural correction

Use Simplified Chinese with pinyin only when helpful. Return raw JSON only.
"""
    return generate_json(prompt, REQUIRED_KEYS, expect_list=False, lang="zh")


def format_dialogue(item):
    lines = [
        f"🎬 *중국어 회화 시뮬레이션* — {item['domain']} · {item['complement_focus']}",
        "",
        f"*상황:* {item['scenario_ko']}",
        f"`{item['context_zh']}`",
        "",
        "💬 *모범 대화*",
    ]
    for turn in item["model_dialogue"]:
        lines.append(f"*{turn['role']}:* {turn['text']}")
    lines.extend(["", "🔑 *핵심 패턴*"])
    for pattern in item["target_patterns"]:
        lines.append(f"• `{pattern}`")
    lines.extend([
        "",
        f"📐 *문법 노트:* {item['grammar_note']}",
        f"⚠️ *한국식 함정:* {item['korean_trap']}",
    ])
    return "\n".join(lines)


def send_dialogue(domain=None, complement_focus=None):
    check_budget_exit("zh")
    item = generate_dialogue(domain=domain, complement_focus=complement_focus)
    update_state(latest_zh_dialogue={"date": date.today().isoformat(), "item": item})
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 비슷한 상황", callback_data="zh:dialogue:more"),
            InlineKeyboardButton("💪 어려웠어", callback_data="zh:dialogue:hard"),
            InlineKeyboardButton("✅ 자신 있어", callback_data="zh:dialogue:ok"),
        ]
    ]).to_dict()
    send_message(format_dialogue(item), reply_markup=reply_markup)

    audio_path = generate_lang_tts(item["tts_script"], "cmn-CN", "chinese_dialogue.mp3", "zh")
    tts_sent = False
    if audio_path and os.path.exists(audio_path):
        send_audio(audio_path, caption="🎧 중국어 모범 발화 — 성조와 어순을 따라 말해보세요")
        tts_sent = True
        os.remove(audio_path)
    add_history(ZH_DIALOGUE_HISTORY_FILE, {
        "date": date.today().isoformat(),
        "domain": item["domain"],
        "complement_focus": item["complement_focus"],
        "scenario_ko": item["scenario_ko"],
        "target_patterns": item["target_patterns"],
        "tts_sent": tts_sent,
    })
    print("✅ 중국어 회화 시뮬레이션 발송 완료")


def send_more_dialogue():
    from english_core import get_state
    latest = get_state().get("latest_zh_dialogue", {}).get("item", {})
    send_dialogue(domain=latest.get("domain"), complement_focus=latest.get("complement_focus"))
    return True


if __name__ == "__main__":
    send_dialogue()
