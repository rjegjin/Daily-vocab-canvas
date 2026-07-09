"""
English roleplay speaking session with TTS and STT.
"""
import difflib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from card_engine import check_budget_exit, generate_tts, log_provider_cost
from english_core import (
    TODAY,
    ENGLISH_STATE_FILE,
    LEARNED_EN_PHRASE_FILE,
    SPEAKING_SESSIONS_FILE,
    SPEAKING_SUBMISSIONS_FILE,
    add_history,
    generate_english_tts_voice,
    generate_json_openai,
    get_state,
    mark_weak,
    merge_learned,
    read_json,
    send_message,
    write_json,
)
from english_dialogue import generate_dialogue

PROJECT_DIR = Path(__file__).resolve().parent
VOICE_ASSISTANT = os.getenv("EN_SPEAKING_VOICE", "en-US-Neural2-D")


def _transcribe_audio(audio_path: str, duration_sec: float) -> tuple:
    """
    Transcribe audio file and log cost.
    Returns: (user_text: str, error_message: str or None)
      - If successful: (text, None)
      - If failed: ("", error_message)
    """
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
        return user_text, None
    except Exception as e:
        return "", f"❌ 음성 변환 실패: {e}"


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, remove punctuation, normalize whitespace."""
    text = text.lower()
    # Remove punctuation
    text = re.sub(r"[.,!?;:'\"-]", "", text)
    # Normalize whitespace
    text = " ".join(text.split())
    return text


def _get_diff_report(model_text: str, learner_text: str) -> dict:
    """
    Compute word-level diff and return report with 3 categories:
    - missing_words: words in model but not in learner
    - misread_words: words in learner but not in model
    - word_order: words present but in different order (same set, different sequence)

    Returns: dict with keys: missing_words, misread_words, word_order, status_message
    """
    model_norm = _normalize_text(model_text)
    learner_norm = _normalize_text(learner_text)

    model_words = model_norm.split()
    learner_words = learner_norm.split()

    # Check overall word sets
    model_set = set(model_words)
    learner_set = set(learner_words)

    missing_words = []
    misread_words = []
    word_order = []

    # ponytail: simple heuristic — if sets match but sequence differs, it's word order
    if model_set == learner_set and model_words != learner_words:
        word_order = list(model_set)
    else:
        # Use SequenceMatcher for detailed diff
        matcher = difflib.SequenceMatcher(None, model_words, learner_words)
        opcodes = matcher.get_opcodes()

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "delete":
                missing_words.extend(model_words[i1:i2])
            elif tag == "insert":
                misread_words.extend(learner_words[j1:j2])
            elif tag == "replace":
                model_seq = set(model_words[i1:i2])
                learner_seq = set(learner_words[j1:j2])
                for word in model_seq:
                    if word not in learner_seq:
                        missing_words.append(word)
                for word in learner_seq:
                    if word not in model_seq:
                        misread_words.append(word)

    # Generate message
    parts = []
    if missing_words:
        parts.append(f"누락: {', '.join(missing_words[:5])}")
    if misread_words:
        parts.append(f"오독: {', '.join(misread_words[:5])}")
    if word_order:
        parts.append(f"어순: {', '.join(word_order[:5])}")

    if not parts:
        status = "✅ 완벽합니다!"
    else:
        status = " | ".join(parts)

    return {
        "missing_words": missing_words,
        "misread_words": misread_words,
        "word_order": word_order,
        "status_message": status,
    }


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


def start_shadowing_session():
    """
    Initialize a shadowing (shadowing read) session.
    Load today's dialogue, extract model sentences (role A), and start with first one.
    Returns: (success: bool, message: str)
    """
    if _has_active_session():
        return False, "이미 진행 중인 말하기 세션이 있습니다. 완료 후 다시 시도해주세요."

    check_budget_exit("en")

    state = get_state()
    today = TODAY()

    # Load today's dialogue
    latest_dialogue = state.get("latest_en_dialogue", {})
    dialogue_date = latest_dialogue.get("date")
    item = None

    if dialogue_date == today:
        item = latest_dialogue.get("item")

    if not item:
        return False, "오늘의 회화 데이터가 없습니다. 먼저 '🎬 EN 회화'를 실행해주세요."

    # Extract model dialogue sentences (role A)
    model_dialogue = item.get("model_dialogue", [])
    sentences = [turn.get("text") for turn in model_dialogue if turn.get("role") == "A" and turn.get("text")]

    if not sentences:
        return False, "따라 읽을 모범 문장이 없습니다."

    # Create shadowing session
    shadowing_session = {
        "date": today,
        "mode": "shadowing",
        "scenario_ko": item.get("scenario_ko", ""),
        "target_expressions": item.get("target_expressions", []),
        "sentences": sentences,
        "current_index": 0,
        "turns": [],
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }

    # Send first sentence
    first_sentence = sentences[0]
    send_message(f"🎤 *쉐도잉 시작* 다음 문장을 따라 읽으세요:\n\n\"{first_sentence}\"")

    # Save session state
    state["speaking_session"] = shadowing_session
    write_json(ENGLISH_STATE_FILE, state)

    return True, f"✅ 쉐도잉 세션 시작! 문장을 따라 읽고 음성 메시지를 보내세요."


def handle_voice_message(audio_path: str, duration_sec: float):
    """
    Handle incoming voice message.
    Branches by session mode:
    - roleplay: Transcribe -> Generate response -> TTS
    - shadowing: Transcribe -> Diff against model sentence -> Move to next or end

    Returns: (success: bool, user_text: str, response_audio_path_or_none: str, bot_response: str)
      - success: True if processing succeeded and session continues, False if session ends or error
      - user_text: transcribed user utterance
      - response_audio_path_or_none: path to TTS audio file (roleplay only), or None
      - bot_response: bot's next utterance text (or feedback/error message)
    """
    state = get_state()
    session = state.get("speaking_session")

    if not session:
        return False, "", None, "진행 중인 말하기 세션이 없습니다."

    check_budget_exit("en")

    # Branch by mode
    if session.get("mode") == "shadowing":
        return _handle_shadowing_voice(audio_path, duration_sec)
    else:
        return _handle_roleplay_voice(audio_path, duration_sec)


def _handle_roleplay_voice(audio_path: str, duration_sec: float):
    """Handle roleplay mode voice message."""
    state = get_state()
    session = state.get("speaking_session")

    if not session:
        return False, "", None, "진행 중인 말하기 세션이 없습니다."

    # Transcribe audio
    user_text, error = _transcribe_audio(audio_path, duration_sec)
    if error:
        return False, "", None, error

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


def _handle_shadowing_voice(audio_path: str, duration_sec: float):
    """Handle shadowing mode voice message."""
    state = get_state()
    session = state.get("speaking_session")

    if not session:
        return False, "", None, "진행 중인 말하기 세션이 없습니다."

    # Transcribe audio
    user_text, error = _transcribe_audio(audio_path, duration_sec)
    if error:
        return False, "", None, error

    if not user_text:
        return False, "", None, "음성을 인식하지 못했습니다. 다시 시도해주세요."

    # Get current sentence and perform diff
    current_index = session.get("current_index", 0)
    sentences = session.get("sentences", [])

    if current_index >= len(sentences):
        state.pop("speaking_session", None)
        write_json(ENGLISH_STATE_FILE, state)
        return False, user_text, None, "✅ 모든 문장을 완료했습니다. 세션이 종료되었습니다."

    model_sentence = sentences[current_index]

    # Perform word-level diff
    diff_report = _get_diff_report(model_sentence, user_text)

    # Record turn
    session["turns"].append({
        "sentence_index": current_index,
        "model_text": model_sentence,
        "user_text": user_text,
        "audio_sec": duration_sec,
        "diff_report": diff_report,
    })

    # Move to next sentence
    session["current_index"] = current_index + 1

    # Check if we've reached the last sentence
    if session["current_index"] >= len(sentences):
        # Session complete
        state.pop("speaking_session", None)
        write_json(ENGLISH_STATE_FILE, state)

        # Record to history
        try:
            session_record = {
                "date": session.get("date", TODAY()),
                "mode": "shadowing",
                "scenario_ko": session.get("scenario_ko", ""),
                "turn_count": len(session["turns"]),
                "target_expressions": session.get("target_expressions", []),
                "feedback_sent": False,
            }
            add_history(SPEAKING_SESSIONS_FILE, session_record, limit=250)

            submission_record = {
                "session_date": session.get("date", TODAY()),
                "submitted_at": datetime.now().isoformat(timespec="seconds"),
                "scenario_ko": session.get("scenario_ko", ""),
                "target_expressions": session.get("target_expressions", []),
                "mode": "shadowing",
                "turns": session["turns"],
            }
            add_history(SPEAKING_SUBMISSIONS_FILE, submission_record, limit=250)
        except Exception as e:
            print(f"⚠️ 이력 기록 실패 (계속): {e}")

        feedback_msg = f"✅ {len(session['turns'])}문장을 완료했습니다. 쉐도잉 세션이 종료되었습니다."
        return False, user_text, None, feedback_msg

    else:
        # Continue to next sentence
        next_sentence = sentences[session["current_index"]]
        state["speaking_session"] = session
        write_json(ENGLISH_STATE_FILE, state)

        # Send next sentence for shadowing
        send_message(f"📍 다음 문장을 따라 읽으세요:\n\n\"{next_sentence}\"")

        feedback_msg = diff_report["status_message"]
        return True, user_text, None, feedback_msg


def analyze_session(session: dict):
    """
    Analyze a completed speaking session using LLM.

    Args:
        session: dict with keys: turns, date, scenario_ko, target_expressions

    Returns:
        dict with keys: errors, target_hit, metrics, next_step
        Returns None if analysis fails.
    """
    turns = session.get("turns", [])
    target_expressions = session.get("target_expressions", [])
    scenario_ko = session.get("scenario_ko", "")

    # Calculate metrics
    user_turns = [t for t in turns if t.get("role") == "user"]
    total_audio_sec = sum(t.get("audio_sec", 0) for t in user_turns)
    avg_words_per_turn = 0
    if user_turns:
        total_words = sum(len(t.get("text", "").split()) for t in user_turns)
        avg_words_per_turn = round(total_words / len(user_turns), 1)

    turns_json = json.dumps(turns, ensure_ascii=False, indent=2)

    prompt = f"""
Analyze this English roleplay speaking session.

Scenario (Korean): {scenario_ko}
Target expressions the learner should try: {json.dumps(target_expressions, ensure_ascii=False)}

Conversation turns:
{turns_json}

Please analyze and return JSON with these keys:

1. errors: array of objects with keys:
   - original: what the learner said (exact quote from turns)
   - corrected: grammatically correct version
   - reason_ko: 1-line explanation in Korean

2. target_hit: object with keys:
   - used_well: list of target expressions used correctly
   - missed: list of target expressions NOT used

3. metrics: object with keys:
   - total_audio_sec: total audio duration (seconds)
   - avg_words_per_turn: average words in user turns
   - filler_count: estimated count of fillers like "um", "like", "uh", "you know"

4. next_step: one Korean actionable suggestion for improvement

IMPORTANT: Exclude any items that look like STT errors (gibberish, fragment-only, or completely unrelated to conversation context). Only include clear grammar/expression mistakes that the learner made.

Return raw JSON only. No markdown.
"""

    try:
        analysis = generate_json_openai(
            prompt,
            required_keys={"errors", "target_hit", "metrics", "next_step"},
            expect_list=False,
            lang="en",
        )

        # Ensure numeric metrics
        if isinstance(analysis.get("metrics"), dict):
            analysis["metrics"]["total_audio_sec"] = total_audio_sec
            if "avg_words_per_turn" not in analysis["metrics"]:
                analysis["metrics"]["avg_words_per_turn"] = avg_words_per_turn

        return analysis
    except Exception as e:
        print(f"⚠️ 세션 분석 실패 (계속): {e}")
        return None


def format_speaking_feedback(analysis: dict):
    """
    Format analysis into Telegram feedback message.
    Follows english_writing.py format_feedback style.
    """
    lines = ["📊 *말하기 세션 피드백*", ""]

    # Errors section
    errors = analysis.get("errors", [])
    if errors:
        lines.extend(["✏️ *표현 교정:*"])
        for error in errors[:5]:
            lines.append(f"• \"{error.get('original')}\"")
            lines.append(f"  → \"{error.get('corrected')}\"")
            lines.append(f"  {error.get('reason_ko', '')}")
        lines.append("")
    else:
        lines.extend(["✏️ *표현 교정:* 특별한 오류가 없었습니다.", ""])

    # Target expression usage
    target = analysis.get("target_hit", {})
    used_well = target.get("used_well", [])
    missed = target.get("missed", [])
    lines.append("🎯 *타깃 표현 활용:*")
    if used_well:
        lines.append(f"✅ 잘 쓴 표현: {' / '.join(used_well)}")
    if missed:
        lines.append(f"💡 다음에 써볼 표현: {' / '.join(missed)}")
    if not used_well and not missed:
        lines.append("아직 타깃 표현이 없습니다.")
    lines.append("")

    # Speech metrics
    metrics = analysis.get("metrics", {})
    lines.extend([
        "📈 *발화 지표:*",
        f"• 총 발화 시간: {metrics.get('total_audio_sec', 0):.1f}초",
        f"• 평균 턴당 단어: {metrics.get('avg_words_per_turn', 0):.1f}개",
        f"• 필러 빈도: {metrics.get('filler_count', 0)}회",
        "",
    ])

    # Next step
    lines.append(f"💪 한 단계 더: {analysis.get('next_step', '꾸준히 연습하세요!')}")

    return "\n".join(lines)


def finalize_session():
    """
    End the current speaking session.
    Full pipeline: analyze → format feedback → weak merge → history recording.

    Returns:
        (turns_data, message) tuple
        - turns_data: dict with turns, date, scenario_ko, or None if no session
        - message: status message

    Guarantees:
        - Session state is always removed (even if analysis fails)
        - Transcripts are always preserved to history (even if analysis fails)
    """
    state = get_state()
    session = state.pop("speaking_session", None)
    write_json(ENGLISH_STATE_FILE, state)

    if not session:
        return None, "진행 중인 말하기 세션이 없습니다."

    turns = session.get("turns", [])
    turn_count = len(turns)
    today = TODAY()
    session_date = session.get("date", today)

    # Always preserve transcript to history (even if analysis fails)
    submission_record = {
        "session_date": session_date,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "scenario_ko": session.get("scenario_ko", ""),
        "target_expressions": session.get("target_expressions", []),
        "turns": turns,
    }

    # Analyze session (roleplay only; shadowing uses diff report instead)
    analysis = None
    if session.get("mode") == "roleplay":
        analysis = analyze_session(session)

    # If analysis succeeded, add it to submission record and send feedback
    if analysis:
        submission_record["analysis"] = analysis

        # Send feedback card
        try:
            feedback_message = format_speaking_feedback(analysis)
            send_message(feedback_message)
        except Exception as e:
            print(f"⚠️ 피드백 전송 실패 (계속): {e}")

        # Extract errors and merge to learned phrases with weak marking
        errors = analysis.get("errors", [])
        if errors:
            # Prepare error items for merge_learned
            error_items = []
            for error in errors:
                corrected = error.get("corrected", "").strip()
                if corrected:
                    error_items.append({
                        "phrase": corrected,
                        "category": "speaking_error",
                    })

            # Merge errors (resets weak to False for existing items)
            if error_items:
                try:
                    merge_learned(LEARNED_EN_PHRASE_FILE, error_items, "phrase")
                    # Mark each as weak (ponytail: order matters — merge first resets weak)
                    for error in errors:
                        corrected = error.get("corrected", "").strip()
                        if corrected:
                            mark_weak(LEARNED_EN_PHRASE_FILE, "phrase", corrected)
                except Exception as e:
                    print(f"⚠️ 약한 표현 병합 실패 (계속): {e}")

    # Record to history files
    try:
        # Session metadata
        session_record = {
            "date": session_date,
            "mode": session.get("mode", "roleplay"),
            "scenario_ko": session.get("scenario_ko", ""),
            "turn_count": turn_count,
            "target_expressions": session.get("target_expressions", []),
            "feedback_sent": bool(analysis),
        }
        add_history(SPEAKING_SESSIONS_FILE, session_record, limit=250)

        # Detailed submissions with analysis
        add_history(SPEAKING_SUBMISSIONS_FILE, submission_record, limit=250)
    except Exception as e:
        print(f"⚠️ 이력 기록 실패 (계속): {e}")

    status_suffix = " (분석 완료)" if analysis else " (분석 실패, 전사 기록됨)"
    return (
        {"turns": turns, "date": session_date, "scenario_ko": session.get("scenario_ko")},
        f"✅ 세션 종료! {turn_count}턴 진행했습니다.{status_suffix}",
    )
