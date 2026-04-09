"""Extra coverage tests for home.router — edge cases and boundary conditions."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from home.models import Archive, Task


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


@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PUT /api/home — update_todo edge cases
# ---------------------------------------------------------------------------


class TestUpdateTodoExtra:
    def test_put_with_empty_daily_list_stores_no_daily_tasks(self, client, session):
        """PUT with daily=[] stores zero daily tasks (no forced minimum)."""
        todo = {
            "weekly": {"task": "Weekly goal", "done": False},
            "daily": [],
        }
        response = client.put("/api/home", json=todo)
        assert response.status_code == 200

        tasks = session.exec(select(Task).where(Task.kind == "daily")).all()
        assert len(tasks) == 0

    def test_put_with_empty_daily_list_weekly_still_stored(self, client, session):
        """PUT with daily=[] stores the weekly task even without daily tasks."""
        todo = {
            "weekly": {"task": "Only goal", "done": True},
            "daily": [],
        }
        client.put("/api/home", json=todo)

        weekly = session.exec(select(Task).where(Task.kind == "weekly")).first()
        assert weekly is not None
        assert weekly.task == "Only goal"
        assert weekly.done is True

    def test_put_replaces_existing_tasks_completely(self, client, session):
        """PUT removes all previous tasks and stores only the new ones."""
        # Seed 5 daily tasks
        for i in range(5):
            session.add(Task(task=f"old-{i}", done=False, kind="daily", position=i))
        session.commit()

        todo = {
            "weekly": {"task": "W", "done": False},
            "daily": [{"task": "new-0", "done": False}],
        }
        client.put("/api/home", json=todo)

        daily = session.exec(select(Task).where(Task.kind == "daily")).all()
        assert len(daily) == 1
        assert daily[0].task == "new-0"

    def test_put_with_malformed_json_returns_422(self, client):
        """Sending non-JSON body to PUT returns 422 Unprocessable Entity."""
        response = client.put(
            "/api/home",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_put_with_missing_weekly_field_returns_422(self, client):
        """Body missing the 'weekly' field fails Pydantic validation (422)."""
        response = client.put(
            "/api/home",
            json={"daily": []},
        )
        assert response.status_code == 422

    def test_put_daily_positions_are_sequential(self, client, session):
        """Daily tasks are stored with positions matching their list order."""
        todo = {
            "weekly": {"task": "", "done": False},
            "daily": [
                {"task": "first", "done": False},
                {"task": "second", "done": True},
                {"task": "third", "done": False},
            ],
        }
        client.put("/api/home", json=todo)

        daily = session.exec(
            select(Task).where(Task.kind == "daily").order_by(Task.position)
        ).all()
        assert [t.task for t in daily] == ["first", "second", "third"]
        assert [t.position for t in daily] == [0, 1, 2]


# ---------------------------------------------------------------------------
# GET /api/home/dates — rolling window
# ---------------------------------------------------------------------------


class TestGetDatesExtra:
    def test_dates_within_rolling_window_are_included(self, client, session):
        """Archive dates within the 14-day rolling window are included in the list."""
        today = date.today()
        for delta in (1, 7, 13):
            d = today - timedelta(days=delta)
            session.add(Archive(date=d, content=f"archive for {d}"))
        session.commit()

        response = client.get("/api/home/dates")
        assert response.status_code == 200
        dates = response.json()

        for delta in (1, 7, 13):
            d = (today - timedelta(days=delta)).isoformat()
            assert d in dates

    def test_dates_outside_rolling_window_are_excluded(self, client, session):
        """Archive dates older than 14 days are excluded from the list."""
        too_old = date.today() - timedelta(days=20)
        session.add(Archive(date=too_old, content="old archive"))
        session.commit()

        response = client.get("/api/home/dates")
        assert response.status_code == 200
        dates = response.json()

        assert too_old.isoformat() not in dates

    def test_dates_list_always_ends_with_today(self, client):
        """The dates list always includes today even if there is no archive yet."""
        response = client.get("/api/home/dates")
        dates = response.json()
        assert dates[-1] == date.today().isoformat()


# ---------------------------------------------------------------------------
# GET /api/home — combined todo with empty DB
# ---------------------------------------------------------------------------


class TestGetTodoExtra:
    def test_get_todo_empty_db_returns_defaults(self, client):
        """With no tasks in DB, GET /api/home returns empty weekly + 3 empty daily."""
        response = client.get("/api/home")
        assert response.status_code == 200
        data = response.json()
        assert data["weekly"]["task"] == ""
        assert data["weekly"]["done"] is False
        assert len(data["daily"]) == 3
        assert all(d["task"] == "" for d in data["daily"])

    def test_get_weekly_with_task_returns_it(self, client, session):
        """GET /api/home/weekly returns the weekly task when one exists."""
        session.add(Task(task="Review proposal", done=True, kind="weekly", position=0))
        session.commit()

        response = client.get("/api/home/weekly")
        assert response.status_code == 200
        data = response.json()
        assert data["task"] == "Review proposal"
        assert data["done"] is True

    def test_get_daily_returns_tasks_in_position_order(self, client, session):
        """GET /api/home/daily returns tasks sorted by position."""
        session.add(Task(task="C", done=False, kind="daily", position=2))
        session.add(Task(task="A", done=False, kind="daily", position=0))
        session.add(Task(task="B", done=False, kind="daily", position=1))
        session.commit()

        response = client.get("/api/home/daily")
        assert response.status_code == 200
        data = response.json()
        assert [d["task"] for d in data] == ["A", "B", "C"]
