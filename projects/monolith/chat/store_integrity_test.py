"""Tests for MessageStore.save_message() -- IntegrityError / duplicate handling.

After the save_messages() refactor, duplicates are caught per-message inside
savepoints (begin_nested).  When flush() raises IntegrityError inside a
savepoint the nested transaction is rolled back, the message is counted as
skipped, and processing continues with the next message.

These tests use a MagicMock session to inject IntegrityError at flush() and
verify the savepoint rollback logic.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from chat.store import MessageStore


@pytest.fixture
def mock_nested():
    """A MagicMock that behaves as a savepoint context manager."""
    nested = MagicMock()
    nested.__enter__ = MagicMock(return_value=nested)
    nested.__exit__ = MagicMock(return_value=False)
    return nested


@pytest.fixture
def mock_session(mock_nested):
    session = MagicMock()
    session.begin_nested.return_value = mock_nested
    return session


@pytest.fixture
def store(mock_session):
    embed_client = AsyncMock()
    embed_client.embed_batch.return_value = [[0.0] * 1024]
    return MessageStore(session=mock_session, embed_client=embed_client)


class TestSaveMessageIntegrityError:
    @pytest.mark.asyncio
    async def test_returns_none_on_integrity_error(self, store, mock_session):
        """save_message returns None when flush raises IntegrityError (duplicate id)."""
        mock_session.flush.side_effect = IntegrityError(
            statement="INSERT ...",
            params={},
            orig=Exception(
                "UNIQUE constraint failed: chat.messages.discord_message_id"
            ),
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
    async def test_rolls_back_savepoint_on_integrity_error(
        self, store, mock_session, mock_nested
    ):
        """save_message rolls back the savepoint when IntegrityError is raised."""
        mock_session.flush.side_effect = IntegrityError(
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

        mock_nested.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_skipped_count_incremented_on_integrity_error(
        self, store, mock_session
    ):
        """save_messages reports skipped=1 when one message hits IntegrityError."""
        mock_session.flush.side_effect = IntegrityError(
            statement="INSERT ...",
            params={},
            orig=Exception("UNIQUE constraint failed"),
        )

        result = await store.save_messages(
            [
                {
                    "discord_message_id": "dup-789",
                    "channel_id": "ch1",
                    "user_id": "u1",
                    "username": "Carol",
                    "content": "Another duplicate",
                    "is_bot": False,
                }
            ]
        )

        assert result.stored == 0
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_successful_save_commits_savepoint(
        self, store, mock_session, mock_nested
    ):
        """save_message commits the savepoint when there is no IntegrityError."""
        # No side_effect on flush -- it succeeds
        mock_session.exec.return_value.first.return_value = MagicMock(
            discord_message_id="unique-999"
        )

        await store.save_message(
            discord_message_id="unique-999",
            channel_id="ch1",
            user_id="u1",
            username="Dave",
            content="New message",
            is_bot=False,
        )

        mock_nested.commit.assert_called_once()
        mock_nested.rollback.assert_not_called()
