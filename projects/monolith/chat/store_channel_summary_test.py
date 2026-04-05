"""Tests for MessageStore channel summary methods."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.models import ChannelSummary, Message, UserChannelSummary
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
    embed_client.embed.return_value = [0.0] * 1024
    return MessageStore(session=session, embed_client=embed_client)


class TestGetChannelSummary:
    def test_returns_none_when_not_exists(self, store):
        result = store.get_channel_summary("ch_unknown")
        assert result is None

    def test_returns_summary_when_exists(self, store, session):
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="hello",
            is_bot=False,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()
        session.add(
            ChannelSummary(
                channel_id="ch1",
                summary="This channel discusses deployments.",
                message_count=10,
                last_message_id=1,
            )
        )
        session.commit()
        result = store.get_channel_summary("ch1")
        assert result is not None
        assert "deployments" in result.summary
        assert result.message_count == 10


class TestUpsertChannelSummary:
    def test_inserts_new_summary(self, store, session):
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="hello",
            is_bot=False,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()
        store.upsert_channel_summary("ch1", "Channel about infra.", 1, 5)
        result = store.get_channel_summary("ch1")
        assert result is not None
        assert result.summary == "Channel about infra."
        assert result.message_count == 5

    def test_updates_existing_summary(self, store, session):
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="hello",
            is_bot=False,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()
        store.upsert_channel_summary("ch1", "First.", 1, 5)
        store.upsert_channel_summary("ch1", "Updated.", 1, 10)
        result = store.get_channel_summary("ch1")
        assert result.summary == "Updated."
        assert result.message_count == 10


class TestGetUserSummariesForUsers:
    def test_returns_matching_summaries(self, store, session):
        store.upsert_summary("ch1", "u1", "Alice", "Alice summary.", 10)
        store.upsert_summary("ch1", "u2", "Bob", "Bob summary.", 20)
        result = store.get_user_summaries_for_users("ch1", ["u1", "u2"])
        assert len(result) == 2
        usernames = {s.username for s in result}
        assert usernames == {"Alice", "Bob"}

    def test_ignores_missing_users(self, store, session):
        store.upsert_summary("ch1", "u1", "Alice", "Alice summary.", 10)
        result = store.get_user_summaries_for_users("ch1", ["u1", "u_missing"])
        assert len(result) == 1
        assert result[0].username == "Alice"

    def test_returns_empty_for_no_matches(self, store):
        result = store.get_user_summaries_for_users("ch1", ["u_missing"])
        assert result == []

    def test_empty_user_ids_returns_empty(self, store):
        result = store.get_user_summaries_for_users("ch1", [])
        assert result == []

    def test_scoped_to_channel(self, store, session):
        store.upsert_summary("ch1", "u1", "Alice", "Alice in ch1.", 10)
        store.upsert_summary("ch2", "u1", "Alice", "Alice in ch2.", 20)
        result = store.get_user_summaries_for_users("ch1", ["u1"])
        assert len(result) == 1
        assert "ch1" in result[0].summary
