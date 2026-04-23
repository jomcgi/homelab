"""Tests for multimodal image forwarding to the agent via streaming.

When users send images, the raw image bytes must be forwarded to the
agent as BinaryContent so the model can actually *see* the image.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent, PartDeltaEvent, TextPartDelta

from chat.bot import ChatBot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _text_delta(content: str) -> PartDeltaEvent:
    return PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=content))


async def _async_iter(events):
    for e in events:
        yield e


def _make_message(
    content: str = "wdyt about this?",
    channel_id: int = 99,
    msg_id: int = 1,
    mentions: list | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = None
    msg.embeds = []
    sent = MagicMock(id=100)
    sent.edit = AsyncMock()
    msg.reply = AsyncMock(return_value=sent)
    return msg


def _make_bot() -> ChatBot:
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
        patch("chat.bot.VisionClient"),
        patch("chat.bot.create_agent") as mock_ca,
    ):
        mock_ec.return_value = AsyncMock()
        mock_ca.return_value = MagicMock()
        bot = ChatBot()
    bot._connection = MagicMock()
    bot._connection.user = MagicMock()
    bot._connection.user.id = 999
    bot._connection.user.display_name = "BotUser"
    return bot


def _make_store():
    mock_store = AsyncMock()
    mock_store.save_message = AsyncMock()
    mock_store.get_recent = MagicMock(return_value=[])
    mock_store.get_attachments = MagicMock(return_value={})
    mock_store.get_channel_summary = MagicMock(return_value=None)
    mock_store.get_user_summaries_for_users = MagicMock(return_value=[])
    mock_store.acquire_lock = MagicMock(return_value=True)
    mock_store.mark_completed = MagicMock()
    return mock_store


def _make_image_attachment(
    filename="meme.png", content_type="image/png", data=b"\x89PNG\r\n\x1a\n"
):
    att = MagicMock()
    att.filename = filename
    att.content_type = content_type
    att.read = AsyncMock(return_value=data)
    return att


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMultimodalImageForwarding:
    @pytest.mark.asyncio
    async def test_image_bytes_sent_as_binary_content(self):
        """When attachments have image data, run_stream_events receives BinaryContent."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="What is this?", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("That's a cool image.")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": b"\x89PNG\r\n\x1a\n",
                        "content_type": "image/png",
                        "filename": "meme.png",
                        "description": "A political meme",
                    }
                ],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock, return_value=""),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        assert isinstance(prompt_arg, list), (
            f"Expected list with BinaryContent, got {type(prompt_arg).__name__}"
        )

        binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
        assert len(binary_parts) == 1
        assert binary_parts[0].data == b"\x89PNG\r\n\x1a\n"
        assert binary_parts[0].media_type == "image/png"

    @pytest.mark.asyncio
    async def test_multiple_images_all_forwarded(self):
        """Multiple image attachments each get their own BinaryContent."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Compare these", mentions=[bot_user])
        msg.attachments = [
            _make_image_attachment(filename="first.png"),
            _make_image_attachment(
                filename="second.jpg", content_type="image/jpeg", data=b"\xff\xd8\xff"
            ),
        ]
        mock_store = _make_store()

        events = [_text_delta("Both look nice.")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": b"\x89PNG",
                        "content_type": "image/png",
                        "filename": "first.png",
                        "description": "First image",
                    },
                    {
                        "data": b"\xff\xd8\xff",
                        "content_type": "image/jpeg",
                        "filename": "second.jpg",
                        "description": "Second image",
                    },
                ],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock, return_value=""),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
        assert len(binary_parts) == 2
        assert binary_parts[0].media_type == "image/png"
        assert binary_parts[1].media_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_no_attachments_sends_plain_string(self):
        """Without attachments, run_stream_events receives a plain string."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Just text", mentions=[bot_user])
        msg.attachments = []
        mock_store = _make_store()

        events = [_text_delta("Sure thing.")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        assert isinstance(prompt_arg, str)

    @pytest.mark.asyncio
    async def test_text_description_still_in_prompt(self):
        """Image text descriptions remain in the prompt alongside BinaryContent."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="What is this?", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("It's a cat.")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": b"\x89PNG",
                        "content_type": "image/png",
                        "filename": "cat.png",
                        "description": "A tabby cat on a windowsill",
                    }
                ],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock, return_value=""),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        text_parts = [p for p in prompt_arg if isinstance(p, str)]
        combined_text = " ".join(text_parts)
        assert "A tabby cat on a windowsill" in combined_text

    @pytest.mark.asyncio
    async def test_attachment_with_none_data_skipped(self):
        """Attachments with None data don't produce BinaryContent."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Check this", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("I see.")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": None,
                        "content_type": "image/png",
                        "filename": "broken.png",
                        "description": "(image could not be processed)",
                    }
                ],
            ),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        if isinstance(prompt_arg, list):
            binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
            assert len(binary_parts) == 0
