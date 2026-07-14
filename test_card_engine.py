"""Image-card quality tests with all provider/network calls mocked."""

from unittest.mock import MagicMock, patch

from PIL import Image

import card_engine


def _icon(color=(80, 150, 220, 255)):
    icon = Image.new("RGBA", (card_engine.ICON_H, card_engine.ICON_H), "white")
    margin = card_engine.ICON_H // 4
    for x in range(margin, card_engine.ICON_H - margin):
        for y in range(margin, card_engine.ICON_H - margin):
            icon.putpixel((x, y), color)
    return icon


def _vocab(count=9):
    return [
        {"word": f"word-{idx}", "visual": f"visual concept {idx}"}
        for idx in range(count)
    ]


def test_create_flashcard_rejects_incomplete_icons(tmp_path):
    output = tmp_path / "card.png"
    vocab = _vocab(2)

    result = card_engine.create_flashcard(
        [_icon(), None],
        vocab,
        lambda item, fonts: [],
        {},
        str(output),
    )

    assert result is None
    assert not output.exists()


def test_openai_generation_uses_three_icon_batches_and_medium_quality(monkeypatch):
    monkeypatch.delenv("VOCAB_OPENAI_IMAGE_QUALITY", raising=False)
    vocab = _vocab()
    calls = []

    def fake_generate(concepts, lang_hint=""):
        calls.append((concepts, lang_hint))
        return Image.new("RGBA", (1024, 1024), "white")

    with patch.object(card_engine, "generate_icon_sheet_openai", side_effect=fake_generate), \
         patch.object(card_engine, "split_icon_sheet", side_effect=lambda sheet, count: [_icon()] * count), \
         patch.object(card_engine, "_save_cached_icon"), \
         patch.object(card_engine, "log_provider_cost") as log_cost:
        icons = card_engine.generate_icons_openai(vocab, "es", "Spanish")

    assert [len(concepts) for concepts, _ in calls] == [3, 3, 3]
    assert len(icons) == 9
    assert log_cost.call_count == 1
    assert log_cost.call_args.kwargs["quality"] == "medium"
    assert log_cost.call_args.kwargs["img_count"] == 3


def test_cache_key_changes_with_visual_model_and_quality(tmp_path, monkeypatch):
    monkeypatch.setattr(card_engine, "_ICON_CACHE_DIR", str(tmp_path))

    base = card_engine._icon_cache_path(
        "es", "banco", "wooden bench", "openai", "gpt-image-1-mini", "medium"
    )
    different_visual = card_engine._icon_cache_path(
        "es", "banco", "river bank", "openai", "gpt-image-1-mini", "medium"
    )
    different_quality = card_engine._icon_cache_path(
        "es", "banco", "wooden bench", "openai", "gpt-image-1-mini", "high"
    )

    assert base != different_visual
    assert base != different_quality


def test_blank_icon_is_not_usable():
    assert card_engine._is_icon_usable(Image.new("RGBA", (162, 162), "white")) is False
    assert card_engine._is_icon_usable(_icon()) is True


def test_telegram_uses_document_upload_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("VOCAB_TELEGRAM_SEND_MODE", raising=False)
    image_path = tmp_path / "card.png"
    _icon().save(image_path)
    session = MagicMock()
    session.post.return_value.json.return_value = {"ok": True}

    with patch("card_engine.requests.Session", return_value=session):
        assert card_engine.send_to_telegram(str(image_path), "token", "chat") is True

    url = session.post.call_args.args[0]
    kwargs = session.post.call_args.kwargs
    assert url.endswith("/sendDocument")
    assert "document" in kwargs["files"]
