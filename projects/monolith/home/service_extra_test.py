"""Extra coverage tests for home.service — exception propagation and next_midnight."""

from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from home import service
from home.models import Archive, Task
from home.service import archive_and_reset, daily_reset_handler

TZ = ZoneInfo("America/Vancouver")


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session with schema stripped."""
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


# ---------------------------------------------------------------------------
# daily_reset_handler — next_midnight calculation
# ---------------------------------------------------------------------------


class TestDailyResetHandlerNextMidnight:
    @pytest.mark.asyncio
    async def test_returns_next_midnight_in_vancouver_tz(self):
        """daily_reset_handler returns the next midnight in America/Vancouver."""
        # 2026-03-10 is a Tuesday (weekday 1)
        mock_now = datetime(2026, 3, 10, 14, 30, 0, tzinfo=TZ)
        expected_midnight = datetime.combine(
            mock_now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
        )
        session = MagicMock()

        with patch.object(service, "datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine
            with patch.object(service, "archive_and_reset"):
                result = await daily_reset_handler(session)

        assert result == expected_midnight
        assert result.tzinfo == TZ

    @pytest.mark.asyncio
    async def test_next_midnight_is_always_one_day_ahead(self):
        """The returned datetime is always midnight of the next calendar day."""
        # Check for a variety of hours to confirm it always advances 1 day
        for hour in (0, 1, 11, 23):
            mock_now = datetime(2026, 4, 5, hour, 0, 0, tzinfo=TZ)  # Sunday
            session = MagicMock()

            with patch.object(service, "datetime") as mock_dt:
                mock_dt.now.return_value = mock_now
                mock_dt.combine = datetime.combine
                with patch.object(service, "archive_and_reset"):
                    result = await daily_reset_handler(session)

            next_day = mock_now.date() + timedelta(days=1)
            assert result.date() == next_day
            assert result.hour == 0
            assert result.minute == 0
            assert result.second == 0

    @pytest.mark.asyncio
    async def test_monday_triggers_weekly_reset(self):
        """On Monday (weekday 0), archive_and_reset is called with weekly_reset=True."""
        mock_now = datetime(2026, 3, 30, 8, 0, 0, tzinfo=TZ)  # Monday
        session = MagicMock()

        with patch.object(service, "datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine
            with patch.object(service, "archive_and_reset") as mock_reset:
                await daily_reset_handler(session)

        mock_reset.assert_called_once_with(session, weekly_reset=True)

    @pytest.mark.asyncio
    async def test_non_monday_triggers_daily_reset(self):
        """On any weekday other than Monday, archive_and_reset is called with weekly_reset=False."""
        # Test Wed (2), Thu (3), Fri (4), Sat (5), Sun (6), Tue (1)
        non_mondays = [
            datetime(2026, 4, 1, 6, 0, tzinfo=TZ),  # Wednesday
            datetime(2026, 4, 2, 6, 0, tzinfo=TZ),  # Thursday
            datetime(2026, 4, 3, 6, 0, tzinfo=TZ),  # Friday
        ]
        for mock_now in non_mondays:
            session = MagicMock()
            with patch.object(service, "datetime") as mock_dt:
                mock_dt.now.return_value = mock_now
                mock_dt.combine = datetime.combine
                with patch.object(service, "archive_and_reset") as mock_reset:
                    await daily_reset_handler(session)
            mock_reset.assert_called_once_with(session, weekly_reset=False)

    @pytest.mark.asyncio
    async def test_archive_and_reset_exception_propagates(self):
        """If archive_and_reset raises, the exception propagates from daily_reset_handler."""
        mock_now = datetime(2026, 4, 7, 3, 0, 0, tzinfo=TZ)  # Tuesday
        session = MagicMock()

        with patch.object(service, "datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine
            with patch.object(
                service, "archive_and_reset", side_effect=RuntimeError("db error")
            ):
                with pytest.raises(RuntimeError, match="db error"):
                    await daily_reset_handler(session)


# ---------------------------------------------------------------------------
# archive_and_reset — large task lists and partial states
# ---------------------------------------------------------------------------


class TestArchiveAndResetExtra:
    def test_large_daily_task_list_all_archived(self, session):
        """More than 3 existing daily tasks are all archived (and replaced by 3 empty slots)."""
        session.add(Task(task="Weekly", done=False, kind="weekly", position=0))
        for i in range(6):
            session.add(
                Task(task=f"Daily {i}", done=(i % 2 == 0), kind="daily", position=i)
            )
        session.commit()

        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert archive is not None
        # All 6 tasks should appear in archive
        for i in range(6):
            assert f"Daily {i}" in archive.content

        # Only 3 new empty daily slots after reset
        daily = session.exec(select(Task).where(Task.kind == "daily")).all()
        assert len(daily) == 3

    def test_weekly_reset_with_no_weekly_task_creates_only_daily_slots(self, session):
        """Weekly reset with no weekly task produces 3 daily slots, no weekly task."""
        for i in range(3):
            session.add(Task(task=f"Daily {i}", done=False, kind="daily", position=i))
        session.commit()

        archive_and_reset(session, weekly_reset=True)

        tasks = session.exec(select(Task)).all()
        weekly = [t for t in tasks if t.kind == "weekly"]
        daily = [t for t in tasks if t.kind == "daily"]
        assert weekly == []
        assert len(daily) == 3

    def test_daily_reset_with_no_weekly_task_preserves_nothing(self, session):
        """Daily reset with no existing weekly task creates 3 empty daily slots only."""
        for i in range(3):
            session.add(Task(task=f"Daily {i}", done=False, kind="daily", position=i))
        session.commit()

        archive_and_reset(session, weekly_reset=False)

        tasks = session.exec(select(Task)).all()
        weekly = [t for t in tasks if t.kind == "weekly"]
        # No weekly task existed → nothing to preserve
        assert weekly == []

    def test_archive_content_contains_day_of_week(self, session):
        """Archive content includes the day name in the header."""
        session.add(Task(task="W", done=False, kind="weekly", position=0))
        session.commit()

        fixed_date = date(2026, 4, 6)  # Monday
        with patch("home.service.date") as mock_date:
            mock_date.today.return_value = fixed_date
            archive_and_reset(session, weekly_reset=True)

        archive = session.exec(select(Archive)).first()
        assert "Monday" in archive.content
        assert "April 6" in archive.content
