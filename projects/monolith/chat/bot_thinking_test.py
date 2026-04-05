"""Tests for thinking mode handling in the Discord bot."""

import pytest

from chat.bot import _parse_thinking


class TestParseThinking:
    def test_no_thinking_tags(self):
        """Plain text without <think> tags passes through unchanged."""
        response, thinking = _parse_thinking("Hello world!")
        assert response == "Hello world!"
        assert thinking is None

    def test_thinking_and_response(self):
        """Extracts thinking and returns clean response."""
        text = "<think>I should greet them.</think>Hello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking == "I should greet them."

    def test_thinking_with_whitespace(self):
        """Strips whitespace between thinking block and response."""
        text = "<think>reasoning</think>\n\nHello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking == "reasoning"

    def test_thinking_only_empty_response(self):
        """Returns empty response when model only produces thinking."""
        text = "<think>I'm just thinking here.</think>"
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "I'm just thinking here."

    def test_thinking_only_whitespace_response(self):
        """Whitespace-only response after thinking is treated as empty."""
        text = "<think>reasoning</think>   \n  "
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "reasoning"

    def test_multiple_think_blocks(self):
        """Multiple <think> blocks are concatenated."""
        text = "<think>first</think>middle<think>second</think>end"
        response, thinking = _parse_thinking(text)
        assert response == "middleend"
        assert thinking == "first\n\nsecond"

    def test_unclosed_think_tag(self):
        """Unclosed <think> tag — treat entire remainder as thinking."""
        text = "<think>no closing tag here"
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "no closing tag here"

    def test_empty_think_block(self):
        """Empty <think></think> produces no thinking text."""
        text = "<think></think>Hello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking is None


from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from chat.bot import _summarize_thinking


class TestSummarizeThinking:
    @pytest.mark.asyncio
    async def test_short_thinking_returned_as_is(self):
        """Thinking under 2000 chars is not summarized."""
        result = await _summarize_thinking(
            "short reasoning", base_url="http://fake:8080"
        )
        assert result == "short reasoning"

    @pytest.mark.asyncio
    async def test_long_thinking_calls_llm(self):
        """Thinking over 2000 chars triggers an LLM summarization call."""
        long_text = "x" * 2001
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "summarized"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_text, base_url="http://fake:8080")

        assert result == "summarized"
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_llm_failure_truncates(self):
        """If summarization LLM call fails, truncate to 1990 chars."""
        long_text = "x" * 2500

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_text, base_url="http://fake:8080")

        assert len(result) <= 2000
        assert result.endswith("... (truncated)")
