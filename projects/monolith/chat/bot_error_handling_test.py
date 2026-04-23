"""Tests for error handling in _process_message when _stream_response fails.

Covers:
- _stream_response raises -> error reply sent to user
- _stream_response raises AND error reply fails -> both exceptions logged
- Storage failure after successful reply does not trigger error reply
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _make_message(
    content: str = "hello",
    author_bot: bool = False,
    channel_id: int = 99,
    msg_id: int = 1,
    mentions: list | None = None,
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
    msg.attachments = []
    msg.embeds = []
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


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


def _make_store():
    """Create a mock MessageStore with standard defaults."""
    mock_store = AsyncMock()
    mock_store.save_message = AsyncMock()
    mock_store.get_recent = MagicMock(return_value=[])
    mock_store.get_attachments = MagicMock(return_value={})
    mock_store.get_channel_summary = MagicMock(return_value=None)
    mock_store.get_user_summaries_for_users = MagicMock(return_value=[])
    mock_store.acquire_lock = MagicMock(return_value=True)
    mock_store.mark_completed = MagicMock()
    mock_store.release_lock = MagicMock()
    return mock_store


# ---------------------------------------------------------------------------
# Test: _stream_response raises -> error reply sent
# ---------------------------------------------------------------------------


class TestStreamResponseFailureSendsErrorReply:
    @pytest.mark.asyncio
    async def test_error_reply_when_stream_response_raises(self):
        """When _stream_response raises, on_message sends the 'Sorry...' error reply."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        mock_store = _make_store()

        bot._stream_response = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Error reply should have been sent
        reply_calls = message.reply.call_args_list
        sorry_calls = [c for c in reply_calls if "trouble" in str(c)]
        assert len(sorry_calls) >= 1


# ---------------------------------------------------------------------------
# Test: error reply itself fails -> both exceptions swallowed and logged
# ---------------------------------------------------------------------------


class TestErrorReplyFails:
    @pytest.mark.asyncio
    async def test_error_reply_failure_swallowed_and_both_exceptions_logged(self):
        """When _stream_response raises AND the error reply also raises,
        on_message swallows both without propagating and calls logger.exception
        once for the respond failure and once for the error-reply failure."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        mock_store = _make_store()

        # _stream_response raises
        bot._stream_response = AsyncMock(side_effect=RuntimeError("LLM down"))
        # Error reply also fails
        message.reply = AsyncMock(side_effect=RuntimeError("discord dead"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.logger") as mock_logger,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Must not propagate either exception.
            await bot.on_message(message)

        # logger.exception should be called at least twice:
        #   1. "Failed to respond to message ..."
        #   2. "Failed to send error reply for message ..."
        exception_calls = mock_logger.exception.call_args_list
        messages_logged = [c.args[0] for c in exception_calls]
        assert any("Failed to respond" in m for m in messages_logged)
        assert any("Failed to send error reply" in m for m in messages_logged)

    @pytest.mark.asyncio
    async def test_on_message_returns_without_raising_on_double_failure(self):
        """on_message does not propagate when _stream_response AND error reply both raise."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        mock_store = _make_store()

        bot._stream_response = AsyncMock(side_effect=RuntimeError("LLM down"))
        message.reply = AsyncMock(side_effect=RuntimeError("discord unavailable"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should NOT raise despite both failures
            await bot.on_message(message)


# ---------------------------------------------------------------------------
# Test: mark_completed called even after error
# ---------------------------------------------------------------------------


class TestMarkCompletedAfterError:
    @pytest.mark.asyncio
    async def test_mark_completed_called_after_stream_response_failure(self):
        """mark_completed is called even when _stream_response raises."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        mock_store = _make_store()

        bot._stream_response = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        mock_store.mark_completed.assert_called()
