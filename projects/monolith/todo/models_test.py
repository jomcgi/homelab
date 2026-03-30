"""Unit tests for todo/models.py — Task and Archive field defaults, table metadata."""

from datetime import date

import pytest
from sqlmodel import Field, Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from todo.models import Archive, Task


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


# ---------------------------------------------------------------------------
# Task model — field defaults
# ---------------------------------------------------------------------------


class TestTaskDefaults:
    def test_done_defaults_to_false(self):
        """Task.done defaults to False when not provided."""
        task = Task(task="Write tests")
        assert task.done is False

    def test_kind_defaults_to_daily(self):
        """Task.kind defaults to 'daily' when not provided."""
        task = Task(task="Write tests")
        assert task.kind == "daily"

    def test_position_defaults_to_zero(self):
        """Task.position defaults to 0 when not provided."""
        task = Task(task="Write tests")
        assert task.position == 0

    def test_task_text_defaults_to_empty_string(self):
        """Task.task defaults to '' when not provided."""
        task = Task()
        assert task.task == ""

    def test_id_defaults_to_none(self):
        """Task.id is None before the row is persisted (auto-assigned by DB)."""
        task = Task(task="Write tests")
        assert task.id is None

    def test_explicit_values_override_defaults(self):
        """Explicitly provided values override all defaults."""
        task = Task(task="Weekly goal", done=True, kind="weekly", position=3)
        assert task.task == "Weekly goal"
        assert task.done is True
        assert task.kind == "weekly"
        assert task.position == 3

    def test_task_persisted_and_retrieved_with_defaults(self, session):
        """A Task row created with defaults round-trips through the DB correctly."""
        session.add(Task(task="Simple task"))
        session.commit()

        result = session.exec(select(Task)).first()
        assert result is not None
        assert result.done is False
        assert result.kind == "daily"
        assert result.position == 0

    def test_id_assigned_after_persist(self, session):
        """Task.id is assigned by the database upon insertion."""
        task = Task(task="Persisted task")
        session.add(task)
        session.commit()
        session.refresh(task)
        assert task.id is not None
        assert isinstance(task.id, int)


# ---------------------------------------------------------------------------
# Task model — table metadata
# ---------------------------------------------------------------------------


class TestTaskTableMetadata:
    def test_table_name_is_tasks(self):
        """Task.__tablename__ is 'tasks'."""
        assert Task.__tablename__ == "tasks"

    def test_schema_is_todo(self):
        """Task table lives in the 'todo' schema."""
        args = Task.__table_args__
        assert isinstance(args, dict)
        assert args.get("schema") == "todo"


# ---------------------------------------------------------------------------
# Archive model — field defaults and types
# ---------------------------------------------------------------------------


class TestArchiveDefaults:
    def test_id_defaults_to_none(self):
        """Archive.id is None before insertion."""
        archive = Archive(date=date.today(), content="# Archive")
        assert archive.id is None

    def test_id_assigned_after_persist(self, session):
        """Archive.id is assigned by the database upon insertion."""
        archive = Archive(date=date.today(), content="# Archive")
        session.add(archive)
        session.commit()
        session.refresh(archive)
        assert archive.id is not None
        assert isinstance(archive.id, int)

    def test_date_field_accepts_date_object(self):
        """Archive.date accepts a datetime.date value."""
        d = date(2026, 3, 28)
        archive = Archive(date=d, content="# Archive")
        assert archive.date == d

    def test_content_field_stores_markdown_string(self):
        """Archive.content stores arbitrary markdown text."""
        md = "# Friday, March 28\n\n## Weekly\nShip feature\n\n## Daily\n- [x] Done"
        archive = Archive(date=date.today(), content=md)
        assert archive.content == md

    def test_archive_persisted_and_retrieved(self, session):
        """Archive round-trips through SQLite with correct field values."""
        target_date = date(2026, 1, 15)
        content = "# January 15\n\n## Weekly\n(none)\n"
        session.add(Archive(date=target_date, content=content))
        session.commit()

        result = session.exec(select(Archive)).first()
        assert result is not None
        assert result.date == target_date
        assert result.content == content


# ---------------------------------------------------------------------------
# Archive model — table metadata
# ---------------------------------------------------------------------------


class TestArchiveTableMetadata:
    def test_table_name_is_archives(self):
        """Archive.__tablename__ is 'archives'."""
        assert Archive.__tablename__ == "archives"

    def test_schema_is_todo(self):
        """Archive table lives in the 'todo' schema."""
        args = Archive.__table_args__
        assert isinstance(args, dict)
        assert args.get("schema") == "todo"


# ---------------------------------------------------------------------------
# Schema-stripping fixture — verify SQLite compatibility
# ---------------------------------------------------------------------------


class TestSQLiteSchemaCompatibility:
    def test_tables_created_in_sqlite_without_error(self, session):
        """Both Task and Archive tables can be created in SQLite (schema stripped)."""
        # session fixture already created tables; verify we can query both
        tasks = session.exec(select(Task)).all()
        archives = session.exec(select(Archive)).all()
        assert tasks == []
        assert archives == []

    def test_both_models_insertable_in_same_session(self, session):
        """Task and Archive rows can coexist in the same SQLite database."""
        session.add(Task(task="Do something", kind="daily", position=0))
        session.add(Archive(date=date.today(), content="# Today"))
        session.commit()

        assert len(session.exec(select(Task)).all()) == 1
        assert len(session.exec(select(Archive)).all()) == 1
