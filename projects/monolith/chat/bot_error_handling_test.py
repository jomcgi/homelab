"""Tests for retry and separated error-handling paths in bot.py.

Covers gaps introduced by:
  734f3e2  feat(monolith): add LLM retry with exponential backoff and error reply
  c1e9722  fix(monolith): separate response and storage error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot, LLM_MAX_RETRIES, LLM_RETRY_BASE_DELAY


# ---------------------------------------------------------------------------
# Helpers (mirror bot_extra_test.py conventions)
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


# ---------------------------------------------------------------------------
# Test 1: error reply itself fails — both exceptions swallowed and logged
# ---------------------------------------------------------------------------


class TestErrorReplyFails:
    @pytest.mark.asyncio
    async def test_error_reply_failure_swallowed_and_both_exceptions_logged(self):
        """When _generate_response raises AND the error reply also raises,
        on_message swallows both without propagating and calls logger.exception
        once for the respond failure and once for the error-reply failure."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None
        # Every call to message.reply raises — normal reply AND error reply both fail.
        message.reply = AsyncMock(side_effect=RuntimeError("discord completely dead"))

        # _generate_response raises immediately (no real store/agent needed).
        bot._generate_response = AsyncMock(side_effect=RuntimeError("LLM down"))

        mock_store = MagicMock()
        mock_store.save_message = AsyncMock()

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

        # logger.exception should be called exactly twice:
        #   1. "Failed to respond to message …"
        #   2. "Failed to send error reply for message …"
        assert mock_logger.exception.call_count == 2
        first_fmt = mock_logger.exception.call_args_list[0][0][0]
        second_fmt = mock_logger.exception.call_args_list[1][0][0]
        assert "Failed to respond to message" in first_fmt
        assert "Failed to send error reply" in second_fmt


# ---------------------------------------------------------------------------
# Test 2: reply(response_text) failure triggers the sorry error reply
# ---------------------------------------------------------------------------


class TestReplyFailureTriggersErrorReply:
    @pytest.mark.asyncio
    async def test_reply_failure_triggers_sorry_message(self):
        """When message.reply(response_text) raises (not _generate_response),
        on_message catches it and sends the 'Sorry, I'm having trouble…' reply."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None
        # First call — reply(response_text) — raises.
        # Second call — reply("Sorry…") — succeeds.
        message.reply = AsyncMock(
            side_effect=[RuntimeError("rate limited"), MagicMock(id=101)]
        )

        # _generate_response succeeds; only message.reply fails.
        bot._generate_response = AsyncMock(return_value=("Here's my answer!", None))

        mock_store = MagicMock()
        mock_store.save_message = AsyncMock()

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

        # reply was called twice: first with the real response, then with the error message.
        assert message.reply.call_count == 2
        first_call_arg = message.reply.call_args_list[0][0][0]
        second_call_arg = message.reply.call_args_list[1][0][0]
        assert first_call_arg == "Here's my answer!"
        assert "trouble" in second_call_arg

    @pytest.mark.asyncio
    async def test_storage_failure_does_not_trigger_error_reply(self):
        """After a successful reply, a storage failure (c1e9722) must NOT trigger
        the 'Sorry…' error message — the user already received an answer."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None
        sent_msg = MagicMock(id=888)
        message.reply = AsyncMock(return_value=sent_msg)

        bot._generate_response = AsyncMock(return_value=("All good!", None))

        call_count = 0

        async def save_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("pgvector unavailable")

        mock_store = MagicMock()
        mock_store.save_message = AsyncMock(side_effect=save_side_effect)

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

        # reply was called exactly once — with the real response, not an error message.
        message.reply.assert_called_once_with("All good!")


# ---------------------------------------------------------------------------
# Test 3: Exponential backoff — verify asyncio.sleep delay values
# ---------------------------------------------------------------------------


class TestExponentialBackoffDelays:
    @pytest.mark.asyncio
    async def test_sleep_called_with_correct_backoff_delays(self):
        """_generate_response sleeps with delays LLM_RETRY_BASE_DELAY * 2^attempt.

        With LLM_MAX_RETRIES=3 and LLM_RETRY_BASE_DELAY=1.0:
          attempt 0 -> sleep(1.0)
          attempt 1 -> sleep(2.0)
          attempt 2 -> no sleep (last attempt, just raises)
        """
        bot = _make_bot()
        msg = _make_message(content="Hello?")
        bot.agent.run = AsyncMock(side_effect=RuntimeError("unavailable"))

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

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
            with pytest.raises(RuntimeError):
                await bot._generate_response(msg)

        # Sleep once between each consecutive attempt (not after the last one).
        assert mock_sleep.call_count == LLM_MAX_RETRIES - 1

        expected_delays = [
            LLM_RETRY_BASE_DELAY * (2**attempt)
            for attempt in range(LLM_MAX_RETRIES - 1)
        ]
        actual_delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert actual_delays == expected_delays, (
            f"Expected sleep delays {expected_delays}, got {actual_delays}"
        )


# ---------------------------------------------------------------------------
# Test 4: _generate_response unit-level retry — retries and re-raises last exc
# ---------------------------------------------------------------------------


class TestGenerateResponseRetry:
    @pytest.mark.asyncio
    async def test_retries_exactly_max_retries_times_and_raises_last_exception(self):
        """_generate_response calls agent.run LLM_MAX_RETRIES times then re-raises
        the last exception when every attempt fails."""
        bot = _make_bot()
        msg = _make_message(content="Retry me!")

        # Construct LLM_MAX_RETRIES distinct errors so we can check the last one.
        errors = [RuntimeError(f"attempt {i + 1}") for i in range(LLM_MAX_RETRIES)]
        bot.agent.run = AsyncMock(side_effect=errors)

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

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
            with pytest.raises(RuntimeError, match=f"attempt {LLM_MAX_RETRIES}"):
                await bot._generate_response(msg)

        # agent.run must be called exactly LLM_MAX_RETRIES times — no more, no fewer.
        assert bot.agent.run.call_count == LLM_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_succeeds_on_first_retry(self):
        """_generate_response returns the successful output when a retry succeeds."""
        bot = _make_bot()
        msg = _make_message(content="Will retry once.")

        mock_result = MagicMock()
        mock_result.output = "Recovered!"
        # First attempt fails, second succeeds.
        bot.agent.run = AsyncMock(side_effect=[RuntimeError("transient"), mock_result])

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

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
            result = await bot._generate_response(msg)

        assert result == ("Recovered!", None)
        assert bot.agent.run.call_count == 2
