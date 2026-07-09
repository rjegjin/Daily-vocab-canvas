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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
