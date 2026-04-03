"""Tests for chat message store -- storage and recall."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Message
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


class TestSaveMessage:
    @pytest.mark.asyncio
    async def test_saves_message_to_db(self, store, session):
        """save_message persists a message to the database."""
        await store.save_message(
            discord_message_id="111",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Hello!",
            is_bot=False,
        )
        msgs = session.exec(select(Message)).all()
        assert len(msgs) == 1
        assert msgs[0].content == "Hello!"
        assert msgs[0].username == "Alice"

    @pytest.mark.asyncio
    async def test_calls_embed_client(self, store):
        """save_message calls the embedding client with the message content."""
        await store.save_message(
            discord_message_id="222",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="What is the weather?",
            is_bot=False,
        )
        store.embed_client.embed.assert_called_once_with("What is the weather?")


class TestGetRecentMessages:
    @pytest.mark.asyncio
    async def test_returns_recent_messages_in_order(self, store, session):
        """get_recent returns messages ordered oldest-first."""
        for i in range(5):
            await store.save_message(
                discord_message_id=str(i),
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                content=f"msg {i}",
                is_bot=False,
            )
        recent = store.get_recent("ch1", limit=3)
        assert len(recent) == 3
        assert recent[0].content == "msg 2"
        assert recent[2].content == "msg 4"

    @pytest.mark.asyncio
    async def test_filters_by_channel(self, store, session):
        """get_recent only returns messages from the specified channel."""
        await store.save_message("a", "ch1", "u1", "A", "in ch1", False)
        await store.save_message("b", "ch2", "u1", "A", "in ch2", False)
        recent = store.get_recent("ch1", limit=10)
        assert len(recent) == 1
        assert recent[0].content == "in ch1"
