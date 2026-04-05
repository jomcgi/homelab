"""Tests for _generate_response() with current_attachments.

Covers the `if current_attachments:` branch that appends image context
to the user prompt when the incoming message has image attachments.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_message(
    content: str = "check this image",
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


class TestGenerateResponseWithAttachments:
    @pytest.mark.asyncio
    async def test_image_context_appended_to_prompt(self):
        """_generate_response includes image context in the prompt when attachments are given."""
        bot = _make_bot()
        msg = _make_message(content="What is in this image?")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "That's a cat."
        bot.agent.run = AsyncMock(return_value=mock_result)

        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "cat.png",
                "description": "A tabby cat sitting on a windowsill",
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
            result = await bot._generate_response(msg, current_attachments=attachments)

        assert result == ("That's a cat.", None)
        prompt_arg = bot.agent.run.call_args[0][0]
        # prompt_arg is a list when images are present; text is the first element
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "cat.png" in text
        assert "A tabby cat sitting on a windowsill" in text

    @pytest.mark.asyncio
    async def test_image_context_uses_attached_image_format(self):
        """_generate_response wraps each attachment in '[Attached image ...' format."""
        bot = _make_bot()
        msg = _make_message(content="Look at these")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "ok"
        bot.agent.run = AsyncMock(return_value=mock_result)

        attachments = [
            {
                "data": b"\xff\xd8\xff",
                "content_type": "image/jpeg",
                "filename": "photo.jpg",
                "description": "A mountain landscape",
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
        # prompt_arg is a list when images are present; text is the first element
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        # The format is: [Attached image 'filename': description]
        assert "[Attached image 'photo.jpg': A mountain landscape]" in text

    @pytest.mark.asyncio
    async def test_multiple_attachments_all_included_in_prompt(self):
        """All attachments are included in the prompt when multiple are provided."""
        bot = _make_bot()
        msg = _make_message(content="Compare these two images")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "Both images look great."
        bot.agent.run = AsyncMock(return_value=mock_result)

        attachments = [
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
        # prompt_arg is a list when images are present; text is the first element
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "first.png" in text
        assert "First image: a dog" in text
        assert "second.jpg" in text
        assert "Second image: a cat" in text

    @pytest.mark.asyncio
    async def test_no_image_context_when_attachments_is_none(self):
        """Prompt does not include image context when current_attachments is None."""
        bot = _make_bot()
        msg = _make_message(content="Plain text message")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "ok"
        bot.agent.run = AsyncMock(return_value=mock_result)

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
        assert "[Attached image" not in prompt_arg

    @pytest.mark.asyncio
    async def test_no_image_context_when_attachments_is_empty_list(self):
        """Prompt does not include image context when current_attachments is []."""
        bot = _make_bot()
        msg = _make_message(content="Any message")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "response"
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=[])

        prompt_arg = bot.agent.run.call_args[0][0]
        assert "[Attached image" not in prompt_arg
