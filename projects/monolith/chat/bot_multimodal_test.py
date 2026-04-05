"""Tests for multimodal image forwarding to the agent.

Gemma 4 is multimodal — when users send images, the raw image bytes
must be forwarded to the agent as BinaryContent so the model can
actually *see* the image, not just a text description.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent

from chat.bot import ChatBot


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_message(
    content: str = "wdyt about this?",
    channel_id: int = 99,
    msg_id: int = 1,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = []
    msg.reference = None
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
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


def _setup_bot_mocks(bot, response_text="That's a cool image."):
    """Wire up store and agent mocks, return the bot."""
    mock_store = MagicMock()
    mock_store.get_recent = MagicMock(return_value=[])
    mock_store.get_attachments = MagicMock(return_value={})
    mock_store.get_channel_summary = MagicMock(return_value=None)
    mock_store.get_user_summaries_for_users = MagicMock(return_value=[])

    mock_result = MagicMock()
    mock_result.new_messages.return_value = []
    mock_result.output = response_text
    bot.agent.run = AsyncMock(return_value=mock_result)

    return mock_store


class TestMultimodalImageForwarding:
    @pytest.mark.asyncio
    async def test_image_bytes_sent_as_binary_content(self):
        """When attachments have image data, agent.run receives BinaryContent objects."""
        bot = _make_bot()
        msg = _make_message(content="What is this?")
        mock_store = _setup_bot_mocks(bot)

        attachments = [
            {
                "data": b"\x89PNG\r\n\x1a\n",
                "content_type": "image/png",
                "filename": "meme.png",
                "description": "A political meme",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        # agent.run should receive a list, not a plain string
        prompt_arg = bot.agent.run.call_args[0][0]
        assert isinstance(prompt_arg, list), (
            f"Expected list with BinaryContent, got {type(prompt_arg).__name__}"
        )

        # Find BinaryContent parts in the list
        binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
        assert len(binary_parts) == 1
        assert binary_parts[0].data == b"\x89PNG\r\n\x1a\n"
        assert binary_parts[0].media_type == "image/png"

    @pytest.mark.asyncio
    async def test_multiple_images_all_forwarded(self):
        """Multiple image attachments each get their own BinaryContent."""
        bot = _make_bot()
        msg = _make_message(content="Compare these")
        mock_store = _setup_bot_mocks(bot)

        attachments = [
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
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        prompt_arg = bot.agent.run.call_args[0][0]
        binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
        assert len(binary_parts) == 2
        assert binary_parts[0].media_type == "image/png"
        assert binary_parts[1].media_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_no_attachments_sends_plain_string(self):
        """Without attachments, agent.run receives a plain string (no regression)."""
        bot = _make_bot()
        msg = _make_message(content="Just text")
        mock_store = _setup_bot_mocks(bot)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=None)

        prompt_arg = bot.agent.run.call_args[0][0]
        assert isinstance(prompt_arg, str)

    @pytest.mark.asyncio
    async def test_text_description_still_in_prompt(self):
        """Image text descriptions remain in the prompt for context alongside BinaryContent."""
        bot = _make_bot()
        msg = _make_message(content="What is this?")
        mock_store = _setup_bot_mocks(bot)

        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "cat.png",
                "description": "A tabby cat on a windowsill",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        prompt_arg = bot.agent.run.call_args[0][0]
        # The text part of the list should contain the image description
        text_parts = [p for p in prompt_arg if isinstance(p, str)]
        combined_text = " ".join(text_parts)
        assert "A tabby cat on a windowsill" in combined_text

    @pytest.mark.asyncio
    async def test_attachment_with_none_data_skipped(self):
        """Attachments with None data don't produce BinaryContent (e.g. failed downloads)."""
        bot = _make_bot()
        msg = _make_message(content="Check this")
        mock_store = _setup_bot_mocks(bot)

        attachments = [
            {
                "data": None,
                "content_type": "image/png",
                "filename": "broken.png",
                "description": "(image could not be processed)",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        prompt_arg = bot.agent.run.call_args[0][0]
        # Should still work but no BinaryContent for the broken attachment
        if isinstance(prompt_arg, list):
            binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
            assert len(binary_parts) == 0
