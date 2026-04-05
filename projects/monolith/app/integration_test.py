"""Integration tests for the full monolith FastAPI application.

Boots the complete app via TestClient with all external dependencies mocked:
- Database: in-memory SQLite with StaticPool
- Lifespan: asyncio.create_task patched to avoid real background tasks
- Discord: DISCORD_BOT_TOKEN unset
- STATIC_DIR: unset (no static mount)
- iCal feed: ICAL_FEED_URL unset (poll_calendar is a no-op)
- Vault MCP: httpx POST mocked to return {"id": "test-note"}
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

# Ensure no static directory or Discord token so module-level behaviour is
# deterministic when app.main is imported.
os.environ.pop("STATIC_DIR", None)
os.environ.pop("DISCORD_BOT_TOKEN", None)
os.environ.pop("ICAL_FEED_URL", None)

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session — strips schemas since SQLite doesn't support them."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas: dict[str, str] = {}
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


def _make_create_task_patcher():
    """Return a side_effect function that closes coroutines instead of scheduling them."""

    def capture_create_task(coro, **kwargs):
        if hasattr(coro, "close"):
            coro.close()
        mock_task = MagicMock()
        return mock_task

    return capture_create_task


@pytest.fixture(name="client")
def client_fixture(session):
    """TestClient with:
    - DB dependency overridden to use in-memory SQLite
    - asyncio.create_task patched to prevent real background tasks
    - Vault httpx POST mocked
    """

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override

    mock_vault_response = MagicMock()
    mock_vault_response.json.return_value = {"id": "test-note"}
    mock_vault_response.raise_for_status = MagicMock()

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)
    mock_async_client.post = AsyncMock(return_value=mock_vault_response)

    with patch("asyncio.create_task", side_effect=_make_create_task_patcher()):
        with patch("notes.service.httpx.AsyncClient", return_value=mock_async_client):
            client = TestClient(app, raise_server_exceptions=False)
            yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_healthz_returns_ok(client):
    """GET /healthz → 200, {"status": "ok"}."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Home routes — individual endpoints
# ---------------------------------------------------------------------------


def test_get_daily_returns_list(client):
    """GET /api/home/daily → 200, list of TaskResponse."""
    response = client.get("/api/home/daily")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert all("task" in item and "done" in item for item in data)


def test_get_weekly_returns_task_response(client):
    """GET /api/home/weekly → 200, TaskResponse."""
    response = client.get("/api/home/weekly")
    assert response.status_code == 200
    data = response.json()
    assert "task" in data
    assert "done" in data


def test_get_home_returns_todo_data(client):
    """GET /api/home → 200, TodoData with weekly + daily keys."""
    response = client.get("/api/home")
    assert response.status_code == 200
    data = response.json()
    assert "weekly" in data
    assert "daily" in data
    assert isinstance(data["daily"], list)


def test_get_dates_returns_list(client):
    """GET /api/home/dates → 200, list of date strings including today."""
    response = client.get("/api/home/dates")
    assert response.status_code == 200
    dates = response.json()
    assert isinstance(dates, list)
    assert date.today().isoformat() in dates


def test_get_archive_not_found(client):
    """GET /api/home/archive/{date} → 404 when no archive exists."""
    response = client.get("/api/home/archive/2020-01-01")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Home routes — PUT then verify
# ---------------------------------------------------------------------------


def test_put_creates_tasks_verified_by_get(client):
    """PUT /api/home → 200; subsequent GET /api/home reflects saved tasks."""
    todo = {
        "weekly": {"task": "Ship the release", "done": False},
        "daily": [
            {"task": "Write integration test", "done": True},
            {"task": "Review PR", "done": False},
            {"task": "Deploy to prod", "done": False},
        ],
    }
    put_response = client.put("/api/home", json=todo)
    assert put_response.status_code == 200

    get_response = client.get("/api/home")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["weekly"]["task"] == "Ship the release"
    assert data["weekly"]["done"] is False
    assert len(data["daily"]) == 3
    assert data["daily"][0]["task"] == "Write integration test"
    assert data["daily"][0]["done"] is True


# ---------------------------------------------------------------------------
# Reset routes
# ---------------------------------------------------------------------------


def test_reset_daily_returns_200(client):
    """POST /api/home/reset/daily → 200."""
    response = client.post("/api/home/reset/daily")
    assert response.status_code == 200


def test_reset_weekly_returns_200(client):
    """POST /api/home/reset/weekly → 200."""
    response = client.post("/api/home/reset/weekly")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Schedule route
# ---------------------------------------------------------------------------


def test_get_schedule_today_returns_list(client):
    """GET /api/schedule/today → 200, list (may be empty)."""
    response = client.get("/api/schedule/today")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Notes route
# ---------------------------------------------------------------------------


def test_post_note_returns_201(client):
    """POST /api/notes with content → 201 and vault response body."""
    response = client.post("/api/notes", json={"content": "test note"})
    assert response.status_code == 201
    assert response.json() == {"id": "test-note"}


def test_post_note_empty_content_returns_400(client):
    """POST /api/notes with empty content → 400."""
    response = client.post("/api/notes", json={"content": ""})
    assert response.status_code == 400


def test_post_note_whitespace_content_returns_400(client):
    """POST /api/notes with whitespace-only content → 400."""
    response = client.post("/api/notes", json={"content": "   "})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# CRUD flow: PUT → GET → reset daily → GET archive dates
# ---------------------------------------------------------------------------


def test_reset_weekly_clears_weekly_task(client):
    """POST /api/home/reset/weekly actually clears the weekly task text."""
    client.put(
        "/api/home",
        json={"weekly": {"task": "Weekly goal", "done": False}, "daily": []},
    )
    resp = client.post("/api/home/reset/weekly")
    assert resp.status_code == 200
    data = client.get("/api/home").json()
    assert data["weekly"]["task"] == ""


def test_get_archive_invalid_date_returns_400(client):
    """GET /api/home/archive/{date} with invalid date string → 400."""
    assert client.get("/api/home/archive/not-a-date").status_code == 400


def test_crud_flow_put_get_reset_archive(client):
    """Full CRUD flow: PUT tasks → GET to verify → reset daily → GET archive dates."""
    # 1. PUT tasks
    todo = {
        "weekly": {"task": "Weekly goal", "done": False},
        "daily": [
            {"task": "Daily task A", "done": True},
            {"task": "Daily task B", "done": False},
            {"task": "Daily task C", "done": False},
        ],
    }
    put_resp = client.put("/api/home", json=todo)
    assert put_resp.status_code == 200

    # 2. GET to verify tasks are persisted
    get_resp = client.get("/api/home")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["weekly"]["task"] == "Weekly goal"
    assert data["daily"][0]["task"] == "Daily task A"
    assert data["daily"][0]["done"] is True

    # 3. Reset daily (archives today's state, preserves weekly)
    reset_resp = client.post("/api/home/reset/daily")
    assert reset_resp.status_code == 200

    # 4. After reset: weekly preserved, daily slots cleared
    after_resp = client.get("/api/home")
    assert after_resp.status_code == 200
    after_data = after_resp.json()
    assert after_data["weekly"]["task"] == "Weekly goal"
    assert all(d["task"] == "" for d in after_data["daily"])

    # 5. Archive dates should include today
    dates_resp = client.get("/api/home/dates")
    assert dates_resp.status_code == 200
    assert date.today().isoformat() in dates_resp.json()

    # 6. GET archive for today should return content with the tasks we put
    today = date.today().isoformat()
    archive_resp = client.get(f"/api/home/archive/{today}")
    assert archive_resp.status_code == 200
    content = archive_resp.json()["content"]
    assert "Weekly goal" in content
    assert "Daily task A" in content
