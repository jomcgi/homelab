"""Tests for MessageStore.save_message() -- IntegrityError / duplicate handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from chat.store import MessageStore


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def store(mock_session):
    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.0] * 1024
    return MessageStore(session=mock_session, embed_client=embed_client)


class TestSaveMessageIntegrityError:
    @pytest.mark.asyncio
    async def test_returns_none_on_integrity_error(self, store, mock_session):
        """save_message returns None when commit raises IntegrityError (duplicate id)."""
        mock_session.commit.side_effect = IntegrityError(
            statement="INSERT ...",
            params={},
            orig=Exception("UNIQUE constraint failed: chat.messages.discord_message_id"),
        )

        result = await store.save_message(
            discord_message_id="dup-123",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Hello again",
            is_bot=False,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_rolls_back_session_on_integrity_error(self, store, mock_session):
        """save_message calls session.rollback() when IntegrityError is raised."""
        mock_session.commit.side_effect = IntegrityError(
            statement="INSERT ...",
            params={},
            orig=Exception("UNIQUE constraint failed"),
        )

        await store.save_message(
            discord_message_id="dup-456",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="Duplicate message",
            is_bot=False,
        )

        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_call_refresh_on_integrity_error(self, store, mock_session):
        """save_message does not call session.refresh() when IntegrityError is raised."""
        mock_session.commit.side_effect = IntegrityError(
            statement="INSERT ...",
            params={},
            orig=Exception("UNIQUE constraint failed"),
        )

        await store.save_message(
            discord_message_id="dup-789",
            channel_id="ch1",
            user_id="u1",
            username="Carol",
            content="Another duplicate",
            is_bot=False,
        )

        mock_session.refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_message_on_successful_save(self, store, mock_session):
        """save_message returns the Message object when there is no IntegrityError."""
        from chat.models import Message

        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None

        result = await store.save_message(
            discord_message_id="unique-999",
            channel_id="ch1",
            user_id="u1",
            username="Dave",
            content="New message",
            is_bot=False,
        )

        assert isinstance(result, Message)
        assert result.discord_message_id == "unique-999"
        assert result.content == "New message"
        mock_session.rollback.assert_not_called()
