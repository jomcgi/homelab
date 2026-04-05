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
