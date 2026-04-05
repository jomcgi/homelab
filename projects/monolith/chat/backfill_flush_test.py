"""Tests for _flush_batch helper in chat backfill."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.backfill import _flush_batch
from chat.store import SaveResult


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
async def test_flush_batch_delegates_to_store(mock_store_cls, mock_session, mock_engine):
    """_flush_batch creates a Session+MessageStore and calls save_messages with the batch."""
    expected_result = SaveResult(stored=3, skipped=1)
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(return_value=expected_result)
    mock_store_cls.return_value = mock_store_instance

    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=session_ctx)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mock_session.return_value = session_ctx

    embed_client = MagicMock()
    batch = [
        {"discord_message_id": "1", "content": "hello"},
        {"discord_message_id": "2", "content": "world"},
        {"discord_message_id": "3", "content": "foo"},
    ]

    result = await _flush_batch(batch, embed_client)

    assert result is expected_result
    mock_engine.assert_called_once()
    mock_session.assert_called_once_with(mock_engine.return_value)
    mock_store_cls.assert_called_once_with(session=session_ctx, embed_client=embed_client)
    mock_store_instance.save_messages.assert_called_once_with(batch)


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
async def test_flush_batch_handles_empty_batch(mock_store_cls, mock_session, mock_engine):
    """_flush_batch with an empty list still calls save_messages and returns its result."""
    expected_result = SaveResult(stored=0, skipped=0)
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(return_value=expected_result)
    mock_store_cls.return_value = mock_store_instance

    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=session_ctx)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mock_session.return_value = session_ctx

    embed_client = MagicMock()

    result = await _flush_batch([], embed_client)

    assert result is expected_result
    mock_store_instance.save_messages.assert_called_once_with([])
