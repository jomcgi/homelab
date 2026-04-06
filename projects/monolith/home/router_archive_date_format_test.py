"""Tests for get_archive() date serialization in home/router.py.

Covers a specific untested path: the ``archive.date.isoformat()`` call in
``get_archive()`` returns an ISO 8601 string (``YYYY-MM-DD``), not some
other string representation of the date.  The router code is:

    return {"date": archive.date.isoformat(), "content": archive.content}

Existing tests in router_archive_test.py and router_test.py verify the 200
status code and content values but don't explicitly assert that the date string
format is ISO 8601 (which differs from Python's ``str(date)`` in edge cases
only on some platforms).  These tests add explicit format-shape assertions and
cover scenarios such as a leap-day archive and a year-boundary date.
"""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from home.models import Archive


# ---------------------------------------------------------------------------
# Fixtures (same pattern as router_test.py and router_archive_test.py)
# ---------------------------------------------------------------------------


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
# Date serialisation format
# ---------------------------------------------------------------------------

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_get_archive_date_field_is_iso_format_string(client, session):
    """The 'date' field in the response matches the pattern YYYY-MM-DD (ISO 8601).

    Ensures ``archive.date.isoformat()`` (not ``str(archive.date)``) is used,
    as the isoformat() method is the guaranteed stable source of that format.
    """
    archive_date = date(2023, 11, 5)
    session.add(Archive(date=archive_date, content="Sunday content"))
    session.commit()

    response = client.get("/api/home/archive/2023-11-05")

    assert response.status_code == 200
    data = response.json()
    assert _ISO_DATE_RE.match(data["date"]), (
        f"'date' field {data['date']!r} does not match ISO 8601 pattern YYYY-MM-DD"
    )


def test_get_archive_date_field_matches_request_date_exactly(client, session):
    """The 'date' field in the response equals the date used in the URL path."""
    archive_date = date(2025, 6, 15)
    session.add(Archive(date=archive_date, content="Mid-June content"))
    session.commit()

    response = client.get("/api/home/archive/2025-06-15")

    assert response.status_code == 200
    assert response.json()["date"] == "2025-06-15"


def test_get_archive_leap_day_returns_200(client, session):
    """An archive stored on a leap day (Feb 29) is retrieved correctly."""
    leap_day = date(2024, 2, 29)  # 2024 is a leap year
    session.add(Archive(date=leap_day, content="Leap day content"))
    session.commit()

    response = client.get("/api/home/archive/2024-02-29")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2024-02-29"
    assert data["content"] == "Leap day content"


def test_get_archive_year_boundary_date(client, session):
    """An archive on the last day of a year (Dec 31) is retrieved correctly."""
    year_end = date(2023, 12, 31)
    session.add(Archive(date=year_end, content="Year end tasks"))
    session.commit()

    response = client.get("/api/home/archive/2023-12-31")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2023-12-31"
    assert data["content"] == "Year end tasks"


def test_get_archive_response_content_type_is_json(client, session):
    """GET /api/home/archive/{date} returns Content-Type: application/json on the 200 path."""
    archive_date = date(2024, 4, 1)
    session.add(Archive(date=archive_date, content="April Fools tasks"))
    session.commit()

    response = client.get("/api/home/archive/2024-04-01")

    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", ""), (
        "Expected application/json Content-Type for archive response"
    )
