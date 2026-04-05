"""Tests for MessageStore.upsert_summary() and find_user_id_by_username() edge cases.

Covers gaps not addressed by store_summary_test.py:
- upsert_summary updates the username field when it changes
- upsert_summary refreshes updated_at when an existing record is updated
- get_user_summary finds by updated username (not stale one)
- find_user_id_by_username returns the user_id from the most recent message
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.models import Message, UserChannelSummary
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


class TestUpsertSummaryUsernameAndTimestamp:
    def test_updates_username_on_existing_record(self, store, session):
        """upsert_summary updates the username field when the display name changes."""
        store.upsert_summary("ch1", "u1", "alice", "Initial summary.", 1)
        store.upsert_summary("ch1", "u1", "Alice", "Updated summary.", 2)

        # Look up by new username
        result = store.get_user_summary("ch1", "Alice")
        assert result is not None
        assert result.username == "Alice"
        assert result.summary == "Updated summary."

    def test_old_username_no_longer_found_after_update(self, store, session):
        """After upsert changes username, get_user_summary returns None for the old name."""
        store.upsert_summary("ch1", "u1", "alice_old", "Some summary.", 1)
        store.upsert_summary("ch1", "u1", "alice_new", "Updated summary.", 2)

        old_result = store.get_user_summary("ch1", "alice_old")
        new_result = store.get_user_summary("ch1", "alice_new")

        assert old_result is None
        assert new_result is not None
        assert new_result.summary == "Updated summary."

    def test_updated_at_refreshed_to_newer_time_on_update(self, store, session):
        """upsert_summary sets updated_at to current time when updating an existing record."""
        past_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Insert directly with a known past updated_at
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                summary="Old summary.",
                last_message_id=1,
                updated_at=past_time,
            )
        )
        session.commit()

        # Call upsert to trigger the update path
        store.upsert_summary("ch1", "u1", "Alice", "New summary.", 10)

        result = store.get_user_summary("ch1", "Alice")
        assert result is not None

        # updated_at should be later than the past_time we explicitly set
        # SQLite stores datetimes without timezone info — strip tz for comparison
        updated_naive = (
            result.updated_at.replace(tzinfo=None)
            if result.updated_at.tzinfo
            else result.updated_at
        )
        past_naive = past_time.replace(tzinfo=None)
        assert updated_naive > past_naive


class TestFindUserIdByUsernameOrdering:
    def test_returns_user_id_from_most_recent_message(self, store, session):
        """find_user_id_by_username returns the user_id from the most recent matching message.

        This matters when the same username was used by different user_ids over time,
        or when the same user created multiple messages.
        """
        t_early = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t_late = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        old_msg = Message(
            discord_message_id="1",
            channel_id="ch1",
            user_id="old_user_id",
            username="Alice",
            content="early message",
            is_bot=False,
            embedding=[0.0] * 1024,
            created_at=t_early,
        )
        new_msg = Message(
            discord_message_id="2",
            channel_id="ch1",
            user_id="new_user_id",
            username="Alice",
            content="late message",
            is_bot=False,
            embedding=[0.0] * 1024,
            created_at=t_late,
        )
        session.add(old_msg)
        session.add(new_msg)
        session.commit()

        result = store.find_user_id_by_username("ch1", "Alice")
        assert result == "new_user_id"

    def test_returns_correct_user_when_many_messages(self, store, session):
        """find_user_id_by_username works correctly when the user has many messages."""
        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i in range(10):
            session.add(
                Message(
                    discord_message_id=str(i),
                    channel_id="ch1",
                    user_id="u1",
                    username="Alice",
                    content=f"message {i}",
                    is_bot=False,
                    embedding=[0.0] * 1024,
                    created_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        session.commit()

        result = store.find_user_id_by_username("ch1", "Alice")
        assert result == "u1"
