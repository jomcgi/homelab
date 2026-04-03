"""Tests for chat SQLModel definitions."""

import pytest
from sqlmodel import SQLModel

from chat.models import Message


class TestMessageModel:
    def test_message_table_name(self):
        """Message model maps to chat.messages table."""
        assert Message.__tablename__ == "messages"
        assert Message.__table_args__["schema"] == "chat"

    def test_message_has_required_fields(self):
        """Message model has all expected columns."""
        columns = {c.name for c in Message.__table__.columns}
        expected = {
            "id",
            "discord_message_id",
            "channel_id",
            "user_id",
            "username",
            "content",
            "is_bot",
            "embedding",
            "created_at",
        }
        assert expected == columns

    def test_message_is_bot_defaults_false(self):
        """is_bot field defaults to False."""
        msg = Message(
            discord_message_id="123",
            channel_id="456",
            user_id="789",
            username="test",
            content="hello",
            embedding=[0.0] * 512,
        )
        assert msg.is_bot is False
