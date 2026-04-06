"""Tests for MessageStore.find_user_id_by_username()."""

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
    embed_client.embed_batch.return_value = [[0.0] * 1024]
    return MessageStore(session=session, embed_client=embed_client)


class TestFindUserIdByUsername:
    @pytest.mark.asyncio
    async def test_returns_user_id_when_found(self, store):
        """find_user_id_by_username returns the user_id for a known username."""
        await store.save_message(
            discord_message_id="101",
            channel_id="ch1",
            user_id="user-abc",
            username="alice",
            content="Hello!",
            is_bot=False,
        )
        result = store.find_user_id_by_username("ch1", "alice")
        assert result == "user-abc"

    def test_returns_none_when_not_found(self, store):
        """find_user_id_by_username returns None when no message has that username."""
        result = store.find_user_id_by_username("ch1", "nobody")
        assert result is None

    def test_returns_none_for_empty_channel(self, store):
        """find_user_id_by_username returns None for a channel with no messages."""
        result = store.find_user_id_by_username("empty-channel", "anyone")
        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_channel_id(self, store):
        """find_user_id_by_username only looks in the given channel."""
        await store.save_message(
            discord_message_id="201",
            channel_id="ch1",
            user_id="user-in-ch1",
            username="bob",
            content="Hi from ch1",
            is_bot=False,
        )
        await store.save_message(
            discord_message_id="202",
            channel_id="ch2",
            user_id="user-in-ch2",
            username="bob",
            content="Hi from ch2",
            is_bot=False,
        )
        result_ch1 = store.find_user_id_by_username("ch1", "bob")
        assert result_ch1 == "user-in-ch1"

        result_ch2 = store.find_user_id_by_username("ch2", "bob")
        assert result_ch2 == "user-in-ch2"

    @pytest.mark.asyncio
    async def test_username_in_ch2_not_found_in_ch1(self, store):
        """A username that only exists in ch2 is not found when searching ch1."""
        await store.save_message(
            discord_message_id="203",
            channel_id="ch2",
            user_id="user-only-ch2",
            username="dave",
            content="Hi",
            is_bot=False,
        )
        result = store.find_user_id_by_username("ch1", "dave")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_most_recent_user_id_for_username(self, store):
        """When a username appears in multiple messages, the most recent user_id is returned."""
        await store.save_message(
            discord_message_id="301",
            channel_id="ch1",
            user_id="user-old",
            username="charlie",
            content="First message",
            is_bot=False,
        )
        # Simulate a second message from the same username (possibly different user_id)
        store.embed_client.embed_batch.return_value = [[0.1] * 1024]
        await store.save_message(
            discord_message_id="302",
            channel_id="ch1",
            user_id="user-new",
            username="charlie",
            content="Second message",
            is_bot=False,
        )
        result = store.find_user_id_by_username("ch1", "charlie")
        # The most recent message (302) has user-new
        assert result == "user-new"

    @pytest.mark.asyncio
    async def test_does_not_match_different_username(self, store):
        """find_user_id_by_username does not return results for a different username."""
        await store.save_message(
            discord_message_id="401",
            channel_id="ch1",
            user_id="user-eve",
            username="eve",
            content="Hi there",
            is_bot=False,
        )
        result = store.find_user_id_by_username("ch1", "frank")
        assert result is None
