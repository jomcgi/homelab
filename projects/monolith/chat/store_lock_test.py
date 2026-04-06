"""Tests for MessageStore message lock operations.

Covers acquire_lock, mark_completed, release_lock, reclaim_expired, and
cleanup_completed.  All tests run against an in-memory SQLite database.

The raw SQL in reclaim_expired and cleanup_completed uses ``chat.message_locks``
(Postgres schema prefix) and ``FOR UPDATE SKIP LOCKED`` (Postgres-only locking).
We patch ``chat.store.text`` with a SQLite-compatible translation helper so the
queries run against the stripped-schema SQLite test database.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text as _real_text
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import MessageLock
from chat.store import MessageStore


# ---------------------------------------------------------------------------
# SQLite compatibility helper
# ---------------------------------------------------------------------------


def _sqlite_text(sql: str):
    """Translate Postgres-specific SQL to SQLite-compatible SQL.

    Strips the ``chat.`` schema prefix (SQLite has no schema support) and
    removes ``FOR UPDATE SKIP LOCKED`` (Postgres-only locking clause).
    """
    sql = sql.replace("chat.message_locks", "message_locks")
    sql = sql.replace("FOR UPDATE SKIP LOCKED", "").rstrip()
    return _real_text(sql)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session with schema stripped for SQLite compat."""
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
    from unittest.mock import AsyncMock

    embed_client = AsyncMock()
    embed_client.embed_batch.return_value = [[0.0] * 1024]
    return MessageStore(session=session, embed_client=embed_client)


# ---------------------------------------------------------------------------
# acquire_lock
# ---------------------------------------------------------------------------


class TestAcquireLock:
    def test_returns_true_on_first_acquire(self, store):
        """First caller to acquire_lock wins and gets True."""
        result = store.acquire_lock("msg-1", "ch-1")
        assert result is True

    def test_returns_false_on_duplicate_acquire(self, store, session):
        """Second acquire_lock on the same message_id returns False."""
        store.acquire_lock("msg-2", "ch-1")
        result = store.acquire_lock("msg-2", "ch-1")
        assert result is False

    def test_lock_row_created_in_db(self, store, session):
        """acquire_lock inserts a MessageLock row."""
        store.acquire_lock("msg-3", "99")
        lock = session.get(MessageLock, "msg-3")
        assert lock is not None
        assert lock.channel_id == "99"
        assert lock.completed is False

    def test_different_messages_can_be_acquired_independently(self, store):
        """Two different message IDs can both be acquired."""
        assert store.acquire_lock("msg-a", "ch-1") is True
        assert store.acquire_lock("msg-b", "ch-1") is True

    def test_duplicate_does_not_overwrite_existing_lock(self, store, session):
        """Failed duplicate acquire leaves the original lock intact."""
        store.acquire_lock("msg-4", "ch-1")
        original_lock = session.get(MessageLock, "msg-4")
        original_claimed_at = original_lock.claimed_at

        store.acquire_lock("msg-4", "ch-1")  # duplicate → False

        lock = session.get(MessageLock, "msg-4")
        assert lock.claimed_at == original_claimed_at


# ---------------------------------------------------------------------------
# mark_completed
# ---------------------------------------------------------------------------


class TestMarkCompleted:
    def test_sets_completed_true(self, store, session):
        """mark_completed sets completed=True on an existing lock."""
        store.acquire_lock("msg-10", "ch-1")
        store.mark_completed("msg-10")
        lock = session.get(MessageLock, "msg-10")
        assert lock.completed is True

    def test_noop_when_lock_does_not_exist(self, store, session):
        """mark_completed on a non-existent ID is a no-op (no exception)."""
        store.mark_completed("nonexistent-id")
        # No error and no row created.
        lock = session.get(MessageLock, "nonexistent-id")
        assert lock is None

    def test_does_not_affect_other_locks(self, store, session):
        """mark_completed only modifies the targeted lock row."""
        store.acquire_lock("msg-11", "ch-1")
        store.acquire_lock("msg-12", "ch-1")
        store.mark_completed("msg-11")

        lock_11 = session.get(MessageLock, "msg-11")
        lock_12 = session.get(MessageLock, "msg-12")
        assert lock_11.completed is True
        assert lock_12.completed is False


# ---------------------------------------------------------------------------
# release_lock
# ---------------------------------------------------------------------------


class TestReleaseLock:
    def test_deletes_lock_row(self, store, session):
        """release_lock removes the lock from the database."""
        store.acquire_lock("msg-20", "ch-1")
        store.release_lock("msg-20")
        lock = session.get(MessageLock, "msg-20")
        assert lock is None

    def test_noop_when_lock_does_not_exist(self, store, session):
        """release_lock on a non-existent ID is a no-op (no exception)."""
        store.release_lock("ghost-message-id")
        lock = session.get(MessageLock, "ghost-message-id")
        assert lock is None

    def test_does_not_affect_other_locks(self, store, session):
        """release_lock only removes the targeted lock."""
        store.acquire_lock("msg-21", "ch-1")
        store.acquire_lock("msg-22", "ch-1")
        store.release_lock("msg-21")

        assert session.get(MessageLock, "msg-21") is None
        assert session.get(MessageLock, "msg-22") is not None

    def test_released_lock_can_be_reacquired(self, store):
        """After release_lock the same ID can be acquired again."""
        store.acquire_lock("msg-23", "ch-1")
        store.release_lock("msg-23")
        result = store.acquire_lock("msg-23", "ch-1")
        assert result is True


# ---------------------------------------------------------------------------
# reclaim_expired
# ---------------------------------------------------------------------------


class TestReclaimExpired:
    """Tests for reclaim_expired.

    The method uses raw SQL with ``FOR UPDATE SKIP LOCKED`` and the
    ``chat.`` schema prefix — both Postgres-only features.  We patch
    ``chat.store.text`` with a SQLite-compatible helper so the query
    executes against the test database.
    """

    def _insert_lock(
        self, session, msg_id, channel_id, *, completed=False, age_seconds=0
    ):
        """Insert a lock with a specific age."""
        claimed_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        lock = MessageLock(
            discord_message_id=msg_id,
            channel_id=channel_id,
            claimed_at=claimed_at,
            completed=completed,
        )
        session.add(lock)
        session.commit()
        session.refresh(lock)
        return lock

    def test_returns_expired_uncompleted_locks(self, store, session):
        """reclaim_expired returns locks older than TTL that are not completed."""
        self._insert_lock(session, "exp-1", "ch-1", age_seconds=60)

        with patch("chat.store.text", side_effect=_sqlite_text):
            result = store.reclaim_expired(ttl_seconds=30, limit=5)

        assert len(result) == 1
        assert result[0].discord_message_id == "exp-1"

    def test_bumps_claimed_at_on_reclaimed_locks(self, store, session):
        """reclaim_expired updates claimed_at on reclaimed locks.

        SQLite returns datetimes without timezone info (offset-naive).  We
        compare both stored values from SQLite so the assertion stays naive
        vs naive and avoids ``TypeError: can't compare offset-naive and
        offset-aware datetimes``.
        """
        old_lock = self._insert_lock(session, "exp-2", "ch-1", age_seconds=60)
        # original_claimed_at is offset-naive (loaded from SQLite).
        original_claimed_at = old_lock.claimed_at

        with patch("chat.store.text", side_effect=_sqlite_text):
            store.reclaim_expired(ttl_seconds=30, limit=5)

        session.expire_all()
        refreshed = session.get(MessageLock, "exp-2")
        assert refreshed is not None
        # Both timestamps are offset-naive (from SQLite); bump is verified by
        # checking the new value is strictly later than the original.
        assert refreshed.claimed_at > original_claimed_at

    def test_completed_locks_not_returned(self, store, session):
        """reclaim_expired does not return completed locks (query filters them)."""
        self._insert_lock(session, "done-1", "ch-1", completed=True, age_seconds=120)

        with patch("chat.store.text", side_effect=_sqlite_text):
            result = store.reclaim_expired(ttl_seconds=30, limit=5)

        assert result == []
        # Completed lock untouched.
        lock = session.get(MessageLock, "done-1")
        assert lock.completed is True

    def test_limit_restricts_number_of_results(self, store, session):
        """reclaim_expired respects the limit parameter."""
        for i in range(5):
            self._insert_lock(session, f"lim-{i}", "ch-1", age_seconds=60)

        with patch("chat.store.text", side_effect=_sqlite_text):
            result = store.reclaim_expired(ttl_seconds=30, limit=2)

        assert len(result) == 2

    def test_empty_result_when_no_expired_locks(self, store, session):
        """reclaim_expired returns empty list when no locks are expired."""
        # Insert a recent lock (5s old, TTL is 30s).
        self._insert_lock(session, "fresh-1", "ch-1", age_seconds=5)

        with patch("chat.store.text", side_effect=_sqlite_text):
            result = store.reclaim_expired(ttl_seconds=30, limit=5)

        assert result == []

    def test_mixed_population_only_returns_expired_uncompleted(self, store, session):
        """reclaim_expired with mixed data only reclaims expired+uncompleted locks.

        This test exercises the full WHERE predicate in a single fixture:
          - ``mix-expired-uncompleted``: expired and not completed → SHOULD be reclaimed
          - ``mix-expired-completed``:   expired but completed    → MUST NOT be returned
          - ``mix-fresh-uncompleted``:   fresh and not completed  → MUST NOT be returned

        A regression that dropped either ``AND`` clause would incorrectly include
        one of the other two rows.
        """
        self._insert_lock(session, "mix-expired-uncompleted", "ch-1", age_seconds=60)
        self._insert_lock(
            session, "mix-expired-completed", "ch-1", completed=True, age_seconds=60
        )
        self._insert_lock(session, "mix-fresh-uncompleted", "ch-1", age_seconds=5)

        with patch("chat.store.text", side_effect=_sqlite_text):
            result = store.reclaim_expired(ttl_seconds=30, limit=10)

        returned_ids = {r.discord_message_id for r in result}
        assert returned_ids == {"mix-expired-uncompleted"}

        # Verify the completed and fresh locks were not bumped.
        session.expire_all()
        completed_lock = session.get(MessageLock, "mix-expired-completed")
        fresh_lock = session.get(MessageLock, "mix-fresh-uncompleted")
        assert completed_lock.completed is True  # untouched
        assert fresh_lock is not None  # still present

    def test_return_value_carries_pre_bump_claimed_at(self, store, session):
        """reclaim_expired returns objects with the *original* claimed_at, not the bumped one.

        The implementation SELECTs rows, constructs MessageLock objects, then
        updates claimed_at in a second pass.  The returned list is built before
        the bump, so callers receive the pre-bump timestamps.  This contract is
        intentional — callers can use it to compute how long the lock was stale.
        """
        old_lock = self._insert_lock(session, "ret-1", "ch-1", age_seconds=60)
        original_claimed_at = old_lock.claimed_at

        with patch("chat.store.text", side_effect=_sqlite_text):
            result = store.reclaim_expired(ttl_seconds=30, limit=5)

        assert len(result) == 1
        returned_lock = result[0]
        # The returned object carries the pre-bump timestamp (offset-naive from SQLite).
        # Strip UTC tzinfo from original if present so comparison is naive vs naive.
        original_naive = original_claimed_at.replace(tzinfo=None)
        returned_naive = (
            returned_lock.claimed_at.replace(tzinfo=None)
            if returned_lock.claimed_at.tzinfo is not None
            else returned_lock.claimed_at
        )
        assert returned_naive == original_naive

        # Confirm the DB row *was* bumped (i.e. the bump actually happened).
        session.expire_all()
        refreshed = session.get(MessageLock, "ret-1")
        assert refreshed.claimed_at > returned_lock.claimed_at


# ---------------------------------------------------------------------------
# cleanup_completed
# ---------------------------------------------------------------------------


class TestCleanupCompleted:
    """Tests for cleanup_completed.

    The method uses raw SQL with the ``chat.`` schema prefix.  We patch
    ``chat.store.text`` with a SQLite-compatible helper for each test.
    """

    def _insert_completed(self, session, msg_id, age_seconds):
        """Insert a completed lock with a given age."""
        claimed_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        lock = MessageLock(
            discord_message_id=msg_id,
            channel_id="ch-1",
            claimed_at=claimed_at,
            completed=True,
        )
        session.add(lock)
        session.commit()

    def test_deletes_old_completed_locks(self, store, session):
        """cleanup_completed removes completed locks older than max_age."""
        self._insert_completed(session, "old-done-1", age_seconds=7200)

        with patch("chat.store.text", side_effect=_sqlite_text):
            count = store.cleanup_completed(max_age_seconds=3600)

        assert count == 1
        assert session.get(MessageLock, "old-done-1") is None

    def test_keeps_young_completed_locks(self, store, session):
        """cleanup_completed retains completed locks newer than max_age."""
        self._insert_completed(session, "new-done-1", age_seconds=60)

        with patch("chat.store.text", side_effect=_sqlite_text):
            count = store.cleanup_completed(max_age_seconds=3600)

        assert count == 0
        assert session.get(MessageLock, "new-done-1") is not None

    def test_keeps_uncompleted_locks_regardless_of_age(self, store, session):
        """cleanup_completed never removes uncompleted (in-progress) locks."""
        claimed_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
        lock = MessageLock(
            discord_message_id="old-incomplete",
            channel_id="ch-1",
            claimed_at=claimed_at,
            completed=False,
        )
        session.add(lock)
        session.commit()

        with patch("chat.store.text", side_effect=_sqlite_text):
            count = store.cleanup_completed(max_age_seconds=3600)

        assert count == 0
        assert session.get(MessageLock, "old-incomplete") is not None

    def test_returns_correct_delete_count(self, store, session):
        """cleanup_completed returns the number of rows deleted."""
        for i in range(3):
            self._insert_completed(session, f"bulk-old-{i}", age_seconds=7200)
        # One young one that should survive.
        self._insert_completed(session, "bulk-young", age_seconds=10)

        with patch("chat.store.text", side_effect=_sqlite_text):
            count = store.cleanup_completed(max_age_seconds=3600)

        assert count == 3

    def test_returns_zero_when_nothing_to_clean(self, store, session):
        """cleanup_completed returns 0 when there is nothing to delete."""
        with patch("chat.store.text", side_effect=_sqlite_text):
            count = store.cleanup_completed(max_age_seconds=3600)

        assert count == 0

    def test_deletes_multiple_old_completed_locks(self, store, session):
        """cleanup_completed deletes all qualifying rows in one call."""
        for i in range(5):
            self._insert_completed(session, f"multi-old-{i}", age_seconds=7200)

        with patch("chat.store.text", side_effect=_sqlite_text):
            count = store.cleanup_completed(max_age_seconds=3600)

        assert count == 5
        remaining = session.exec(select(MessageLock)).all()
        assert len(remaining) == 0
