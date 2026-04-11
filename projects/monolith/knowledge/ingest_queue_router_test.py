"""Tests for the ingest queue API endpoint."""

import pytest

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from knowledge.ingest_queue import IngestQueueItem


@pytest.fixture
def session():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(session):
    from app.main import app
    from app.db import get_session

    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_queue_ingest_youtube(client, session):
    resp = client.post(
        "/api/knowledge/ingest",
        json={
            "url": "https://www.youtube.com/watch?v=abc123",
            "source_type": "youtube",
        },
    )
    assert resp.status_code == 201
    assert resp.json() == {"queued": True}

    items = session.query(IngestQueueItem).all()
    assert len(items) == 1
    assert items[0].url == "https://www.youtube.com/watch?v=abc123"
    assert items[0].source_type == "youtube"
    assert items[0].status == "pending"


def test_queue_ingest_webpage(client, session):
    resp = client.post(
        "/api/knowledge/ingest",
        json={"url": "https://example.com/blog/post", "source_type": "webpage"},
    )
    assert resp.status_code == 201


def test_queue_ingest_empty_url_rejected(client):
    resp = client.post(
        "/api/knowledge/ingest",
        json={"url": "", "source_type": "youtube"},
    )
    assert resp.status_code == 400


def test_queue_ingest_invalid_source_type(client):
    resp = client.post(
        "/api/knowledge/ingest",
        json={"url": "https://example.com", "source_type": "pdf"},
    )
    assert resp.status_code == 422
