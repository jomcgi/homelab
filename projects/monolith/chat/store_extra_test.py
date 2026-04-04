"""Extra coverage for store.py -- get_recent() with an empty channel."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.store import MessageStore


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session (schema-stripped for SQLite compat)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


@pytest.fixture
def store(session):
    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.0] * 512
    return MessageStore(session=session, embed_client=embed_client)


class TestGetRecentEmptyChannel:
    def test_returns_empty_list_for_channel_with_no_messages(self, store):
        """get_recent() returns [] when no messages exist for the given channel."""
        result = store.get_recent("channel-with-no-messages", limit=20)
        assert result == []

    def test_returns_empty_list_for_nonexistent_channel(self, store):
        """get_recent() returns [] for a channel ID that has never received a message."""
        result = store.get_recent("nonexistent-channel-xyz", limit=5)
        assert isinstance(result, list)
        assert len(result) == 0
