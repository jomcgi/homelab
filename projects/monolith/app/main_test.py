"""Unit tests for app.main — /healthz endpoint, router registration, static mount,
and lifespan background-task lifecycle.

IMPORTANT: STATIC_DIR must be unset (or point to a non-existent path) *before*
this module is imported so that we can test the "directory missing" code path.
The StaticFiles conditional mount runs at module-import time in app/main.py.
"""

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

# Ensure no valid static directory is set so the conditional mount is skipped.
os.environ.pop("STATIC_DIR", None)

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402


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


@pytest.fixture(name="client")
def client_fixture(session):
    """TestClient with the DB dependency overridden to use in-memory SQLite."""

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /healthz endpoint
# ---------------------------------------------------------------------------


def test_healthz_returns_ok(client):
    """GET /healthz returns HTTP 200 with {"status": "ok"}."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_content_type_is_json(client):
    """GET /healthz response Content-Type is application/json."""
    response = client.get("/healthz")
    assert "application/json" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------


def test_todo_router_registered():
    """Todo router is included — routes with /api/todo prefix exist in the app."""
    paths = [getattr(route, "path", "") for route in app.routes]
    assert any(p.startswith("/api/todo") for p in paths), (
        "No /api/todo routes found; todo_router may not be included"
    )


def test_schedule_router_registered():
    """Schedule router is included — routes with /api/schedule prefix exist."""
    paths = [getattr(route, "path", "") for route in app.routes]
    assert any(p.startswith("/api/schedule") for p in paths), (
        "No /api/schedule routes found; schedule_router may not be included"
    )


def test_notes_router_registered():
    """Notes router is included — routes with /api/notes prefix exist in the app."""
    paths = [getattr(route, "path", "") for route in app.routes]
    assert any(p.startswith("/api/notes") for p in paths), (
        "No /api/notes routes found; notes_router may not be included"
    )


def test_todo_router_daily_endpoint_responds(client):
    """GET /api/todo/daily from the todo router returns a 200 response."""
    response = client.get("/api/todo/daily")
    assert response.status_code == 200


def test_schedule_router_today_endpoint_responds(client):
    """GET /api/schedule/today from the schedule router returns a 200 response."""
    response = client.get("/api/schedule/today")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Static directory mount — "dir missing" behaviour
# ---------------------------------------------------------------------------


def test_no_frontend_mount_when_static_dir_missing():
    """When STATIC_DIR doesn't point to an existing directory, no static mount is added."""
    # The module was imported without a valid STATIC_DIR (see module-level setup).
    # Verify there is no route named "frontend".
    frontend_mount = next(
        (r for r in app.routes if getattr(r, "name", None) == "frontend"),
        None,
    )
    assert frontend_mount is None, (
        "StaticFiles mount 'frontend' was unexpectedly added to the app"
    )


def test_api_routes_still_work_without_static_dir(client):
    """/healthz responds even when the static frontend directory is absent."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_path_returns_404_without_static_dir(client):
    """Without a catch-all static mount, an unknown path returns 404."""
    response = client.get("/nonexistent-page.html")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# lifespan() context manager — background task lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_creates_two_background_tasks_on_startup():
    """Lifespan creates exactly two asyncio tasks (scheduler + calendar) on startup."""
    from app.main import lifespan

    created_tasks = []

    def capture_create_task(coro, **kwargs):
        # Close the coroutine so Python doesn't warn about it never being awaited
        if hasattr(coro, "close"):
            coro.close()
        mock_task = MagicMock()
        created_tasks.append(mock_task)
        return mock_task

    with patch("asyncio.create_task", side_effect=capture_create_task):
        async with lifespan(app):
            pass

    assert len(created_tasks) == 2


@pytest.mark.asyncio
async def test_lifespan_cancels_all_tasks_on_shutdown():
    """Both background tasks are cancelled when the lifespan context exits."""
    from app.main import lifespan

    mock_tasks = []

    def capture_create_task(coro, **kwargs):
        if hasattr(coro, "close"):
            coro.close()
        mock_task = MagicMock()
        mock_tasks.append(mock_task)
        return mock_task

    with patch("asyncio.create_task", side_effect=capture_create_task):
        async with lifespan(app):
            pass

    assert len(mock_tasks) == 2
    for task in mock_tasks:
        task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_no_tasks_cancelled_before_shutdown():
    """Tasks are created but not cancelled until the lifespan context manager exits."""
    from app.main import lifespan

    mock_tasks = []

    def capture_create_task(coro, **kwargs):
        if hasattr(coro, "close"):
            coro.close()
        mock_task = MagicMock()
        mock_tasks.append(mock_task)
        return mock_task

    with patch("asyncio.create_task", side_effect=capture_create_task):
        async with lifespan(app):
            # Both tasks should exist at this point (index 0 = scheduler, index 1 = calendar)
            assert len(mock_tasks) == 2
            for task in mock_tasks:
                task.cancel.assert_not_called()

    # After lifespan exits, both must have been cancelled
    for task in mock_tasks:
        task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_scheduler_task_is_first_created():
    """The scheduler task is created before the calendar task (order matches source)."""
    from app.main import lifespan

    creation_order = []

    def capture_create_task(coro, **kwargs):
        # Identify which coroutine is being wrapped by its qualified name
        creation_order.append(getattr(coro, "__qualname__", "") or type(coro).__name__)
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=capture_create_task):
        async with lifespan(app):
            pass

    # First task should be run_scheduler, second should be calendar_loop
    assert len(creation_order) == 2
    assert "run_scheduler" in creation_order[0]
    assert "calendar_loop" in creation_order[1]
