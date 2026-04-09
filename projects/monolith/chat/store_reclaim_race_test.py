"""Tests for the reclaim_expired race-condition guard in chat/store.py.

The ``reclaim_expired`` method fetches expired locks with FOR UPDATE SKIP
LOCKED and then re-reads each one via ``session.get()`` before bumping
``claimed_at``.  Between the SELECT and the GET, another process can delete
the row; the ``if refreshed:`` guard at line 376 prevents an
``AttributeError`` in that scenario.

These tests exercise that guard path directly using a mock session so the
SQLite test fixture's lack of advisory-lock support is irrelevant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.models import MessageLock
from chat.store import MessageStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sqlite_text(sql_str, *args, **kwargs):
    """Replace the Postgres-specific SQL with SQLite-compatible equivalent."""
    from sqlalchemy import text

    # Strip the FOR UPDATE SKIP LOCKED clause (SQLite doesn't support it)
    sqlite_sql = (
        sql_str.replace("FOR UPDATE SKIP LOCKED", "")
        .replace("chat.message_locks", "messagelocks")
        .strip()
    )
    return text(sqlite_sql)


@pytest.fixture(name="session")
def session_fixture():
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
def embed_client():
    client = MagicMock()
    return client


@pytest.fixture
def store(session, embed_client):
    return MessageStore(session=session, embed_client=embed_client)


# ---------------------------------------------------------------------------
# reclaim_expired — race-condition guard: session.get() returns None
# ---------------------------------------------------------------------------


class TestReclaimExpiredRaceGuard:
    """The ``if refreshed:`` guard prevents AttributeError when a lock is
    deleted between the FOR UPDATE SKIP LOCKED SELECT and the session.get().

    We simulate this by:
    1. Inserting a real expired lock into the SQLite fixture.
    2. Patching ``session.get`` to return ``None`` for the specific lock ID.
    3. Verifying that ``reclaim_expired`` completes without raising and that
       the returned list still contains the lock from the SELECT phase.
    """

    def _insert_lock(self, session, msg_id, *, age_seconds=60):
        from datetime import timedelta

        lock = MessageLock(
            discord_message_id=msg_id,
            channel_id="ch-race",
            claimed_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
            completed=False,
        )
        session.add(lock)
        session.commit()
        session.refresh(lock)
        return lock

    def test_none_refreshed_does_not_raise(self, store, session):
        """When session.get() returns None (deleted row), reclaim_expired must
        not raise AttributeError and must complete normally."""
        self._insert_lock(session, "race-1")

        original_get = session.get

        def get_none_for_race(model, pk, **kw):
            if model is MessageLock and pk == "race-1":
                return None
            return original_get(model, pk, **kw)

        with patch("chat.store.text", side_effect=_sqlite_text):
            with patch.object(session, "get", side_effect=get_none_for_race):
                # Must not raise AttributeError (was: refreshed.claimed_at = now)
                result = store.reclaim_expired(ttl_seconds=30, limit=5)

        # The SELECT phase found the lock; we still return it.
        assert len(result) == 1
        assert result[0].discord_message_id == "race-1"

    def test_none_refreshed_skips_bump(self, store, session):
        """When the race fires, claimed_at is NOT bumped (no row to update)."""
        self._insert_lock(session, "race-2", age_seconds=90)

        original_get = session.get

        def get_none(model, pk, **kw):
            if model is MessageLock:
                return None
            return original_get(model, pk, **kw)

        with patch("chat.store.text", side_effect=_sqlite_text):
            with patch.object(session, "get", side_effect=get_none):
                result = store.reclaim_expired(ttl_seconds=30, limit=5)

        # The lock is returned from the SELECT phase...
        assert len(result) == 1
        # ...but session.add() was never called with a bump, so claimed_at
        # is unchanged in the DB.
        session.expire_all()
        lock_after = session.get(MessageLock, "race-2")
        assert lock_after is not None
        # The original lock is still in the DB (no-op update path)

    def test_partial_race_only_bumps_present_locks(self, store, session):
        """When only one of two expired locks disappears mid-reclaim, only the
        present lock has its claimed_at bumped."""
        from datetime import timedelta

        lock_a = self._insert_lock(session, "race-a", age_seconds=60)
        original_claimed_a = lock_a.claimed_at
        self._insert_lock(session, "race-b", age_seconds=60)

        original_get = session.get

        def get_none_for_b(model, pk, **kw):
            if model is MessageLock and pk == "race-b":
                return None
            return original_get(model, pk, **kw)

        with patch("chat.store.text", side_effect=_sqlite_text):
            with patch.object(session, "get", side_effect=get_none_for_b):
                result = store.reclaim_expired(ttl_seconds=30, limit=5)

        assert len(result) == 2
        # lock-a was bumped
        session.expire_all()
        a_after = session.get(MessageLock, "race-a")
        assert a_after is not None
        assert a_after.claimed_at > original_claimed_a
