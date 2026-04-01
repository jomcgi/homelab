from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
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
    # SQLite doesn't support schemas (e.g. "home.tasks"), so strip them
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


@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_weekly_empty(client):
    response = client.get("/api/home/weekly")
    assert response.status_code == 200
    assert response.json() == {"task": "", "done": False}


def test_get_daily_empty(client):
    response = client.get("/api/home/daily")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(d["task"] == "" for d in data)


def test_put_and_get_todo(client):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [
            {"task": "Write tests", "done": True},
            {"task": "Review PR", "done": False},
        ],
    }
    response = client.put("/api/home", json=todo)
    assert response.status_code == 200

    response = client.get("/api/home")
    assert response.status_code == 200
    data = response.json()
    assert data["weekly"]["task"] == "Ship feature"
    assert len(data["daily"]) == 2
    assert data["daily"][0]["done"] is True


def test_reset_daily_preserves_weekly(client, session):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [{"task": "Write tests", "done": True}],
    }
    client.put("/api/home", json=todo)

    response = client.post("/api/home/reset/daily")
    assert response.status_code == 200

    data = client.get("/api/home").json()
    assert data["weekly"]["task"] == "Ship feature"
    assert all(d["task"] == "" for d in data["daily"])


def test_reset_weekly_clears_all(client, session):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [{"task": "Write tests", "done": True}],
    }
    client.put("/api/home", json=todo)

    response = client.post("/api/home/reset/weekly")
    assert response.status_code == 200

    data = client.get("/api/home").json()
    assert data["weekly"]["task"] == ""
    assert all(d["task"] == "" for d in data["daily"])


def test_reset_creates_archive(client, session):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [{"task": "Write tests", "done": True}],
    }
    client.put("/api/home", json=todo)
    client.post("/api/home/reset/daily")

    today = date.today().isoformat()
    response = client.get(f"/api/home/archive/{today}")
    assert response.status_code == 200
    assert "Ship feature" in response.json()["content"]
    assert "[x] Write tests" in response.json()["content"]


def test_get_dates_includes_today(client):
    response = client.get("/api/home/dates")
    assert response.status_code == 200
    dates = response.json()
    assert date.today().isoformat() in dates


def test_get_archive_not_found(client):
    response = client.get("/api/home/archive/2020-01-01")
    assert response.status_code == 404


def test_get_archive_invalid_date(client):
    response = client.get("/api/home/archive/not-a-date")
    assert response.status_code == 400
