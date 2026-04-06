"""Tests for ChatBot.reprocess_message().

Covers the three outcomes:
  1. Channel not found → logs warning and returns without processing.
  2. Message deleted (discord.NotFound) → marks lock completed, returns.
  3. Happy path → calls _process_message with the fetched message.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from chat.bot import ChatBot


# ---------------------------------------------------------------------------
# Helpers (mirroring bot_session_failure_test.py conventions)
# ---------------------------------------------------------------------------


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals — never touches real services."""
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
# Tests
# ---------------------------------------------------------------------------


class TestReprocessMessage:
    @pytest.mark.asyncio
    async def test_channel_not_found_logs_warning_and_returns(self):
        """When get_channel returns None, a warning is logged and we return early."""
        bot = _make_bot()
        # get_channel is inherited from discord.Client; patch it on the instance
        bot.get_channel = MagicMock(return_value=None)

        with patch("chat.bot.logger") as mock_logger:
            await bot.reprocess_message("msg-42", "ch-99")

        mock_logger.warning.assert_called_once()
        warning_args = mock_logger.warning.call_args[0]
        assert "ch-99" in str(warning_args) or "msg-42" in str(warning_args)

    @pytest.mark.asyncio
    async def test_channel_not_found_does_not_call_process_message(self):
        """No _process_message call when the channel is missing."""
        bot = _make_bot()
        bot.get_channel = MagicMock(return_value=None)

        with patch.object(bot, "_process_message", new_callable=AsyncMock) as mock_pm:
            await bot.reprocess_message("msg-43", "ch-99")

        mock_pm.assert_not_called()

    @pytest.mark.asyncio
    async def test_message_deleted_marks_lock_completed(self):
        """When discord.NotFound is raised, the lock is marked completed."""
        bot = _make_bot()

        mock_channel = AsyncMock()
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(status=404), "Unknown Message")
        )
        bot.get_channel = MagicMock(return_value=mock_channel)

        mock_store = MagicMock()
        mock_session_instance = MagicMock()
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session", return_value=mock_session_instance),
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            await bot.reprocess_message("msg-deleted", "ch-1")

        mock_store.mark_completed.assert_called_once_with("msg-deleted")

    @pytest.mark.asyncio
    async def test_message_deleted_does_not_call_process_message(self):
        """No _process_message call when the message was deleted."""
        bot = _make_bot()

        mock_channel = AsyncMock()
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(status=404), "Unknown Message")
        )
        bot.get_channel = MagicMock(return_value=mock_channel)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session"),
            patch("chat.bot.MessageStore"),
            patch.object(bot, "_process_message", new_callable=AsyncMock) as mock_pm,
        ):
            await bot.reprocess_message("msg-deleted-2", "ch-1")

        mock_pm.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_calls_process_message(self):
        """Happy path: reprocess_message calls _process_message with the fetched message."""
        bot = _make_bot()

        fetched_message = MagicMock()
        mock_channel = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=fetched_message)
        bot.get_channel = MagicMock(return_value=mock_channel)

        with patch.object(bot, "_process_message", new_callable=AsyncMock) as mock_pm:
            await bot.reprocess_message("msg-ok", "ch-1")

        mock_pm.assert_called_once_with(fetched_message)

    @pytest.mark.asyncio
    async def test_http_exception_logs_and_returns(self):
        """discord.HTTPException (non-404) logs an exception and returns."""
        bot = _make_bot()

        mock_channel = AsyncMock()
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=500), "Server Error")
        )
        bot.get_channel = MagicMock(return_value=mock_channel)

        with (
            patch("chat.bot.logger") as mock_logger,
            patch.object(bot, "_process_message", new_callable=AsyncMock) as mock_pm,
        ):
            await bot.reprocess_message("msg-http-err", "ch-1")

        mock_logger.exception.assert_called_once()
        mock_pm.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_exception_does_not_mark_completed(self):
        """discord.HTTPException does NOT mark the lock completed (message may still exist)."""
        bot = _make_bot()

        mock_channel = AsyncMock()
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=503), "Unavailable")
        )
        bot.get_channel = MagicMock(return_value=mock_channel)

        mock_store = MagicMock()

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session"),
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            await bot.reprocess_message("msg-http-err-2", "ch-1")

        mock_store.mark_completed.assert_not_called()
