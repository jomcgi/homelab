"""Tests for agent helper functions: build_system_prompt and format_context_messages.

Covers gaps not addressed by existing test files:
- build_system_prompt: exact tool descriptions, conciseness guidance, tool usage prompt
- format_context_messages: timestamp format, bot "Assistant" label, multiple messages,
  multiple attachments per message, missing message id in attachment map
"""

from datetime import datetime, timezone

from chat.agent import build_system_prompt, format_context_messages
from chat.models import Attachment, Blob, Message


def _make_message(
    *,
    id: int = 1,
    username: str = "Alice",
    content: str = "hello",
    is_bot: bool = False,
    created_at: datetime | None = None,
) -> Message:
    """Convenience factory for Message objects used in tests."""
    if created_at is None:
        created_at = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    return Message(
        id=id,
        discord_message_id=str(id),
        channel_id="ch1",
        user_id="u1",
        username=username,
        content=content,
        is_bot=is_bot,
        embedding=[0.0] * 1024,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# build_system_prompt — return type
# ---------------------------------------------------------------------------


class TestBuildSystemPromptReturnType:
    def test_returns_string(self):
        """build_system_prompt() returns a str instance."""
        result = build_system_prompt()
        assert isinstance(result, str)

    def test_returns_non_empty_string(self):
        """build_system_prompt() returns a non-empty string."""
        result = build_system_prompt()
        assert len(result) > 0


# ---------------------------------------------------------------------------
# build_system_prompt — content: tool descriptions
# ---------------------------------------------------------------------------


class TestBuildSystemPromptToolDescriptions:
    def test_includes_web_search_tool_name(self):
        """System prompt mentions the web_search tool by name."""
        prompt = build_system_prompt()
        assert "web_search" in prompt

    def test_includes_search_history_tool_name(self):
        """System prompt mentions the search_history tool by name."""
        prompt = build_system_prompt()
        assert "search_history" in prompt

    def test_includes_get_user_summary_tool_name(self):
        """System prompt mentions the get_user_summary tool by name."""
        prompt = build_system_prompt()
        assert "get_user_summary" in prompt

    def test_web_search_described_for_current_information(self):
        """web_search description indicates it retrieves current/up-to-date information."""
        prompt = build_system_prompt()
        # The prompt says "Look up current information from the web"
        assert "current" in prompt

    def test_search_history_described_for_older_messages(self):
        """search_history description references older messages in the channel."""
        prompt = build_system_prompt()
        assert "older" in prompt

    def test_search_history_mentions_username_filter(self):
        """search_history description notes it can filter by username."""
        prompt = build_system_prompt()
        assert "username" in prompt

    def test_get_user_summary_describes_list_all_users(self):
        """get_user_summary description says call with no username to list all users."""
        prompt = build_system_prompt()
        assert "no username" in prompt


# ---------------------------------------------------------------------------
# build_system_prompt — content: guidance phrases
# ---------------------------------------------------------------------------


class TestBuildSystemPromptGuidance:
    def test_includes_discord_chat_context(self):
        """System prompt identifies the agent as a Discord chat assistant."""
        prompt = build_system_prompt()
        assert "Discord" in prompt

    def test_instructs_concise_responses(self):
        """System prompt instructs the model to keep responses concise."""
        prompt = build_system_prompt()
        assert "concise" in prompt

    def test_instructs_use_tools_before_claiming_no_context(self):
        """System prompt tells the agent to use tools before saying it lacks context."""
        prompt = build_system_prompt()
        assert "Use your tools" in prompt

    def test_mentions_recent_conversation_history(self):
        """System prompt notes the agent can see recent conversation history."""
        prompt = build_system_prompt()
        assert "recent" in prompt


# ---------------------------------------------------------------------------
# format_context_messages — timestamp format
# ---------------------------------------------------------------------------


class TestFormatContextMessagesTimestamp:
    def test_timestamp_uses_year_month_day_hour_minute_format(self):
        """Timestamps appear as [YYYY-MM-DD HH:MM] in the output."""
        msg = _make_message(
            created_at=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
        )
        result = format_context_messages([msg])
        assert "[2026-04-01 14:30]" in result

    def test_timestamp_is_zero_padded(self):
        """Single-digit month, day, hour, and minute values are zero-padded."""
        msg = _make_message(
            created_at=datetime(2026, 1, 5, 8, 5, tzinfo=timezone.utc),
        )
        result = format_context_messages([msg])
        assert "[2026-01-05 08:05]" in result


# ---------------------------------------------------------------------------
# format_context_messages — bot vs user label
# ---------------------------------------------------------------------------


class TestFormatContextMessagesBotLabel:
    def test_bot_message_uses_assistant_label_not_username(self):
        """Bot messages are prefixed with 'Assistant:' not the bot's username."""
        msg = _make_message(username="SomeBot", content="Beep boop", is_bot=True)
        result = format_context_messages([msg])
        assert "Assistant:" in result
        assert "SomeBot:" not in result

    def test_user_message_uses_actual_username(self):
        """User messages are prefixed with the actual username followed by a colon."""
        msg = _make_message(username="charlie", content="hey there", is_bot=False)
        result = format_context_messages([msg])
        assert "charlie:" in result
        assert "Assistant:" not in result

    def test_bot_message_content_is_included(self):
        """The content of a bot message is present in the output."""
        msg = _make_message(username="bot", content="I can help", is_bot=True)
        result = format_context_messages([msg])
        assert "I can help" in result


# ---------------------------------------------------------------------------
# format_context_messages — multiple messages
# ---------------------------------------------------------------------------


class TestFormatContextMessagesMultiple:
    def test_two_messages_produce_two_lines(self):
        """Two messages produce exactly two newline-separated lines."""
        msg1 = _make_message(
            id=1,
            username="Alice",
            content="first",
            created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        )
        msg2 = _make_message(
            id=2,
            username="Bob",
            content="second",
            created_at=datetime(2026, 4, 1, 12, 1, tzinfo=timezone.utc),
        )
        result = format_context_messages([msg1, msg2])
        lines = result.split("\n")
        assert len(lines) == 2

    def test_message_ordering_is_preserved(self):
        """Messages appear in the order provided to format_context_messages."""
        msg1 = _make_message(id=1, username="First", content="alpha")
        msg2 = _make_message(id=2, username="Second", content="beta")
        result = format_context_messages([msg1, msg2])
        first_pos = result.index("First")
        second_pos = result.index("Second")
        assert first_pos < second_pos

    def test_mixed_bot_and_user_messages(self):
        """Bot and user messages in the same list are formatted with correct labels."""
        user_msg = _make_message(id=1, username="dave", content="question", is_bot=False)
        bot_msg = _make_message(id=2, username="bot", content="answer", is_bot=True)
        result = format_context_messages([user_msg, bot_msg])
        assert "dave: question" in result
        assert "Assistant: answer" in result


# ---------------------------------------------------------------------------
# format_context_messages — attachments
# ---------------------------------------------------------------------------


class TestFormatContextMessagesAttachments:
    def test_multiple_attachments_per_message_all_appear(self):
        """All image descriptions from multiple attachments for one message are included."""
        msg = _make_message(id=5, content="look at these")
        attachments_map = {
            5: [
                (
                    Attachment(id=1, message_id=5, blob_sha256="aaa", filename="a.png"),
                    Blob(sha256="aaa", data=b"", content_type="image/png", description="A dog"),
                ),
                (
                    Attachment(id=2, message_id=5, blob_sha256="bbb", filename="b.png"),
                    Blob(sha256="bbb", data=b"", content_type="image/png", description="A cat"),
                ),
            ]
        }
        result = format_context_messages([msg], attachments_map)
        assert "[Image: A dog]" in result
        assert "[Image: A cat]" in result

    def test_no_image_line_when_message_id_absent_from_map(self):
        """No image annotation is added when the message id is not in the attachments map."""
        msg = _make_message(id=10, content="plain message")
        attachments_map = {99: []}  # different message id
        result = format_context_messages([msg], attachments_map)
        assert "[Image:" not in result

    def test_none_attachments_map_produces_no_image_lines(self):
        """Passing attachments_by_msg=None does not raise and adds no image annotations."""
        msg = _make_message(id=3, content="no pics here")
        result = format_context_messages([msg], None)
        assert "[Image:" not in result
        assert "no pics here" in result

    def test_attachment_image_line_uses_indented_format(self):
        """Image descriptions are prefixed with two spaces and the [Image:] marker."""
        msg = _make_message(id=7, content="see this")
        attachments_map = {
            7: [
                (
                    Attachment(id=1, message_id=7, blob_sha256="ccc", filename="c.png"),
                    Blob(sha256="ccc", data=b"", content_type="image/png", description="Sunset"),
                ),
            ]
        }
        result = format_context_messages([msg], attachments_map)
        assert "  [Image: Sunset]" in result
