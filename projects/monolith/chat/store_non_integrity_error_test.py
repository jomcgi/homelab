"""Tests for MessageStore.save_message() -- non-IntegrityError exception propagation.

store_integrity_test.py covers the IntegrityError / duplicate-key path.
These tests cover the orthogonal case: when the session raises an exception that
is NOT an IntegrityError (e.g. OperationalError on a lost DB connection), the
exception must propagate to the caller unchanged.  No rollback is expected for
these exceptions — the caller's own error handler is responsible for clean-up.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from chat.store import MessageStore


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def store(mock_session):
    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.0] * 1024
    return MessageStore(session=mock_session, embed_client=embed_client)


class TestSaveMessageNonIntegrityError:
    @pytest.mark.asyncio
    async def test_propagates_operational_error_from_commit(self, store, mock_session):
        """save_message propagates OperationalError raised by session.commit()."""
        mock_session.commit.side_effect = OperationalError(
            statement="INSERT ...",
            params={},
            orig=Exception("connection closed"),
        )

        with pytest.raises(OperationalError):
            await store.save_message(
                discord_message_id="op-err-1",
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                content="Hello",
                is_bot=False,
            )

    @pytest.mark.asyncio
    async def test_propagates_runtime_error_from_flush(self, store, mock_session):
        """save_message propagates RuntimeError raised by session.flush()."""
        mock_session.flush.side_effect = RuntimeError("unexpected db state")

        with pytest.raises(RuntimeError, match="unexpected db state"):
            await store.save_message(
                discord_message_id="rt-err-1",
                channel_id="ch1",
                user_id="u1",
                username="Bob",
                content="Test",
                is_bot=False,
            )

    @pytest.mark.asyncio
    async def test_does_not_rollback_on_operational_error(self, store, mock_session):
        """save_message does NOT call session.rollback() for non-IntegrityError.

        Only IntegrityError (duplicate-key) triggers a deliberate rollback.
        Other exceptions propagate without the store performing a rollback — the
        outer session context manager (or caller) handles cleanup.
        """
        mock_session.commit.side_effect = OperationalError(
            statement="INSERT ...",
            params={},
            orig=Exception("connection reset"),
        )

        with pytest.raises(OperationalError):
            await store.save_message(
                discord_message_id="op-err-2",
                channel_id="ch1",
                user_id="u1",
                username="Carol",
                content="Test",
                is_bot=False,
            )

        mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_exception_from_embed_client(self, store, mock_session):
        """save_message propagates exceptions raised by embed_client.embed()."""
        store.embed_client.embed.side_effect = RuntimeError("embedding service down")

        with pytest.raises(RuntimeError, match="embedding service down"):
            await store.save_message(
                discord_message_id="emb-err-1",
                channel_id="ch1",
                user_id="u1",
                username="Dave",
                content="Embed this",
                is_bot=False,
            )
