"""Unit tests for scheduler loop functions (_tick, _complete_job, _fail_job, etc.)."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from shared.scheduler import (
    ScheduledJob,
    _complete_job,
    _fail_job,
    _registry,
    _release_lock,
    _tick,
    run_scheduler_loop,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session with schema stripped (SQLite has no schemas)."""
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


@pytest.fixture(autouse=True)
def _clear_registry():
    """Ensure a clean handler registry for each test."""
    _registry.clear()
    yield
    _registry.clear()


def _make_job(
    name: str = "test-job",
    interval_secs: int = 60,
    next_run_at: datetime | None = None,
    locked_by: str | None = "host-1",
    locked_at: datetime | None = None,
    last_run_at: datetime | None = None,
    last_status: str | None = None,
) -> ScheduledJob:
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        name=name,
        interval_secs=interval_secs,
        next_run_at=next_run_at or now,
        locked_by=locked_by,
        locked_at=locked_at or now,
        last_run_at=last_run_at,
        last_status=last_status,
    )


# ---------------------------------------------------------------------------
# _complete_job
# ---------------------------------------------------------------------------


class TestCompleteJob:
    def test_clears_lock_and_advances(self, session: Session):
        """_complete_job sets last_status='ok', clears lock, advances next_run_at."""
        job = _make_job(interval_secs=120)
        session.add(job)
        session.commit()

        _complete_job(session, job, override=None)

        assert job.last_status == "ok"
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.last_run_at is not None
        # next_run_at should be ~120s from now
        expected_min = datetime.now(timezone.utc) + timedelta(seconds=115)
        expected_max = datetime.now(timezone.utc) + timedelta(seconds=125)
        next_run = (
            job.next_run_at.replace(tzinfo=timezone.utc)
            if job.next_run_at.tzinfo is None
            else job.next_run_at
        )
        assert expected_min <= next_run <= expected_max

    def test_uses_override(self, session: Session):
        """_complete_job uses handler-returned datetime instead of computed next."""
        job = _make_job(interval_secs=60)
        session.add(job)
        session.commit()

        override_time = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        _complete_job(session, job, override=override_time)

        next_run = (
            job.next_run_at.replace(tzinfo=timezone.utc)
            if job.next_run_at.tzinfo is None
            else job.next_run_at
        )
        assert next_run == override_time
        assert job.last_status == "ok"


# ---------------------------------------------------------------------------
# _fail_job
# ---------------------------------------------------------------------------


class TestFailJob:
    def test_records_error_and_advances(self, session: Session):
        """_fail_job sets last_status to error message, clears lock, advances next_run_at."""
        job = _make_job(interval_secs=90)
        session.add(job)
        session.commit()

        _fail_job(session, job, "connection timeout")

        assert job.last_status == "error: connection timeout"
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.last_run_at is not None
        expected_min = datetime.now(timezone.utc) + timedelta(seconds=85)
        expected_max = datetime.now(timezone.utc) + timedelta(seconds=95)
        next_run = (
            job.next_run_at.replace(tzinfo=timezone.utc)
            if job.next_run_at.tzinfo is None
            else job.next_run_at
        )
        assert expected_min <= next_run <= expected_max

    def test_truncates_long_error(self, session: Session):
        """Error messages are truncated to 200 chars."""
        job = _make_job()
        session.add(job)
        session.commit()

        long_error = "x" * 500
        _fail_job(session, job, long_error)

        # "error: " prefix + 200 chars
        assert job.last_status == f"error: {'x' * 200}"
        assert len(job.last_status) == 7 + 200  # "error: " is 7 chars


# ---------------------------------------------------------------------------
# _release_lock
# ---------------------------------------------------------------------------


class TestReleaseLock:
    def test_clears_lock_only(self, session: Session):
        """_release_lock only clears lock fields, doesn't touch other fields."""
        original_next = datetime(2030, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        original_last = datetime(2030, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        job = _make_job(
            locked_by="host-1",
            next_run_at=original_next,
            last_run_at=original_last,
            last_status="ok",
        )
        session.add(job)
        session.commit()

        _release_lock(session, job)

        assert job.locked_by is None
        assert job.locked_at is None
        # These should be unchanged
        next_run = (
            job.next_run_at.replace(tzinfo=timezone.utc)
            if job.next_run_at.tzinfo is None
            else job.next_run_at
        )
        last_run = (
            job.last_run_at.replace(tzinfo=timezone.utc)
            if job.last_run_at.tzinfo is None
            else job.last_run_at
        )
        assert next_run == original_next
        assert last_run == original_last
        assert job.last_status == "ok"


# ---------------------------------------------------------------------------
# _tick (mocked)
# ---------------------------------------------------------------------------


class TestTick:
    @pytest.mark.asyncio
    async def test_calls_handler_on_claimed_job(self):
        """When _claim_next_job returns a name, the handler is called."""
        handler = AsyncMock(return_value=None)
        _registry["my-job"] = handler

        now = datetime.now(timezone.utc)
        fake_job = ScheduledJob(
            name="my-job",
            interval_secs=60,
            next_run_at=now,
            locked_by="host",
            locked_at=now,
        )

        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = fake_job

        with (
            patch("shared.scheduler.get_engine"),
            patch("shared.scheduler.Session") as mock_session_cls,
            patch("shared.scheduler._claim_next_job", return_value="my-job"),
            patch("shared.scheduler._complete_job") as mock_complete,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await _tick()

        handler.assert_called_once_with(mock_session)
        mock_complete.assert_called_once_with(mock_session, fake_job, None)

    @pytest.mark.asyncio
    async def test_skips_when_no_due_jobs(self):
        """When _claim_next_job returns None, no handler is called."""
        handler = AsyncMock()
        _registry["some-job"] = handler

        with (
            patch("shared.scheduler.get_engine"),
            patch("shared.scheduler.Session") as mock_session_cls,
            patch("shared.scheduler._claim_next_job", return_value=None),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock(spec=Session)
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await _tick()

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_fail_on_handler_exception(self):
        """When a handler raises, _fail_job is called."""
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        _registry["fail-job"] = handler

        now = datetime.now(timezone.utc)
        fake_job = ScheduledJob(
            name="fail-job",
            interval_secs=60,
            next_run_at=now,
            locked_by="host",
            locked_at=now,
        )

        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = fake_job

        with (
            patch("shared.scheduler.get_engine"),
            patch("shared.scheduler.Session") as mock_session_cls,
            patch("shared.scheduler._claim_next_job", return_value="fail-job"),
            patch("shared.scheduler._fail_job") as mock_fail,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await _tick()

        mock_fail.assert_called_once_with(mock_session, fake_job, "boom")

    @pytest.mark.asyncio
    async def test_releases_lock_for_missing_handler(self):
        """When a job is claimed but no handler exists, _release_lock is called."""
        now = datetime.now(timezone.utc)
        fake_job = ScheduledJob(
            name="orphan-job",
            interval_secs=60,
            next_run_at=now,
            locked_by="host",
            locked_at=now,
        )

        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = fake_job

        with (
            patch("shared.scheduler.get_engine"),
            patch("shared.scheduler.Session") as mock_session_cls,
            patch("shared.scheduler._claim_next_job", return_value="orphan-job"),
            patch("shared.scheduler._release_lock") as mock_release,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await _tick()

        mock_release.assert_called_once_with(mock_session, fake_job)


# ---------------------------------------------------------------------------
# run_scheduler_loop
# ---------------------------------------------------------------------------


class TestRunSchedulerLoop:
    @pytest.mark.asyncio
    async def test_catches_tick_exceptions(self):
        """The loop continues after _tick raises an exception."""
        call_count = 0

        async def tick_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("tick exploded")
            if call_count >= 3:
                raise KeyboardInterrupt  # break the loop

        with (
            patch("shared.scheduler._tick", side_effect=tick_side_effect),
            patch(
                "shared.scheduler.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_scheduler_loop(poll_interval=1)

        # tick was called at least 3 times (first errored, second succeeded, third broke)
        assert call_count >= 3
        # sleep was called between ticks
        assert mock_sleep.call_count >= 2
