"""Extra edge-case tests for _extract_thinking() in chat/bot.py.

The existing bot_thinking_test.py covers the primary paths (no thinking,
single ThinkingPart, empty/whitespace content, None content, multiple parts
across one or many ModelResponse objects).

These tests cover the remaining edge cases:

- Content with leading/trailing whitespace is stripped before joining
- A ThinkingPart with content=" " (single space) is treated as empty
- A ThinkingPart with content="\t\n" is treated as empty
- All ThinkingParts having None content returns None
- Mixed None-content and whitespace-only parts are all filtered out
- An empty new_messages() list returns None
- A ModelResponse whose only parts are TextPart objects returns None
- Stripping preserves internal whitespace (multiline content)
"""

from unittest.mock import MagicMock

from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart

from chat.bot import _extract_thinking


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result_from_parts(parts) -> MagicMock:
    """Build a mock agent result with a single ModelResponse containing parts."""
    response = ModelResponse(parts=parts)
    result = MagicMock()
    result.new_messages.return_value = [response]
    return result


def _make_result_empty_messages() -> MagicMock:
    """Build a mock agent result where new_messages() returns an empty list."""
    result = MagicMock()
    result.new_messages.return_value = []
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractThinkingExtra:
    def test_leading_trailing_whitespace_stripped_from_single_part(self):
        """Content with surrounding whitespace is stripped before returning."""
        result = _make_result_from_parts(
            [ThinkingPart(content="  stripped reasoning  "), TextPart(content="Hi")]
        )
        assert _extract_thinking(result) == "stripped reasoning"

    def test_leading_trailing_whitespace_stripped_before_joining(self):
        """Both parts have leading/trailing whitespace stripped before concatenation."""
        result = _make_result_from_parts(
            [
                ThinkingPart(content="  first thought  "),
                ThinkingPart(content="  second thought  "),
                TextPart(content="Hi"),
            ]
        )
        assert _extract_thinking(result) == "first thought\n\nsecond thought"

    def test_internal_whitespace_preserved(self):
        """Internal newlines and spaces within a ThinkingPart are preserved."""
        multiline = "Step 1: analyse\n\nStep 2: conclude"
        result = _make_result_from_parts(
            [ThinkingPart(content=multiline), TextPart(content="Hi")]
        )
        assert _extract_thinking(result) == multiline

    def test_single_space_content_returns_none(self):
        """A ThinkingPart with content=' ' (single space) is treated as empty → None."""
        result = _make_result_from_parts(
            [ThinkingPart(content=" "), TextPart(content="Hi")]
        )
        assert _extract_thinking(result) is None

    def test_tab_only_content_returns_none(self):
        """A ThinkingPart with content='\t' is whitespace-only → None."""
        result = _make_result_from_parts(
            [ThinkingPart(content="\t"), TextPart(content="Hi")]
        )
        assert _extract_thinking(result) is None

    def test_mixed_tabs_and_newlines_returns_none(self):
        """Tabs and newlines without real content are whitespace-only → None."""
        result = _make_result_from_parts(
            [ThinkingPart(content="\t\n\r\n"), TextPart(content="Hi")]
        )
        assert _extract_thinking(result) is None

    def test_all_thinking_parts_have_none_content(self):
        """When every ThinkingPart has content=None, returns None."""
        result = _make_result_from_parts(
            [
                ThinkingPart(content=None),
                ThinkingPart(content=None),
                TextPart(content="Hi"),
            ]
        )
        assert _extract_thinking(result) is None

    def test_mixture_of_none_and_whitespace_returns_none(self):
        """ThinkingParts with None or whitespace-only content are all filtered out."""
        result = _make_result_from_parts(
            [
                ThinkingPart(content=None),
                ThinkingPart(content="  "),
                ThinkingPart(content="\t"),
                TextPart(content="Hi"),
            ]
        )
        assert _extract_thinking(result) is None

    def test_valid_content_mixed_with_none_and_whitespace(self):
        """Only non-empty, non-whitespace ThinkingParts are included."""
        result = _make_result_from_parts(
            [
                ThinkingPart(content=None),
                ThinkingPart(content="  real thinking  "),
                ThinkingPart(content="\t\n"),
                TextPart(content="Hi"),
            ]
        )
        assert _extract_thinking(result) == "real thinking"

    def test_empty_messages_list_returns_none(self):
        """When new_messages() returns an empty list, returns None."""
        result = _make_result_empty_messages()
        assert _extract_thinking(result) is None

    def test_model_response_with_only_text_parts_returns_none(self):
        """A ModelResponse containing only TextPart objects returns None."""
        result = _make_result_from_parts(
            [TextPart(content="Hello"), TextPart(content="World")]
        )
        assert _extract_thinking(result) is None

    def test_model_response_with_single_text_part_returns_none(self):
        """A ModelResponse with exactly one TextPart and no ThinkingParts returns None."""
        result = _make_result_from_parts([TextPart(content="Only text here")])
        assert _extract_thinking(result) is None

    def test_stripped_content_is_what_gets_joined(self):
        """The separator \n\n is inserted between stripped (not raw) content strings."""
        result = _make_result_from_parts(
            [
                ThinkingPart(content="  part one  "),
                ThinkingPart(content="  part two  "),
            ]
        )
        thinking = _extract_thinking(result)
        # The join separator sits between the stripped strings
        assert thinking == "part one\n\npart two"
        # The raw whitespace should not appear at the boundary
        assert "  \n\n" not in thinking
