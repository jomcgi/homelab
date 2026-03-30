"""Unit tests for todo business logic — archive_and_reset()."""

from datetime import date
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from todo.models import Archive, Task
from todo.service import archive_and_reset


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session with schema stripped (SQLite has no schemas)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # SQLite doesn't support schemas (e.g. "todo.tasks"), so strip them
    # before creating tables and restore after.
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

    # Restore schemas so production code is unaffected.
    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


def _seed_tasks(
    session: Session,
    weekly_text: str = "Weekly task",
    daily_texts: list[str] | None = None,
    weekly_done: bool = False,
) -> None:
    """Seed a weekly task and up to 3 daily tasks into the session."""
    session.add(Task(task=weekly_text, done=weekly_done, kind="weekly", position=0))
    for i, text in enumerate(daily_texts or ["Daily 1", "Daily 2", "Daily 3"]):
        session.add(Task(task=text, done=(i == 0), kind="daily", position=i))
    session.commit()


# ---------------------------------------------------------------------------
# Daily reset
# ---------------------------------------------------------------------------


class TestDailyReset:
    def test_preserves_weekly_task(self, session):
        """A daily reset keeps the weekly task in place."""
        _seed_tasks(session, weekly_text="Big project")
        archive_and_reset(session, weekly_reset=False)

        tasks = session.exec(select(Task)).all()
        weekly = [t for t in tasks if t.kind == "weekly"]
        assert len(weekly) == 1
        assert weekly[0].task == "Big project"

    def test_clears_daily_tasks(self, session):
        """A daily reset replaces daily tasks with empty slots."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=False)

        daily = session.exec(
            select(Task).where(Task.kind == "daily").order_by(Task.position)
        ).all()
        assert len(daily) == 3
        assert all(t.task == "" for t in daily)
        assert all(not t.done for t in daily)

    def test_daily_tasks_have_correct_positions(self, session):
        """Three daily slots with positions 0, 1, 2 are created."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=False)

        daily = session.exec(
            select(Task).where(Task.kind == "daily").order_by(Task.position)
        ).all()
        assert [t.position for t in daily] == [0, 1, 2]

    def test_creates_archive_with_daily_content(self, session):
        """Archive markdown includes completed and uncompleted daily tasks."""
        _seed_tasks(
            session,
            weekly_text="Ship feature",
            daily_texts=["Done task", "Undone task"],
        )
        # First task is seeded with done=True, second with done=False
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert archive is not None
        assert "[x] Done task" in archive.content
        assert "[ ] Undone task" in archive.content
        assert "Ship feature" in archive.content

    def test_creates_archive_with_today_as_date(self, session):
        """Archive date is today's date."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert archive is not None
        assert archive.date == date.today()

    def test_preserves_weekly_done_state(self, session):
        """Daily reset preserves the done flag on the weekly task."""
        _seed_tasks(session, weekly_done=True)
        archive_and_reset(session, weekly_reset=False)

        weekly = session.exec(select(Task).where(Task.kind == "weekly")).first()
        assert weekly is not None
        assert weekly.done is True


# ---------------------------------------------------------------------------
# Weekly reset
# ---------------------------------------------------------------------------


class TestWeeklyReset:
    def test_clears_weekly_task(self, session):
        """A weekly reset removes the weekly task entirely."""
        _seed_tasks(session, weekly_text="Big project")
        archive_and_reset(session, weekly_reset=True)

        weekly = session.exec(select(Task).where(Task.kind == "weekly")).all()
        assert weekly == []

    def test_clears_all_daily_tasks(self, session):
        """A weekly reset replaces all daily tasks with empty slots."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=True)

        daily = session.exec(
            select(Task).where(Task.kind == "daily").order_by(Task.position)
        ).all()
        assert len(daily) == 3
        assert all(t.task == "" for t in daily)

    def test_creates_archive_for_weekly_reset(self, session):
        """Archive is created even for a weekly reset."""
        _seed_tasks(session, weekly_text="Weekly goal")
        archive_and_reset(session, weekly_reset=True)

        archive = session.exec(select(Archive)).first()
        assert archive is not None
        assert "Weekly goal" in archive.content


# ---------------------------------------------------------------------------
# Archive behaviour
# ---------------------------------------------------------------------------


class TestArchiveBehaviour:
    def test_creates_archive_on_first_reset(self, session):
        """First reset for a date creates a new Archive row."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=False)

        archives = session.exec(select(Archive)).all()
        assert len(archives) == 1

    def test_updates_existing_archive_on_second_reset(self, session):
        """Second reset on the same date updates the existing Archive row."""
        _seed_tasks(session, weekly_text="First weekly")
        archive_and_reset(session, weekly_reset=False)

        # Re-seed and reset again (same day)
        session.add(Task(task="Second weekly", done=False, kind="weekly", position=0))
        session.commit()
        archive_and_reset(session, weekly_reset=False)

        archives = session.exec(select(Archive)).all()
        assert len(archives) == 1
        assert "Second weekly" in archives[0].content

    def test_archive_includes_date_header(self, session):
        """Archive markdown starts with a date heading."""
        _seed_tasks(session)
        fixed_date = date(2026, 3, 28)
        with patch("todo.service.date") as mock_date:
            mock_date.today.return_value = fixed_date
            archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert archive is not None
        # Should contain the formatted date (Friday, March 28)
        assert "March 28" in archive.content

    def test_archive_includes_weekly_section(self, session):
        """Archive has a '## Weekly' section."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert "## Weekly" in archive.content

    def test_archive_includes_daily_section(self, session):
        """Archive has a '## Daily' section."""
        _seed_tasks(session)
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert "## Daily" in archive.content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_weekly_task_shows_none_in_archive(self, session):
        """If the weekly task text is empty, archive shows '(none)'."""
        session.add(Task(task="", done=False, kind="weekly", position=0))
        session.commit()
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert "(none)" in archive.content

    def test_no_weekly_task_shows_none_in_archive(self, session):
        """If there is no weekly task at all, archive shows '(none)'."""
        session.add(Task(task="Only daily", done=False, kind="daily", position=0))
        session.commit()
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        assert "(none)" in archive.content

    def test_daily_tasks_with_empty_text_not_in_archive(self, session):
        """Daily tasks with empty text are not included in the archive checklist."""
        session.add(Task(task="Weekly", done=False, kind="weekly", position=0))
        session.add(Task(task="", done=False, kind="daily", position=0))
        session.commit()
        archive_and_reset(session, weekly_reset=False)

        archive = session.exec(select(Archive)).first()
        # An empty task should NOT appear as a checklist item
        assert "- [ ] " not in archive.content
        assert "- [x] " not in archive.content

    def test_reset_with_no_tasks_creates_empty_archive(self, session):
        """Resetting when the DB is empty still creates an archive."""
        archive_and_reset(session, weekly_reset=False)

        archives = session.exec(select(Archive)).all()
        assert len(archives) == 1
        assert "(none)" in archives[0].content

    def test_previous_tasks_all_deleted_after_reset(self, session):
        """After reset, the old task records are removed from the database."""
        # Add tasks that shouldn't survive the reset
        for i in range(5):
            session.add(
                Task(task=f"Old task {i}", done=False, kind="daily", position=i)
            )
        session.add(Task(task="Old weekly", done=False, kind="weekly", position=0))
        session.commit()

        archive_and_reset(session, weekly_reset=True)

        remaining = session.exec(select(Task)).all()
        for t in remaining:
            assert "Old" not in t.task

    def test_exactly_three_daily_slots_created(self, session):
        """Reset always produces exactly 3 daily task slots."""
        # Start with zero tasks
        archive_and_reset(session, weekly_reset=False)

        daily = session.exec(select(Task).where(Task.kind == "daily")).all()
        assert len(daily) == 3
