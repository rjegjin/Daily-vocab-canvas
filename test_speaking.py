"""
Minimal tests for english_speaking module with mocked network calls.
"""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

# Mock environment variables before importing
os.environ.setdefault("VOCAB_BOT_TOKEN", "test_token")
os.environ.setdefault("VOCAB_CHAT_ID", "123456")
os.environ.setdefault("GEMINI_API_KEY", "test_key")


def test_start_speaking_session_success():
    """Test successful session startup."""
    from english_speaking import start_speaking_session
    from english_core import ENGLISH_STATE_FILE, write_json

    # Clear state
    write_json(ENGLISH_STATE_FILE, {})

    with patch("english_speaking.generate_dialogue") as mock_gen, \
         patch("english_speaking.generate_english_tts_voice") as mock_tts, \
         patch("english_speaking.send_message") as mock_send, \
         patch("english_speaking.generate_json_openai") as mock_openai:

        mock_gen.return_value = {
            "scenario_ko": "공항에서 짐을 찾는 상황",
            "target_expressions": ["Where is my luggage?", "Can you help me?"],
            "context_en": "You lost your luggage at the airport",
        }
        mock_openai.return_value = {"text": "Hello! I can help you find your luggage."}
        mock_tts.return_value = None  # No actual TTS file

        success, message = start_speaking_session()

        assert success is True
        assert "시작" in message or "session" in message.lower()

        # Verify state was saved
        from english_core import get_state
        state = get_state()
        assert "speaking_session" in state
        session = state["speaking_session"]
        assert session["mode"] == "roleplay"
        assert len(session["turns"]) == 1
        assert session["turns"][0]["role"] == "assistant"


def test_start_speaking_session_already_active():
    """Test rejection when session already active."""
    from english_speaking import start_speaking_session
    from english_core import ENGLISH_STATE_FILE, write_json

    # Pre-populate active session
    state = {
        "speaking_session": {
            "mode": "roleplay",
            "turns": [{"role": "assistant", "text": "Hello"}],
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    success, message = start_speaking_session()

    assert success is False
    assert "이미 진행 중인" in message or "already" in message.lower()


def test_handle_voice_message_success():
    """Test voice message handling with transcription and response."""
    from english_speaking import handle_voice_message
    from english_core import ENGLISH_STATE_FILE, write_json

    # Setup active session
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "공항에서",
            "target_expressions": ["Where is my luggage?"],
            "turns": [
                {"role": "assistant", "text": "Hello! How can I help?"}
            ],
            "max_turns": 8,
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    with patch("openai.OpenAI") as mock_openai_class, \
         patch("english_speaking.generate_json_openai") as mock_gen_response, \
         patch("english_speaking.generate_english_tts_voice") as mock_tts, \
         patch("english_speaking.log_provider_cost"), \
         patch("english_speaking.check_budget_exit"):

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_transcript = MagicMock()
        mock_transcript.text = "I lost my luggage"
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        mock_gen_response.return_value = {"text": "Let me help you find it."}
        mock_tts.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_file = f.name
            f.write(b"fake audio data")

        try:
            success, user_text, audio_path, message = handle_voice_message(temp_file, 5.0)

            assert success is True
            assert user_text == "I lost my luggage"
            assert "Let me help you find it" in message

            # Verify session was updated
            from english_core import get_state
            session = get_state().get("speaking_session")
            assert len(session["turns"]) == 3  # assistant, user, assistant
            assert session["turns"][1]["role"] == "user"
            assert session["turns"][1]["audio_sec"] == 5.0
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)


def test_handle_voice_message_no_session():
    """Test voice message handling with no active session."""
    from english_speaking import handle_voice_message
    from english_core import ENGLISH_STATE_FILE, write_json

    # Clear state
    write_json(ENGLISH_STATE_FILE, {})

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        temp_file = f.name
        f.write(b"fake audio data")

    try:
        success, user_text, audio_path, message = handle_voice_message(temp_file, 5.0)

        assert success is False
        assert "진행 중인" in message or "no session" in message.lower()
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)


def test_handle_voice_message_max_turns():
    """Test session auto-termination at max turns."""
    from english_speaking import handle_voice_message
    from english_core import ENGLISH_STATE_FILE, write_json

    # Setup session at max_turns-1
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "공항에서",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hi"},
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "How are you?"},
                {"role": "user", "text": "Good"},
                {"role": "assistant", "text": "Great"},
                {"role": "user", "text": "Yes"},
                {"role": "assistant", "text": "Okay"},
            ],  # 7 turns, max is 8, so next user turn hits limit
            "max_turns": 8,
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    with patch("openai.OpenAI") as mock_openai_class, \
         patch("english_speaking.check_budget_exit"), \
         patch("english_speaking.log_provider_cost"):

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_transcript = MagicMock()
        mock_transcript.text = "That's it"
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_file = f.name
            f.write(b"fake audio data")

        try:
            success, user_text, audio_path, message = handle_voice_message(temp_file, 5.0)

            assert success is False
            assert "8턴" in message or "종료" in message

            # Verify session was cleared
            from english_core import get_state
            session = get_state().get("speaking_session")
            assert session is None
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)


def test_finalize_session():
    """Test session finalization."""
    from english_speaking import finalize_session
    from english_core import ENGLISH_STATE_FILE, write_json

    # Setup session
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "공항에서",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hi"},
                {"role": "user", "text": "Hello"},
            ],
            "max_turns": 8,
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    turns_data, message = finalize_session()

    assert "종료" in message or "completed" in message.lower()
    assert turns_data is not None
    assert turns_data["turns"] == state["speaking_session"]["turns"]

    # Verify session was cleared
    from english_core import get_state
    session = get_state().get("speaking_session")
    assert session is None


def test_finalize_session_no_session():
    """Test finalization with no active session."""
    from english_speaking import finalize_session
    from english_core import ENGLISH_STATE_FILE, write_json

    # Clear state
    write_json(ENGLISH_STATE_FILE, {})

    turns_data, message = finalize_session()

    assert turns_data is None
    assert "진행 중인" in message or "no session" in message.lower()


def test_analyze_session_basic():
    """Test analyze_session generates proper analysis."""
    from english_speaking import analyze_session

    session = {
        "turns": [
            {"role": "assistant", "text": "Where do you want to go?"},
            {"role": "user", "text": "I want go to the park", "audio_sec": 3.0},
            {"role": "assistant", "text": "That sounds fun!"},
            {"role": "user", "text": "Yes, I like parks", "audio_sec": 2.0},
        ],
        "scenario_ko": "공원 가기",
        "target_expressions": ["I would like to go to", "It's a great place"],
    }

    with patch("english_speaking.generate_json_openai") as mock_gen:
        mock_gen.return_value = {
            "errors": [
                {
                    "original": "I want go to the park",
                    "corrected": "I want to go to the park",
                    "reason_ko": "to 전치사 누락",
                }
            ],
            "target_hit": {
                "used_well": [],
                "missed": ["I would like to go to", "It's a great place"],
            },
            "metrics": {
                "total_audio_sec": 5.0,
                "avg_words_per_turn": 4.5,
                "filler_count": 0,
            },
            "next_step": "to 전치사 사용을 더 연습해보세요",
        }

        result = analyze_session(session)

        assert result is not None
        assert len(result["errors"]) == 1
        assert result["errors"][0]["corrected"] == "I want to go to the park"
        assert "I would like to go to" in result["target_hit"]["missed"]
        assert result["metrics"]["total_audio_sec"] == 5.0
        assert "to 전치사" in result["next_step"]


def test_analyze_session_failure():
    """Test analyze_session returns None on LLM failure."""
    from english_speaking import analyze_session

    session = {
        "turns": [
            {"role": "assistant", "text": "Hello"},
            {"role": "user", "text": "Hi", "audio_sec": 1.0},
        ],
        "scenario_ko": "인사",
        "target_expressions": [],
    }

    with patch("english_speaking.generate_json_openai") as mock_gen:
        mock_gen.side_effect = RuntimeError("API 오류")

        result = analyze_session(session)

        assert result is None


def test_finalize_session_with_analysis_and_weak_merge():
    """Test finalize_session with successful analysis and weak merge."""
    from english_speaking import finalize_session
    from english_core import (
        ENGLISH_STATE_FILE,
        LEARNED_EN_PHRASE_FILE,
        SPEAKING_SESSIONS_FILE,
        SPEAKING_SUBMISSIONS_FILE,
        write_json,
        read_json,
    )

    # Setup session
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "공항 짐 찾기",
            "target_expressions": ["Where is my luggage?"],
            "turns": [
                {"role": "assistant", "text": "Hello!"},
                {"role": "user", "text": "I lost my baggage", "audio_sec": 3.0},
                {"role": "assistant", "text": "Let me help."},
                {"role": "user", "text": "Thanks", "audio_sec": 1.0},
            ],
            "max_turns": 8,
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    # Clear history files
    write_json(LEARNED_EN_PHRASE_FILE, [])
    write_json(SPEAKING_SESSIONS_FILE, [])
    write_json(SPEAKING_SUBMISSIONS_FILE, [])

    with patch("english_speaking.analyze_session") as mock_analyze, \
         patch("english_speaking.send_message") as mock_send:

        mock_analyze.return_value = {
            "errors": [
                {
                    "original": "I lost my baggage",
                    "corrected": "I lost my luggage",
                    "reason_ko": "baggage → luggage (더 정확한 표현)",
                }
            ],
            "target_hit": {
                "used_well": [],
                "missed": ["Where is my luggage?"],
            },
            "metrics": {
                "total_audio_sec": 4.0,
                "avg_words_per_turn": 2.5,
                "filler_count": 0,
            },
            "next_step": "Lost luggage 상황에서 표현을 더 연습해보세요",
        }

        turns_data, message = finalize_session()

        assert turns_data is not None
        assert "분석 완료" in message
        assert len(turns_data["turns"]) == 4

        # Verify session was cleared
        from english_core import get_state
        session = get_state().get("speaking_session")
        assert session is None

        # Verify learned phrase was merged and marked weak
        phrases = read_json(LEARNED_EN_PHRASE_FILE, [])
        assert len(phrases) > 0
        luggage_item = None
        for item in phrases:
            if item.get("phrase") == "I lost my luggage":
                luggage_item = item
                break
        assert luggage_item is not None
        assert luggage_item["weak"] is True
        assert luggage_item["category"] == "speaking_error"

        # Verify history was recorded
        sessions = read_json(SPEAKING_SESSIONS_FILE, [])
        assert len(sessions) > 0
        assert sessions[-1]["scenario_ko"] == "공항 짐 찾기"
        assert sessions[-1]["turn_count"] == 4
        assert sessions[-1]["feedback_sent"] is True

        submissions = read_json(SPEAKING_SUBMISSIONS_FILE, [])
        assert len(submissions) > 0
        assert submissions[-1]["scenario_ko"] == "공항 짐 찾기"
        assert "analysis" in submissions[-1]


def test_finalize_session_analysis_failure_preserves_transcript():
    """Test finalize_session preserves transcript even if analysis fails."""
    from english_speaking import finalize_session
    from english_core import (
        ENGLISH_STATE_FILE,
        SPEAKING_SUBMISSIONS_FILE,
        write_json,
        read_json,
    )

    # Setup session
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "카페에서 주문",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "What would you like?"},
                {"role": "user", "text": "Coffee please", "audio_sec": 2.0},
            ],
            "max_turns": 8,
            "started_at": "10:30:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)
    write_json(SPEAKING_SUBMISSIONS_FILE, [])

    with patch("english_speaking.analyze_session") as mock_analyze, \
         patch("english_speaking.send_message"):

        mock_analyze.return_value = None  # Simulate analysis failure

        turns_data, message = finalize_session()

        assert turns_data is not None
        assert "분석 실패" in message
        assert "전사 기록됨" in message

        # Verify transcript was preserved
        submissions = read_json(SPEAKING_SUBMISSIONS_FILE, [])
        assert len(submissions) > 0
        assert submissions[-1]["scenario_ko"] == "카페에서 주문"
        assert len(submissions[-1]["turns"]) == 2
        assert "analysis" not in submissions[-1]


def test_weak_merge_order():
    """Test that weak items are marked correctly: merge then mark."""
    from english_speaking import finalize_session
    from english_core import (
        ENGLISH_STATE_FILE,
        LEARNED_EN_PHRASE_FILE,
        write_json,
        read_json,
    )

    # Pre-populate learned phrases with an existing weak item
    existing_phrases = [
        {
            "phrase": "beautiful day",
            "date_added": "2026-07-01",
            "category": "phrase_card",
            "seen_count": 2,
            "weak": True,
            "weak_date": "2026-07-08",
        }
    ]
    write_json(LEARNED_EN_PHRASE_FILE, existing_phrases)

    # Setup session with error containing the same phrase
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "일상 대화",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hello"},
                {"role": "user", "text": "Hello", "audio_sec": 1.0},
            ],
            "max_turns": 8,
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    with patch("english_speaking.analyze_session") as mock_analyze, \
         patch("english_speaking.send_message"):

        mock_analyze.return_value = {
            "errors": [
                {
                    "original": "It's beautifull day",
                    "corrected": "beautiful day",
                    "reason_ko": "a beautiful day 전체 표현",
                }
            ],
            "target_hit": {"used_well": [], "missed": []},
            "metrics": {
                "total_audio_sec": 1.0,
                "avg_words_per_turn": 1.0,
                "filler_count": 0,
            },
            "next_step": "계속 연습하세요",
        }

        finalize_session()

        # Verify weak marking: after merge, weak should be reset to False
        # Then mark_weak should set it back to True
        phrases = read_json(LEARNED_EN_PHRASE_FILE, [])
        beautiful_item = next(
            (p for p in phrases if p.get("phrase") == "beautiful day"),
            None,
        )
        assert beautiful_item is not None
        assert beautiful_item["weak"] is True  # Should be marked weak
        assert beautiful_item["weak_date"] == "2026-07-09"  # Should have today's date


def test_start_shadowing_session_success():
    """Test successful shadowing session startup."""
    from english_speaking import start_shadowing_session
    from english_core import ENGLISH_STATE_FILE, write_json

    # Clear state and set up latest dialogue
    state = {
        "latest_en_dialogue": {
            "date": "2026-07-09",
            "item": {
                "scenario_ko": "공항에서 짐을 찾는 상황",
                "target_expressions": ["Where is my luggage?"],
                "model_dialogue": [
                    {"role": "A", "text": "Hello, where is my luggage?"},
                    {"role": "B", "text": "Let me check for you."},
                    {"role": "A", "text": "Thank you very much."},
                ],
            }
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    with patch("english_speaking.send_message") as mock_send, \
         patch("english_speaking.check_budget_exit"):

        success, message = start_shadowing_session()

        assert success is True
        assert "쉐도잉" in message

        # Verify state was saved
        from english_core import get_state
        state = get_state()
        assert "speaking_session" in state
        session = state["speaking_session"]
        assert session["mode"] == "shadowing"
        assert session["current_index"] == 0
        assert len(session["sentences"]) == 2  # Two role A sentences
        assert session["sentences"][0] == "Hello, where is my luggage?"


def test_start_shadowing_session_no_dialogue():
    """Test rejection when no dialogue data available."""
    from english_speaking import start_shadowing_session
    from english_core import ENGLISH_STATE_FILE, write_json

    write_json(ENGLISH_STATE_FILE, {})

    with patch("english_speaking.check_budget_exit"):
        success, message = start_shadowing_session()

        assert success is False
        assert "회화 데이터" in message or "없습니다" in message


def test_start_shadowing_with_active_roleplay():
    """Test rejection of shadowing when roleplay session active."""
    from english_speaking import start_shadowing_session
    from english_core import ENGLISH_STATE_FILE, write_json

    # Pre-populate active roleplay session
    state = {
        "speaking_session": {
            "mode": "roleplay",
            "turns": [{"role": "assistant", "text": "Hello"}],
        },
        "latest_en_dialogue": {
            "date": "2026-07-09",
            "item": {
                "scenario_ko": "공항",
                "target_expressions": [],
                "model_dialogue": [
                    {"role": "A", "text": "Hello"},
                ],
            }
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    with patch("english_speaking.check_budget_exit"):
        success, message = start_shadowing_session()

        assert success is False
        assert "이미 진행 중인" in message


def test_get_diff_report_perfect_match():
    """Test diff report with perfect match."""
    from english_speaking import _get_diff_report

    report = _get_diff_report("Hello world", "Hello world")

    assert report["missing_words"] == []
    assert report["misread_words"] == []
    assert report["word_order"] == []
    assert report["status_message"] == "✅ 완벽합니다!"


def test_get_diff_report_missing_words():
    """Test diff report with missing words."""
    from english_speaking import _get_diff_report

    report = _get_diff_report("Hello beautiful world", "Hello world")

    assert "beautiful" in report["missing_words"]
    assert "누락: beautiful" in report["status_message"]


def test_get_diff_report_misread_words():
    """Test diff report with misread words."""
    from english_speaking import _get_diff_report

    report = _get_diff_report("Hello world", "Hello beautiful world")

    assert "beautiful" in report["misread_words"]
    assert "오독: beautiful" in report["status_message"]


def test_get_diff_report_word_order():
    """Test diff report detects word order deviation."""
    from english_speaking import _get_diff_report

    report = _get_diff_report("Hello beautiful world", "beautiful Hello world")

    assert "hello" in report["word_order"] or "beautiful" in report["word_order"]
    assert "어순:" in report["status_message"]


def test_get_diff_report_normalization():
    """Test diff report handles case and punctuation."""
    from english_speaking import _get_diff_report

    # Case difference should be ignored
    report = _get_diff_report("Hello World", "hello world")
    assert report["missing_words"] == []
    assert report["misread_words"] == []
    assert report["word_order"] == []

    # Punctuation should be ignored
    report = _get_diff_report("Hello, world!", "Hello world")
    assert report["missing_words"] == []
    assert report["misread_words"] == []
    assert report["word_order"] == []


def test_handle_shadowing_voice_perfect_match():
    """Test shadowing voice handling with perfect match."""
    from english_speaking import handle_voice_message
    from english_core import ENGLISH_STATE_FILE, write_json

    # Setup shadowing session
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "shadowing",
            "scenario_ko": "공항에서",
            "target_expressions": [],
            "sentences": ["Hello, where is my luggage?", "Thank you very much."],
            "current_index": 0,
            "turns": [],
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)

    with patch("openai.OpenAI") as mock_openai_class, \
         patch("english_speaking.check_budget_exit"), \
         patch("english_speaking.log_provider_cost"), \
         patch("english_speaking.send_message") as mock_send:

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_transcript = MagicMock()
        mock_transcript.text = "Hello, where is my luggage?"
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_file = f.name
            f.write(b"fake audio data")

        try:
            success, user_text, audio_path, message = handle_voice_message(temp_file, 3.0)

            assert success is True
            assert user_text == "Hello, where is my luggage?"
            assert message == "✅ 완벽합니다!"

            # Verify session advanced to next sentence
            from english_core import get_state
            session = get_state().get("speaking_session")
            assert session["current_index"] == 1
            assert len(session["turns"]) == 1
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)


def test_handle_shadowing_voice_last_sentence():
    """Test shadowing voice handling on last sentence completes session."""
    from english_speaking import handle_voice_message
    from english_core import ENGLISH_STATE_FILE, SPEAKING_SESSIONS_FILE, write_json

    # Setup shadowing session with only one sentence left
    state = {
        "speaking_session": {
            "date": "2026-07-09",
            "mode": "shadowing",
            "scenario_ko": "공항에서",
            "target_expressions": [],
            "sentences": ["Thank you very much."],
            "current_index": 0,
            "turns": [],
            "started_at": "10:00:00",
        }
    }
    write_json(ENGLISH_STATE_FILE, state)
    write_json(SPEAKING_SESSIONS_FILE, [])

    with patch("openai.OpenAI") as mock_openai_class, \
         patch("english_speaking.check_budget_exit"), \
         patch("english_speaking.log_provider_cost"):

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_transcript = MagicMock()
        mock_transcript.text = "Thank you very much."
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_file = f.name
            f.write(b"fake audio data")

        try:
            success, user_text, audio_path, message = handle_voice_message(temp_file, 2.0)

            assert success is False
            assert "완료" in message or "종료" in message

            # Verify session was cleared
            from english_core import get_state
            session = get_state().get("speaking_session")
            assert session is None
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)


def test_normalize_text():
    """Test text normalization."""
    from english_speaking import _normalize_text

    # Lowercase
    assert _normalize_text("HELLO") == "hello"

    # Punctuation removal
    assert _normalize_text("Hello, world!") == "hello world"

    # Whitespace normalization
    assert _normalize_text("Hello   world") == "hello world"

    # Combined
    assert _normalize_text("HELLO, World!!!") == "hello world"


def test_speaking_stats_empty():
    """Test speaking_stats with no sessions."""
    from english_speaking import speaking_stats
    from english_core import SPEAKING_SESSIONS_FILE, SPEAKING_SUBMISSIONS_FILE, write_json

    # Clear files
    write_json(SPEAKING_SESSIONS_FILE, [])
    write_json(SPEAKING_SUBMISSIONS_FILE, [])

    stats = speaking_stats()

    assert stats["total_sessions"] == 0
    assert stats["this_month_sessions"] == 0
    assert stats["total_audio_sec"] == 0.0
    assert stats["recent_scenario"] == "기록 없음"


def test_speaking_stats_basic():
    """Test speaking_stats with sample sessions."""
    from english_speaking import speaking_stats
    from english_core import SPEAKING_SESSIONS_FILE, SPEAKING_SUBMISSIONS_FILE, write_json
    from datetime import date

    today = str(date.today())
    this_month = today[:7]

    # Create sample sessions
    sessions = [
        {
            "date": this_month + "-01",
            "mode": "roleplay",
            "scenario_ko": "첫 번째 상황",
            "turn_count": 4,
            "target_expressions": [],
            "feedback_sent": True,
        },
        {
            "date": this_month + "-05",
            "mode": "shadowing",
            "scenario_ko": "두 번째 상황",
            "turn_count": 2,
            "target_expressions": [],
            "feedback_sent": False,
        },
        {
            "date": today,
            "mode": "roleplay",
            "scenario_ko": "최근 상황",
            "turn_count": 3,
            "target_expressions": [],
            "feedback_sent": True,
        },
    ]

    # Create sample submissions with audio
    submissions = [
        {
            "session_date": this_month + "-01",
            "submitted_at": f"{this_month}-01T10:00:00",
            "scenario_ko": "첫 번째 상황",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hello"},
                {"role": "user", "text": "Hi", "audio_sec": 2.0},
                {"role": "assistant", "text": "How are you?"},
                {"role": "user", "text": "Good", "audio_sec": 1.5},
            ],
        },
        {
            "session_date": this_month + "-05",
            "submitted_at": f"{this_month}-05T11:00:00",
            "scenario_ko": "두 번째 상황",
            "target_expressions": [],
            "mode": "shadowing",
            "turns": [
                {
                    "sentence_index": 0,
                    "model_text": "Thank you",
                    "user_text": "Thank you",
                    "audio_sec": 3.0,
                    "diff_report": {"missing_words": [], "misread_words": []},
                }
            ],
        },
        {
            "session_date": today,
            "submitted_at": f"{today}T12:00:00",
            "scenario_ko": "최근 상황",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hi"},
                {"role": "user", "text": "Hello", "audio_sec": 2.5},
            ],
        },
    ]

    write_json(SPEAKING_SESSIONS_FILE, sessions)
    write_json(SPEAKING_SUBMISSIONS_FILE, submissions)

    stats = speaking_stats()

    assert stats["total_sessions"] == 3
    assert stats["this_month_sessions"] == 3
    assert stats["total_audio_sec"] == 9.0  # 2.0 + 1.5 + 3.0 + 2.5
    assert stats["recent_scenario"] == "최근 상황"
    assert stats["mode_breakdown"]["roleplay"] == 2
    assert stats["mode_breakdown"]["shadowing"] == 1


def test_speaking_stats_missing_file():
    """Test speaking_stats when files don't exist."""
    from english_speaking import speaking_stats
    from english_core import SPEAKING_SESSIONS_FILE, SPEAKING_SUBMISSIONS_FILE
    import os

    # Ensure files don't exist
    try:
        os.remove(SPEAKING_SESSIONS_FILE)
    except FileNotFoundError:
        pass
    try:
        os.remove(SPEAKING_SUBMISSIONS_FILE)
    except FileNotFoundError:
        pass

    stats = speaking_stats()

    assert stats["total_sessions"] == 0
    assert stats["this_month_sessions"] == 0
    assert stats["total_audio_sec"] == 0.0
    assert stats["recent_scenario"] == "기록 없음"


def test_speaking_stats_partial_month():
    """Test speaking_stats filters by month correctly."""
    from english_speaking import speaking_stats
    from english_core import SPEAKING_SESSIONS_FILE, SPEAKING_SUBMISSIONS_FILE, write_json

    sessions = [
        {
            "date": "2026-06-15",
            "mode": "roleplay",
            "scenario_ko": "지난달 상황",
            "turn_count": 2,
            "target_expressions": [],
            "feedback_sent": False,
        },
        {
            "date": "2026-07-09",
            "mode": "roleplay",
            "scenario_ko": "이달 상황",
            "turn_count": 3,
            "target_expressions": [],
            "feedback_sent": True,
        },
    ]

    submissions = [
        {
            "session_date": "2026-06-15",
            "submitted_at": "2026-06-15T10:00:00",
            "scenario_ko": "지난달 상황",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hi"},
                {"role": "user", "text": "Hello", "audio_sec": 1.0},
            ],
        },
        {
            "session_date": "2026-07-09",
            "submitted_at": "2026-07-09T10:00:00",
            "scenario_ko": "이달 상황",
            "target_expressions": [],
            "turns": [
                {"role": "assistant", "text": "Hello"},
                {"role": "user", "text": "Hi", "audio_sec": 2.0},
            ],
        },
    ]

    write_json(SPEAKING_SESSIONS_FILE, sessions)
    write_json(SPEAKING_SUBMISSIONS_FILE, submissions)

    # Mock today to be in July 2026
    with patch("english_speaking.TODAY") as mock_today:
        mock_today.return_value = "2026-07-09"

        stats = speaking_stats()

        assert stats["total_sessions"] == 2
        assert stats["this_month_sessions"] == 1  # Only July
        assert stats["total_audio_sec"] == 3.0  # Both months' audio


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
