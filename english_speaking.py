"""
English roleplay speaking session with TTS and STT.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

from card_engine import check_budget_exit, generate_tts, log_provider_cost
from english_core import (
    TODAY,
    ENGLISH_STATE_FILE,
    generate_english_tts_voice,
    generate_json_openai,
    get_state,
    read_json,
    send_message,
    write_json,
)
from english_dialogue import generate_dialogue

PROJECT_DIR = Path(__file__).resolve().parent
VOICE_ASSISTANT = os.getenv("EN_SPEAKING_VOICE", "en-US-Neural2-D")


def _has_active_session():
    """Check if a speaking session is already active."""
    state = get_state()
    return "speaking_session" in state and state["speaking_session"]


def start_speaking_session():
    """
    Initialize a speaking session.
    Load today's dialogue or generate a new one.
    Send bot's first utterance.
    Returns: (success: bool, message: str)
    """
    if _has_active_session():
        return False, "이미 진행 중인 말하기 세션이 있습니다. 완료 후 다시 시도해주세요."

    check_budget_exit("en")

    state = get_state()
    today = TODAY()

    # Load today's dialogue or generate new one
    latest_dialogue = state.get("latest_en_dialogue", {})
    dialogue_date = latest_dialogue.get("date")
    item = None

    if dialogue_date == today:
        item = latest_dialogue.get("item")

    if not item:
        item = generate_dialogue()
        state["latest_en_dialogue"] = {"date": today, "item": item}
        write_json(ENGLISH_STATE_FILE, state)

    # Extract scenario info
    scenario_ko = item.get("scenario_ko", "")
    target_expressions = item.get("target_expressions", [])
    context_en = item.get("context_en", "")

    # Create initial session state
    speaking_session = {
        "date": today,
        "mode": "roleplay",
        "scenario_ko": scenario_ko,
        "target_expressions": target_expressions,
        "turns": [],
        "max_turns": 8,
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }

    # Generate bot's first utterance
    prompt = f"""
You are an English conversation partner in a roleplay scenario.
Scenario (Korean): {scenario_ko}
Context: {context_en}

Start the conversation naturally in English. Be friendly and encourage the learner.
Mention the scenario briefly and ask them to respond.

Keep it to 1-2 sentences.
"""
    try:
        bot_utterance = generate_json_openai(
            prompt,
            required_keys=None,
            expect_list=False,
            lang="en",
        )
        if isinstance(bot_utterance, dict):
            bot_utterance = bot_utterance.get("text", str(bot_utterance))
        bot_utterance = str(bot_utterance).strip()
    except Exception as e:
        return False, f"❌ 첫 발화 생성 실패: {e}"

    # Add first turn
    speaking_session["turns"].append({
        "role": "assistant",
        "text": bot_utterance,
    })

    # Save session state
    state["speaking_session"] = speaking_session
    write_json(ENGLISH_STATE_FILE, state)

    # Generate TTS and send
    try:
        audio_path = generate_english_tts_voice(
            bot_utterance,
            "speaking_session_bot.mp3",
            VOICE_ASSISTANT,
        )
        if audio_path and os.path.exists(audio_path):
            from english_core import send_audio
            send_audio(audio_path, caption="🎤 봇 발화 — 답해주세요")
            os.remove(audio_path)
    except Exception as e:
        print(f"⚠️ TTS 발송 실패 (계속): {e}")

    send_message(
        f"🎬 *상황:* {scenario_ko}\n\n"
        f"*봇:* {bot_utterance}\n\n"
        f"💬 음성 메시지로 답해주세요!"
    )

    return True, f"✅ 말하기 세션 시작! 음성 메시지로 답해주세요."


def handle_voice_message(audio_path: str, duration_sec: float):
    """
    Handle incoming voice message.
    Transcribe -> Generate response -> TTS
    Returns: (success: bool, user_text: str, response_audio_path_or_none: str, bot_response: str)
      - success: True if processing succeeded and session continues, False if max_turns reached or error
      - user_text: transcribed user utterance
      - response_audio_path_or_none: path to TTS audio file for bot response, or None if TTS failed
      - bot_response: bot's next utterance text (or error message if success=False)
    """
    state = get_state()
    session = state.get("speaking_session")

    if not session:
        return False, "", None, "진행 중인 말하기 세션이 없습니다."

    check_budget_exit("en")

    # Transcribe audio to text
    try:
        from openai import OpenAI
        client = OpenAI()

        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f,
            )
        user_text = transcript.text or ""

        # Log STT cost
        cost = (duration_sec / 60.0) * 0.003  # ~$0.003 per minute
        log_provider_cost(
            "en",
            "openai_stt",
            cost,
            model="gpt-4o-mini-transcribe",
            audio_sec=duration_sec,
        )
    except Exception as e:
        return False, "", None, f"❌ 음성 변환 실패: {e}"

    if not user_text:
        return False, "", None, "음성을 인식하지 못했습니다. 다시 시도해주세요."

    # Add user turn to history
    session["turns"].append({
        "role": "user",
        "text": user_text,
        "audio_sec": duration_sec,
    })

    # Check if max turns reached
    if len(session["turns"]) >= session["max_turns"]:
        state.pop("speaking_session", None)
        write_json(ENGLISH_STATE_FILE, state)
        return False, user_text, None, "✅ 8턴에 도달했습니다. 세션이 종료되었습니다."

    # Generate next response
    scenario_ko = session.get("scenario_ko", "")
    target_expressions = session.get("target_expressions", [])
    turns_json = json.dumps(session["turns"], ensure_ascii=False, indent=2)

    coaching_policy = f"""
You are an English conversation partner providing coaching feedback.

Scenario: {scenario_ko}
Target expressions the learner should try: {json.dumps(target_expressions, ensure_ascii=False)}

Conversation history:
{turns_json}

The learner just said: "{user_text}"

Your response should:
1. Continue the conversation naturally
2. If the learner hesitates or pauses, provide hints gently
3. Only correct serious errors immediately
4. Encourage natural use of target expressions
5. Keep it to 1-2 sentences

Return a JSON object with only one key "text" containing your next utterance.
"""

    try:
        response_data = generate_json_openai(
            coaching_policy,
            required_keys=None,
            expect_list=False,
            lang="en",
        )
        if isinstance(response_data, dict):
            bot_response = response_data.get("text", str(response_data))
        else:
            bot_response = str(response_data)
        bot_response = bot_response.strip()
    except Exception as e:
        return False, user_text, None, f"❌ 다음 발화 생성 실패: {e}"

    # Add bot turn
    session["turns"].append({
        "role": "assistant",
        "text": bot_response,
    })

    # Save updated session
    state["speaking_session"] = session
    write_json(ENGLISH_STATE_FILE, state)

    # Generate TTS for response
    response_audio_path = None
    try:
        response_audio_path = generate_english_tts_voice(
            bot_response,
            "speaking_session_response.mp3",
            VOICE_ASSISTANT,
        )
    except Exception as e:
        print(f"⚠️ 응답 TTS 실패 (계속): {e}")

    return True, user_text, response_audio_path, bot_response


def finalize_session():
    """
    End the current speaking session.
    Returns turns data for potential extension (P1-b).
    """
    state = get_state()
    session = state.pop("speaking_session", None)
    write_json(ENGLISH_STATE_FILE, state)

    if not session:
        return None, "진행 중인 말하기 세션이 없습니다."

    turns = session.get("turns", [])
    turn_count = len(turns)

    return (
        {"turns": turns, "date": session.get("date"), "scenario_ko": session.get("scenario_ko")},
        f"✅ 세션 종료! {turn_count}턴 진행했습니다.",
    )
