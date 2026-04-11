"""Tests for the dead letter API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from knowledge.gardener import Gardener
from knowledge.models import AtomRawProvenance, RawInput


@pytest.fixture
def session():
    from sqlmodel.pool import StaticPool

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
        with Session(engine) as s:
            yield s
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


@pytest.fixture
def client(session):
    from app.main import app
    from app.db import get_session

    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_raw(
    session: Session,
    *,
    raw_id: str = "raw-1",
    path: str = "raw/test.md",
    source: str = "test",
) -> RawInput:
    raw = RawInput(
        raw_id=raw_id,
        path=path,
        source=source,
        content="test content",
        content_hash="abc123",
    )
    session.add(raw)
    session.commit()
    session.refresh(raw)
    return raw


def _make_dead_letter(
    session: Session, raw: RawInput, *, error: str = "boom", retry_count: int = 3
) -> AtomRawProvenance:
    prov = AtomRawProvenance(
        raw_fk=raw.id,
        derived_note_id="failed",
        gardener_version="test-v1",
        error=error,
        retry_count=retry_count,
    )
    session.add(prov)
    session.commit()
    session.refresh(prov)
    return prov


class TestListDeadLetters:
    def test_returns_exhausted_raws(self, client, session):
        raw = _make_raw(session)
        prov = _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)

        resp = client.get("/api/knowledge/dead-letter")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == raw.id
        assert item["path"] == raw.path
        assert item["source"] == raw.source
        assert item["error"] == "boom"
        assert item["retry_count"] == Gardener._MAX_RETRIES

    def test_excludes_retriable(self, client, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=1)

        resp = client.get("/api/knowledge/dead-letter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    def test_empty_when_no_failures(self, client, session):
        resp = client.get("/api/knowledge/dead-letter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []


class TestReplayDeadLetter:
    def test_replay_deletes_provenance(self, client, session):
        raw = _make_raw(session)
        prov = _make_dead_letter(session, raw)

        resp = client.post(f"/api/knowledge/dead-letter/{raw.id}/replay")
        assert resp.status_code == 200
        assert resp.json() == {"replayed": True}

        # Provenance row should be deleted
        remaining = session.get(AtomRawProvenance, prov.id)
        assert remaining is None

    def test_404_for_unknown_raw_id(self, client, session):
        resp = client.post("/api/knowledge/dead-letter/9999/replay")
        assert resp.status_code == 404

    def test_404_for_non_dead_lettered_raw(self, client, session):
        raw = _make_raw(session)
        # Raw exists but has no dead-letter provenance
        resp = client.post(f"/api/knowledge/dead-letter/{raw.id}/replay")
        assert resp.status_code == 404
