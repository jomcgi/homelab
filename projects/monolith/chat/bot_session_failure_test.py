"""Tests for on_message() when the DB session fails before attachments is assigned.

Regression test for a latent NameError: if get_engine() or Session.__enter__()
raises *before* `attachments = await download_image_attachments(...)` is reached,
the variable `attachments` is unbound.  A subsequent `should_respond` check
returning True would then cause _generate_response(message, attachments) to raise
NameError, propagating out of the catch-all try/except and crashing the handler.

The fix (bot.py) initialises `attachments = []` before the try block, ensuring
the variable is always bound regardless of how early the session fails.
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


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals so it never touches real services."""
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
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


def _make_message(
    content: str = "hello",
    author_bot: bool = False,
    channel_id: int = 99,
    msg_id: int = 1,
    mentions=None,
    reference=None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = author_bot
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = reference
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    msg.attachments = []
    return msg


class TestOnMessageSessionFailureBeforeAttachments:
    @pytest.mark.asyncio
    async def test_get_engine_raises_before_attachments_no_name_error(self):
        """on_message does not raise NameError when get_engine() fails.

        This tests the fix where attachments=[] is initialised before the
        try block.  Without the fix, get_engine() raising means 'attachments'
        is unbound; calling _generate_response(message, attachments) later
        would raise NameError when the bot is mentioned.
        """
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None

        mock_generate_response = AsyncMock(return_value="Hello!")

        with (
            patch(
                "chat.bot.get_engine", side_effect=RuntimeError("engine unavailable")
            ),
            patch("chat.bot.Session"),
            patch.object(bot, "_generate_response", mock_generate_response),
        ):
            # Must not raise NameError (or any other unhandled exception)
            await bot.on_message(message)

        # The bot should still have attempted to reply using an empty attachments list
        mock_generate_response.assert_called_once()
        _, kwargs = mock_generate_response.call_args
        # current_attachments should be the empty-list fallback (falsy → None was passed)
        # or []  — either way, not unbound
        call_args = mock_generate_response.call_args[0]
        # attachments arg is the second positional arg or keyword current_attachments
        passed_attachments = (
            call_args[1] if len(call_args) > 1 else mock_generate_response.call_args[1].get("current_attachments", [])
        )
        assert passed_attachments == [] or passed_attachments is None

    @pytest.mark.asyncio
    async def test_session_enter_raises_before_attachments_no_name_error(self):
        """on_message does not raise NameError when Session.__enter__() fails.

        Session.__enter__ raising before download_image_attachments() is called
        means attachments was never assigned inside the try block.  The initialised
        attachments=[] default ensures _generate_response is still callable.
        """
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None

        mock_session_instance = MagicMock()
        mock_session_instance.__enter__ = MagicMock(
            side_effect=RuntimeError("session enter failed")
        )
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        mock_generate_response = AsyncMock(return_value="Hello!")

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session", return_value=mock_session_instance),
            patch.object(bot, "_generate_response", mock_generate_response),
        ):
            await bot.on_message(message)

        # The response was still generated (without a NameError)
        mock_generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_fails_not_responding_bot_returns_cleanly(self):
        """on_message returns cleanly after store failure when bot is not mentioned."""
        bot = _make_bot()
        message = _make_message(content="Just talking", mentions=[], author_bot=False)
        message.reference = None

        with (
            patch(
                "chat.bot.get_engine", side_effect=RuntimeError("engine unavailable")
            ),
            patch("chat.bot.Session"),
        ):
            # Should not raise, and should not attempt to generate a response
            await bot.on_message(message)

        message.reply.assert_not_called()
