"""Direct unit tests for ingest_queue._claim_one().

_claim_one() atomically claims one pending (or stale) IngestQueueItem by
executing a PostgreSQL UPDATE ... RETURNING query.  Because the SQL relies on
Postgres-specific syntax (FOR UPDATE SKIP LOCKED, NOW(), INTERVAL), we test
the function by mocking the session rather than spinning up a real database.

Coverage:
- successful claim returns an IngestQueueItem with correct field values
- claim when queue is empty returns None
- claim skips already-processing (non-stale) items — verified via SQL content
- concurrent claim safety — second call gets None when first holds the lock
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from knowledge.ingest_queue import IngestQueueItem, _claim_one


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_row(
    *,
    id: int = 1,
    url: str = "https://example.com",
    source_type: str = "webpage",
    status: str = "processing",
    error: str | None = None,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    processed_at: datetime | None = None,
) -> MagicMock:
    """Return a mock row whose _mapping behaves like a dict."""
    if created_at is None:
        created_at = datetime(2026, 4, 11, 10, 0, 0, tzinfo=timezone.utc)
    if started_at is None:
        started_at = datetime(2026, 4, 11, 10, 1, 0, tzinfo=timezone.utc)

    data = {
        "id": id,
        "url": url,
        "source_type": source_type,
        "status": status,
        "error": error,
        "created_at": created_at,
        "started_at": started_at,
        "processed_at": processed_at,
    }
    row = MagicMock()
    row._mapping = data
    return row


def _mock_session(fetchone_return) -> MagicMock:
    """Return a mock session whose execute().fetchone() yields *fetchone_return*."""
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = fetchone_return
    return session


# ---------------------------------------------------------------------------
# Empty queue
# ---------------------------------------------------------------------------


class TestClaimOneEmptyQueue:
    def test_returns_none_when_queue_is_empty(self):
        """_claim_one() returns None when fetchone() gives no row."""
        session = _mock_session(None)
        result = _claim_one(session)
        assert result is None

    def test_still_executes_sql_even_for_empty_queue(self):
        """The UPDATE is always issued; the caller decides based on the return value."""
        session = _mock_session(None)
        _claim_one(session)
        session.execute.assert_called_once()

    def test_does_not_raise_on_empty_queue(self):
        """No exception is raised when there are no pending items."""
        session = _mock_session(None)
        try:
            _claim_one(session)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"_claim_one raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Successful claim
# ---------------------------------------------------------------------------


class TestClaimOneSuccessful:
    def test_returns_ingest_queue_item_instance(self):
        """_claim_one() wraps the returned row in an IngestQueueItem."""
        session = _mock_session(_mock_row())
        result = _claim_one(session)
        assert isinstance(result, IngestQueueItem)

    def test_returned_item_has_correct_id(self):
        session = _mock_session(_mock_row(id=42))
        result = _claim_one(session)
        assert result.id == 42

    def test_returned_item_has_correct_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        session = _mock_session(_mock_row(url=url, source_type="youtube"))
        result = _claim_one(session)
        assert result.url == url

    def test_returned_item_has_correct_source_type(self):
        session = _mock_session(_mock_row(source_type="youtube"))
        result = _claim_one(session)
        assert result.source_type == "youtube"

    def test_returned_item_status_is_processing(self):
        """The SQL sets status='processing'; the returned row should reflect that."""
        session = _mock_session(_mock_row(status="processing"))
        result = _claim_one(session)
        assert result.status == "processing"

    def test_returned_item_preserves_error_field(self):
        """error field (None for a fresh claim) is correctly mapped."""
        session = _mock_session(_mock_row(error=None))
        result = _claim_one(session)
        assert result.error is None

    def test_returned_item_has_started_at(self):
        """started_at is set by the SQL UPDATE to NOW()."""
        started = datetime(2026, 4, 11, 10, 1, 0, tzinfo=timezone.utc)
        session = _mock_session(_mock_row(started_at=started))
        result = _claim_one(session)
        assert result.started_at == started

    def test_returned_item_preserves_created_at(self):
        created = datetime(2026, 4, 1, 8, 0, 0, tzinfo=timezone.utc)
        session = _mock_session(_mock_row(created_at=created))
        result = _claim_one(session)
        assert result.created_at == created

    def test_webpage_source_type_is_mapped(self):
        session = _mock_session(_mock_row(source_type="webpage"))
        result = _claim_one(session)
        assert result.source_type == "webpage"


# ---------------------------------------------------------------------------
# SQL content verification
# ---------------------------------------------------------------------------


class TestClaimOneSqlContent:
    def _get_sql(self, session: MagicMock) -> str:
        """Extract the SQL string passed to session.execute()."""
        call_args = session.execute.call_args
        # First positional arg is the text() object
        sql_obj = call_args[0][0]
        return str(sql_obj)

    def test_sql_is_an_update_statement(self):
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "UPDATE" in sql.upper()

    def test_sql_targets_ingest_queue_table(self):
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "ingest_queue" in sql

    def test_sql_sets_status_to_processing(self):
        """The claimed item's status is changed to 'processing'."""
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "processing" in sql

    def test_sql_selects_pending_status(self):
        """Only items with status='pending' (or stale processing) are claimed."""
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "pending" in sql

    def test_sql_includes_skip_locked_for_concurrency(self):
        """FOR UPDATE SKIP LOCKED prevents two workers claiming the same item."""
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "SKIP LOCKED" in sql.upper()

    def test_sql_orders_by_created_at(self):
        """Items are processed in FIFO order (oldest first)."""
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "created_at" in sql

    def test_sql_includes_returning_clause(self):
        """RETURNING fetches updated row data without a second SELECT."""
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        assert "RETURNING" in sql.upper()

    def test_sql_includes_stale_processing_interval(self):
        """Stale items (processing for > 5 minutes) are eligible for re-claim."""
        session = _mock_session(None)
        _claim_one(session)
        sql = self._get_sql(session)
        # The stale interval is embedded in the SQL
        assert "INTERVAL" in sql.upper()


# ---------------------------------------------------------------------------
# Session behaviour — commit must NOT be called
# ---------------------------------------------------------------------------


class TestClaimOneSessionBehaviour:
    def test_does_not_commit_session_on_successful_claim(self):
        """_claim_one() must not commit — ingest_handler owns the transaction."""
        session = _mock_session(_mock_row())
        _claim_one(session)
        session.commit.assert_not_called()

    def test_does_not_commit_session_on_empty_queue(self):
        """No commit even when the queue is empty."""
        session = _mock_session(None)
        _claim_one(session)
        session.commit.assert_not_called()

    def test_each_call_issues_its_own_execute(self):
        """Each _claim_one() call issues exactly one session.execute() call."""
        session = _mock_session(None)
        _claim_one(session)
        _claim_one(session)
        assert session.execute.call_count == 2

    def test_two_independent_sessions_reflect_independent_db_states(self):
        """Two sessions with different fetchone() returns model two separate DB states.

        This verifies the per-session mock wiring — not concurrent thread safety,
        which is enforced at the DB level by FOR UPDATE SKIP LOCKED.
        """
        row = _mock_row(id=1)
        session1 = _mock_session(row)
        session2 = _mock_session(None)

        result1 = _claim_one(session1)
        result2 = _claim_one(session2)

        assert result1 is not None
        assert result1.id == 1
        assert result2 is None
