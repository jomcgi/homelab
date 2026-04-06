"""Tests for _summarize_thinking() when the LLM returns an oversized summary.

Covers the branch:
    if len(summary) > DISCORD_MESSAGE_LIMIT:
        return summary[:THINKING_TRUNCATE_AT] + "... (truncated)"

This path is distinct from the error/fallback truncation tested in
bot_thinking_test.py: here the LLM *succeeds* but its output still exceeds
Discord's message limit, so the result must be truncated.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import DISCORD_MESSAGE_LIMIT, THINKING_TRUNCATE_AT, _summarize_thinking


class TestSummarizeThinkingOversizedSummary:
    @pytest.mark.asyncio
    async def test_oversized_llm_summary_is_truncated_to_thinking_truncate_at(self):
        """When LLM returns a summary longer than DISCORD_MESSAGE_LIMIT,
        the result is truncated to THINKING_TRUNCATE_AT + '... (truncated)'."""
        long_input = "x" * 2500  # must exceed DISCORD_MESSAGE_LIMIT to trigger LLM call

        oversized_summary = "y" * (DISCORD_MESSAGE_LIMIT + 100)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": oversized_summary}}]
        }

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        expected = oversized_summary[:THINKING_TRUNCATE_AT] + "... (truncated)"
        assert result == expected

    @pytest.mark.asyncio
    async def test_truncated_result_fits_within_discord_limit(self):
        """The truncated summary must never exceed DISCORD_MESSAGE_LIMIT."""
        long_input = "x" * 5000

        very_long_summary = "a" * 10000
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": very_long_summary}}]
        }

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        assert len(result) <= DISCORD_MESSAGE_LIMIT
        assert result.endswith("... (truncated)")

    @pytest.mark.asyncio
    async def test_summary_exactly_at_discord_limit_is_not_truncated(self):
        """A summary of exactly DISCORD_MESSAGE_LIMIT chars is returned as-is.

        The condition is strictly > DISCORD_MESSAGE_LIMIT, so the boundary
        value must NOT trigger truncation.
        """
        long_input = "x" * 2500

        exact_summary = "z" * DISCORD_MESSAGE_LIMIT
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": exact_summary}}]
        }

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        assert result == exact_summary
        assert not result.endswith("... (truncated)")

    @pytest.mark.asyncio
    async def test_oversized_summary_starts_with_thinking_truncate_at_prefix(self):
        """Truncated summary keeps the first THINKING_TRUNCATE_AT chars of the LLM output."""
        long_input = "x" * 2500

        # Use a distinctive pattern so we can verify the prefix exactly
        oversized_summary = "AB" * (DISCORD_MESSAGE_LIMIT + 50)  # alternating chars
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": oversized_summary}}]
        }

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        assert result.startswith(oversized_summary[:THINKING_TRUNCATE_AT])
        assert result == oversized_summary[:THINKING_TRUNCATE_AT] + "... (truncated)"

    @pytest.mark.asyncio
    async def test_thinking_truncate_at_is_strictly_less_than_discord_limit(self):
        """Sanity-check: THINKING_TRUNCATE_AT + len('... (truncated)') <= DISCORD_MESSAGE_LIMIT."""
        suffix = "... (truncated)"
        assert THINKING_TRUNCATE_AT + len(suffix) <= DISCORD_MESSAGE_LIMIT
