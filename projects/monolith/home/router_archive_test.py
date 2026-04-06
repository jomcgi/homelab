"""Tests for the get_archive() 200 happy path in home/router.py.

Existing router_test.py covers:
- 404 (archive not found)
- 400 (invalid date format)
- indirect 200 via reset (test_reset_creates_archive)

This file adds:
- Direct 200 happy path: Archive row inserted into DB, endpoint returns correct JSON
- Response contains both 'date' and 'content' keys with correct values
- Endpoint handles archives with multi-line content correctly
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from home.models import Archive


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # SQLite doesn't support schemas (e.g. "home.archives"), so strip them
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


def test_get_archive_returns_200_with_existing_archive(client, session):
    """GET /api/home/archive/{date} returns 200 when an Archive exists for that date."""
    archive_date = date(2024, 1, 15)
    archive = Archive(date=archive_date, content="## Weekly\n- [ ] Ship feature\n## Daily\n- [x] Write tests")
    session.add(archive)
    session.commit()

    response = client.get("/api/home/archive/2024-01-15")

    assert response.status_code == 200


def test_get_archive_returns_correct_date_in_response(client, session):
    """GET /api/home/archive/{date} response includes the 'date' key with ISO-format string."""
    archive_date = date(2024, 3, 22)
    archive = Archive(date=archive_date, content="Some content")
    session.add(archive)
    session.commit()

    response = client.get("/api/home/archive/2024-03-22")

    assert response.status_code == 200
    data = response.json()
    assert "date" in data
    assert data["date"] == "2024-03-22"


def test_get_archive_returns_correct_content_in_response(client, session):
    """GET /api/home/archive/{date} response includes the 'content' key with stored text."""
    content = "## Weekly\n- [x] Deploy service\n## Daily\n- [ ] Review PR"
    archive_date = date(2024, 6, 10)
    archive = Archive(date=archive_date, content=content)
    session.add(archive)
    session.commit()

    response = client.get("/api/home/archive/2024-06-10")

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert data["content"] == content


def test_get_archive_response_has_exactly_two_keys(client, session):
    """GET /api/home/archive/{date} response dict has exactly 'date' and 'content' keys."""
    archive_date = date(2024, 7, 4)
    archive = Archive(date=archive_date, content="Independence Day tasks")
    session.add(archive)
    session.commit()

    response = client.get("/api/home/archive/2024-07-04")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"date", "content"}


def test_get_archive_returns_multiline_content_intact(client, session):
    """GET /api/home/archive/{date} preserves multiline content including newlines and markdown."""
    multiline_content = (
        "## Weekly\n"
        "- [x] Ship feature\n"
        "- [ ] Write docs\n"
        "\n"
        "## Daily\n"
        "- [x] Standup\n"
        "- [x] Code review\n"
        "- [ ] Deploy\n"
    )
    archive_date = date(2024, 8, 20)
    archive = Archive(date=archive_date, content=multiline_content)
    session.add(archive)
    session.commit()

    response = client.get("/api/home/archive/2024-08-20")

    assert response.status_code == 200
    assert response.json()["content"] == multiline_content


def test_get_archive_with_empty_content(client, session):
    """GET /api/home/archive/{date} works when the archive content is an empty string."""
    archive_date = date(2024, 9, 1)
    archive = Archive(date=archive_date, content="")
    session.add(archive)
    session.commit()

    response = client.get("/api/home/archive/2024-09-01")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2024-09-01"
    assert data["content"] == ""


def test_get_archive_different_dates_return_different_content(client, session):
    """Two archives with different dates each return their own content."""
    session.add(Archive(date=date(2024, 10, 1), content="October first content"))
    session.add(Archive(date=date(2024, 10, 2), content="October second content"))
    session.commit()

    resp1 = client.get("/api/home/archive/2024-10-01")
    resp2 = client.get("/api/home/archive/2024-10-02")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["content"] == "October first content"
    assert resp2.json()["content"] == "October second content"
