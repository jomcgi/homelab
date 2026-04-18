"""Tests for the gardener's daily/weekly task consolidation."""

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.gardener import Gardener, GardenStats
from knowledge.models import Note


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
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


def _make_task(
    session: Session,
    note_id: str,
    title: str = "Task",
    *,
    status: str = "active",
    due: str | None = None,
    size: str | None = None,
    blocked_by: list[str] | None = None,
) -> Note:
    """Create a task note in the DB."""
    rel_path = f"_processed/{note_id}.md"
    extra: dict = {"status": status}
    if due is not None:
        extra["due"] = due
    if size is not None:
        extra["size"] = size
    if blocked_by is not None:
        extra["blocked-by"] = blocked_by
    note = Note(
        note_id=note_id,
        path=rel_path,
        title=title,
        content_hash=f"hash-{note_id}",
        type="active",
        tags=[],
        extra=extra,
        indexed_at=datetime.now(timezone.utc),
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


FAKE_TODAY = date(2026, 4, 17)  # Thursday, week W16


class TestGeneratesDailyNote:
    @patch("knowledge.gardener.date")
    def test_generates_daily_note(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        _make_task(session, "task-today", "Task Today", due="2026-04-17", size="medium")
        _make_task(
            session, "task-overdue", "Task Overdue", due="2026-04-15", size="small"
        )

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        count = gardener._consolidate_task_views()

        daily_path = tmp_path / "_processed" / "tasks-daily-2026-04-17.md"
        assert daily_path.exists()
        content = daily_path.read_text()

        assert "id: tasks-daily-2026-04-17" in content
        assert 'title: "Daily Tasks' in content
        assert "type: fact" in content
        assert "tags: [tasks, daily]" in content
        assert "**task-today**" in content
        assert "**task-overdue**" in content
        assert count >= 1  # at least daily was generated


class TestGeneratesWeeklyNote:
    @patch("knowledge.gardener.date")
    def test_generates_weekly_note(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        # Monday of this week
        _make_task(session, "task-mon", "Monday Task", due="2026-04-13", size="small")
        # Thursday (today)
        _make_task(
            session, "task-thu", "Thursday Task", due="2026-04-17", size="medium"
        )

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        gardener._consolidate_task_views()

        weekly_path = tmp_path / "_processed" / "tasks-weekly-2026-W16.md"
        assert weekly_path.exists()
        content = weekly_path.read_text()

        assert "id: tasks-weekly-2026-W16" in content
        assert 'title: "Weekly Tasks' in content
        assert "type: fact" in content
        assert "tags: [tasks, weekly]" in content
        # Grouped by day
        assert "2026-04-13" in content
        assert "2026-04-17" in content


class TestSkipsTasksWithoutDueDate:
    @patch("knowledge.gardener.date")
    def test_skips_tasks_without_due_date(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        _make_task(session, "task-no-due", "No Due Date", size="small")
        _make_task(session, "task-due", "Has Due", due="2026-04-17", size="small")

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        gardener._consolidate_task_views()

        daily_path = tmp_path / "_processed" / "tasks-daily-2026-04-17.md"
        content = daily_path.read_text()
        assert "task-no-due" not in content
        assert "task-due" in content


class TestSortsBySize:
    @patch("knowledge.gardener.date")
    def test_sorts_by_size(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        _make_task(session, "task-large", "Large Task", due="2026-04-17", size="large")
        _make_task(session, "task-small", "Small Task", due="2026-04-17", size="small")
        _make_task(
            session, "task-medium", "Medium Task", due="2026-04-17", size="medium"
        )
        _make_task(
            session, "task-unknown", "Unknown Task", due="2026-04-17", size="unknown"
        )
        _make_task(session, "task-nosize", "No Size Task", due="2026-04-17")

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        gardener._consolidate_task_views()

        daily_path = tmp_path / "_processed" / "tasks-daily-2026-04-17.md"
        content = daily_path.read_text()

        # Find positions of each task in the content
        pos_small = content.index("task-small")
        pos_medium = content.index("task-medium")
        pos_large = content.index("task-large")
        pos_unknown = content.index("task-unknown")
        pos_nosize = content.index("task-nosize")

        assert pos_small < pos_medium < pos_large < pos_unknown < pos_nosize


class TestMarksOverdue:
    @patch("knowledge.gardener.date")
    def test_marks_overdue(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        _make_task(
            session, "task-overdue", "Overdue Task", due="2026-04-15", size="small"
        )
        _make_task(session, "task-today", "Today Task", due="2026-04-17", size="small")

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        gardener._consolidate_task_views()

        daily_path = tmp_path / "_processed" / "tasks-daily-2026-04-17.md"
        content = daily_path.read_text()

        # Overdue task should have the marker
        lines = content.split("\n")
        for line in lines:
            if "task-overdue" in line:
                assert "overdue" in line
            if "task-today" in line:
                assert "overdue" not in line


class TestMarksBlocked:
    @patch("knowledge.gardener.date")
    def test_marks_blocked(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        _make_task(
            session,
            "task-blocked",
            "Blocked Task",
            due="2026-04-17",
            size="medium",
            status="blocked",
            blocked_by=["some-dependency"],
        )

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        gardener._consolidate_task_views()

        daily_path = tmp_path / "_processed" / "tasks-daily-2026-04-17.md"
        content = daily_path.read_text()

        assert "blocked by some-dependency" in content


class TestNoSessionIsNoop:
    def test_no_session_is_noop(self, tmp_path):
        gardener = Gardener(vault_root=tmp_path, session=None)
        (tmp_path / "_processed").mkdir(exist_ok=True)

        count = gardener._consolidate_task_views()

        assert count == 0
        # No files should be generated
        files = list((tmp_path / "_processed").glob("tasks-*.md"))
        assert len(files) == 0


class TestWiredIntoRun:
    @pytest.mark.asyncio
    @patch("knowledge.gardener.date")
    async def test_wired_into_run(self, mock_date, tmp_path, session):
        mock_date.today.return_value = FAKE_TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        gardener = Gardener(vault_root=tmp_path, session=session)
        (tmp_path / "_processed").mkdir(exist_ok=True)
        (tmp_path / "_raw").mkdir(exist_ok=True)

        mock_consolidate = AsyncMock(return_value=5)
        # _consolidate_task_views is sync, so use a regular mock
        from unittest.mock import MagicMock

        mock_consolidate = MagicMock(return_value=5)
        gardener._consolidate_task_views = mock_consolidate  # type: ignore[method-assign]

        stats = await gardener.run()

        mock_consolidate.assert_called_once()
        assert stats.consolidated == 5
