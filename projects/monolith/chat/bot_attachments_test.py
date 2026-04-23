"""Tests for attachment handling in the streaming response flow.

Verifies that image attachments are appended to the prompt as context
text (e.g. "[Attached image 'cat.png': A tabby cat]") when
run_stream_events is called via on_message.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import PartDeltaEvent, TextPartDelta

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
    content: str = "check this image",
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
    """Build a ChatBot with mocked internals."""
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
    mock_store.get_blob = MagicMock(return_value=None)
    return mock_store


def _make_image_attachment(
    filename="cat.png", content_type="image/png", data=b"\x89PNG"
):
    att = MagicMock()
    att.filename = filename
    att.content_type = content_type
    att.read = AsyncMock(return_value=data)
    return att


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImageContextInPrompt:
    @pytest.mark.asyncio
    async def test_image_context_appended_to_prompt(self):
        """Image attachment context appears in the prompt sent to run_stream_events."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="What is in this image?", mentions=[bot_user])

        img = _make_image_attachment(
            filename="cat.png", content_type="image/png", data=b"\x89PNG"
        )
        msg.attachments = [img]

        mock_store = _make_store()

        events = [_text_delta("That's a cat.")]
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
                        "description": "A tabby cat sitting on a windowsill",
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
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "cat.png" in text
        assert "A tabby cat sitting on a windowsill" in text

    @pytest.mark.asyncio
    async def test_image_context_uses_attached_image_format(self):
        """Image context wraps each attachment in '[Attached image ...' format."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Look at these", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("ok")]
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
                        "data": b"\xff\xd8\xff",
                        "content_type": "image/jpeg",
                        "filename": "photo.jpg",
                        "description": "A mountain landscape",
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
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "[Attached image 'photo.jpg': A mountain landscape]" in text

    @pytest.mark.asyncio
    async def test_multiple_attachments_all_included_in_prompt(self):
        """All attachments are included in the prompt when multiple are provided."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Compare these two images", mentions=[bot_user])
        msg.attachments = [
            _make_image_attachment(filename="first.png"),
            _make_image_attachment(filename="second.jpg", content_type="image/jpeg"),
        ]
        mock_store = _make_store()

        events = [_text_delta("Both images look great.")]
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
                        "description": "First image: a dog",
                    },
                    {
                        "data": b"\xff\xd8\xff",
                        "content_type": "image/jpeg",
                        "filename": "second.jpg",
                        "description": "Second image: a cat",
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
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "first.png" in text
        assert "First image: a dog" in text
        assert "second.jpg" in text
        assert "Second image: a cat" in text

    @pytest.mark.asyncio
    async def test_no_image_context_when_no_attachments(self):
        """Prompt does not include image context when there are no attachments."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Plain text message", mentions=[bot_user])
        msg.attachments = []
        mock_store = _make_store()

        events = [_text_delta("ok")]
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
        assert "[Attached image" not in prompt_arg
