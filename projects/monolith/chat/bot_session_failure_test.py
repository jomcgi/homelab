"""Tests for on_message() when the DB session fails during lock acquisition.

With the message lock pattern, get_engine() or Session failures during
acquire_lock() cause on_message to return early — the message is not
processed and no response is attempted. This is the correct behaviour:
if we can't claim the lock, we can't safely process.
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


class TestOnMessageSessionFailureDuringLock:
    @pytest.mark.asyncio
    async def test_get_engine_raises_during_lock_returns_cleanly(self):
        """on_message returns cleanly when get_engine() fails during lock acquisition.

        With the lock-first pattern, a DB failure during acquire_lock means the
        message cannot be claimed. on_message should return without processing.
        """
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None

        with patch(
            "chat.bot.get_engine", side_effect=RuntimeError("engine unavailable")
        ):
            await bot.on_message(message)

        # No reply should be attempted — lock acquisition failed
        message.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_enter_raises_during_lock_returns_cleanly(self):
        """on_message returns cleanly when Session.__enter__() fails during lock.

        Session context manager failure prevents lock acquisition, so the
        message is not processed.
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

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session", return_value=mock_session_instance),
        ):
            await bot.on_message(message)

        message.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_fails_not_responding_bot_returns_cleanly(self):
        """on_message returns cleanly after lock failure when bot is not mentioned."""
        bot = _make_bot()
        message = _make_message(content="Just talking", mentions=[], author_bot=False)
        message.reference = None

        with (
            patch(
                "chat.bot.get_engine", side_effect=RuntimeError("engine unavailable")
            ),
            patch("chat.bot.Session"),
        ):
            await bot.on_message(message)

        message.reply.assert_not_called()
