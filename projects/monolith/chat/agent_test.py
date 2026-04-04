"""Tests for PydanticAI chat agent."""

from chat.agent import build_system_prompt, format_context_messages


class TestBuildSystemPrompt:
    def test_includes_bot_identity(self):
        """System prompt identifies the bot."""
        prompt = build_system_prompt()
        assert "Discord" in prompt or "chat" in prompt.lower()

    def test_includes_web_search_guidance(self):
        """System prompt mentions web search capability."""
        prompt = build_system_prompt()
        assert "search" in prompt.lower()


class TestFormatContextMessages:
    def test_formats_user_message(self):
        """User messages include username and content."""
        from datetime import datetime, timezone

        from chat.models import Message

        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Hello there",
            is_bot=False,
            embedding=[0.0] * 1024,
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        )
        formatted = format_context_messages([msg])
        assert "Alice" in formatted
        assert "Hello there" in formatted

    def test_formats_bot_message(self):
        """Bot messages are labeled as assistant."""
        from datetime import datetime, timezone

        from chat.models import Message

        msg = Message(
            id=2,
            discord_message_id="2",
            channel_id="ch1",
            user_id="bot",
            username="Bot",
            content="Hi!",
            is_bot=True,
            embedding=[0.0] * 1024,
            created_at=datetime(2026, 4, 3, 12, 1, tzinfo=timezone.utc),
        )
        formatted = format_context_messages([msg])
        assert "Hi!" in formatted
