"""Tests for ChatBot exponential backoff delays and nested error-reply failure."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chat.bot import ChatBot, LLM_MAX_RETRIES, LLM_RETRY_BASE_DELAY


# ---------------------------------------------------------------------------
# Shared helpers (mirrors bot_coverage_test.py patterns)
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_message(
    content: str = "hello bot",
    author_bot: bool = False,
    channel_id: int = 99,
    msg_id: int = 1,
    mentions: list | None = None,
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
    msg.reference = None
    msg.attachments = []
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals so it never touches real services."""
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


# ---------------------------------------------------------------------------
# Exponential backoff delay values
# ---------------------------------------------------------------------------


class TestExponentialBackoffDelays:
    """Verify that asyncio.sleep is called with LLM_RETRY_BASE_DELAY * 2**attempt."""

    @pytest.mark.asyncio
    async def test_sleep_delays_on_all_failures(self):
        """All 3 attempts fail: asyncio.sleep called with 1.0s then 2.0s (no sleep on last)."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        # Agent always raises
        bot.agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(RuntimeError, match="LLM down"):
                await bot._generate_response(msg)

        # Sleep called for attempt 0 (delay=1.0) and attempt 1 (delay=2.0)
        # No sleep for attempt 2 (last attempt, condition is False)
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list == [
            call(LLM_RETRY_BASE_DELAY * (2**0)),  # 1.0
            call(LLM_RETRY_BASE_DELAY * (2**1)),  # 2.0
        ]

    @pytest.mark.asyncio
    async def test_sleep_delay_values_match_formula(self):
        """Explicit check: delays are exactly 1.0s and 2.0s per the formula."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        error = ConnectionError("timeout")
        bot.agent.run = AsyncMock(side_effect=error)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError):
                await bot._generate_response(msg)

        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0]

    @pytest.mark.asyncio
    async def test_no_sleep_when_first_attempt_succeeds(self):
        """No sleep when the first attempt succeeds."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "All good!"
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = await bot._generate_response(msg)

        assert result == ("All good!", None)
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_sleep_once_when_second_attempt_succeeds(self):
        """One sleep (1.0s) when first attempt fails but second succeeds."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "Recovered!"
        bot.agent.run = AsyncMock(side_effect=[RuntimeError("first fail"), mock_result])

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = await bot._generate_response(msg)

        assert result == ("Recovered!", None)
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args_list == [call(1.0)]

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self):
        """_generate_response re-raises the last exception after all retries fail."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        bot.agent.run = AsyncMock(side_effect=ValueError("model error"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ValueError, match="model error"):
                await bot._generate_response(msg)

        # agent.run called exactly LLM_MAX_RETRIES times
        assert bot.agent.run.call_count == LLM_MAX_RETRIES


# ---------------------------------------------------------------------------
# Nested error-reply failure (graceful degradation)
# ---------------------------------------------------------------------------


class TestNestedErrorReplyFailure:
    """on_message returns gracefully when BOTH the response reply AND the error
    fallback reply raise exceptions."""

    @pytest.mark.asyncio
    async def test_on_message_returns_without_raising_on_double_reply_failure(self):
        """on_message does not propagate when response reply AND error reply both raise."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot_user = bot.user

        message = _make_message(mentions=[bot_user])
        # Both reply calls raise
        message.reply = AsyncMock(side_effect=RuntimeError("discord unavailable"))

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "Some response"
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

            # Should NOT raise despite both reply calls failing
            await bot.on_message(message)

        # reply was called twice: once for the response, once for the error fallback
        assert message.reply.call_count == 2

    @pytest.mark.asyncio
    async def test_logger_exception_called_for_both_failures(self):
        """logger.exception is called for both the response failure and the error reply failure."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot_user = bot.user

        message = _make_message(mentions=[bot_user])
        message.reply = AsyncMock(side_effect=OSError("network gone"))

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "Response text"
        bot.agent.run = AsyncMock(return_value=mock_result)

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

            await bot.on_message(message)

        # logger.exception should have been called at least twice —
        # once for "Failed to respond" and once for "Failed to send error reply"
        exception_calls = mock_logger.exception.call_args_list
        assert len(exception_calls) >= 2

        messages_logged = [c.args[0] for c in exception_calls]
        assert any("Failed to respond" in m for m in messages_logged)
        assert any("Failed to send error reply" in m for m in messages_logged)

    @pytest.mark.asyncio
    async def test_error_fallback_when_generate_response_raises(self):
        """When _generate_response raises, the error fallback reply is attempted."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot_user = bot.user

        message = _make_message(mentions=[bot_user])
        message.reply = AsyncMock(side_effect=RuntimeError("still broken"))

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        # Agent always fails — triggers _generate_response to raise
        bot.agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.asyncio.sleep", new_callable=AsyncMock),
            patch("chat.bot.logger") as mock_logger,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            # Must not raise
            await bot.on_message(message)

        # The error fallback reply was attempted (and also failed)
        assert message.reply.call_count >= 1
        # Both failures logged
        exception_calls = mock_logger.exception.call_args_list
        messages_logged = [c.args[0] for c in exception_calls]
        assert any("Failed to respond" in m for m in messages_logged)
        assert any("Failed to send error reply" in m for m in messages_logged)
