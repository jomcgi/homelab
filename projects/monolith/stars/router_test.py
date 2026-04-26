"""Integration tests for stars.router — read path + cache headers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from stars.models import RefreshRun
from stars.router import router


@pytest.fixture(name="app_client")
def app_client_fixture():
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
    session = Session(engine)

    app = FastAPI()
    app.include_router(router)

    def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    yield TestClient(app), session
    session.close()
    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


class TestGetBest:
    def test_empty_state_returns_empty_payload_with_cache_header(self, app_client):
        client, _ = app_client
        resp = client.get("/api/stars/best")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ranked_count"] == 0
        assert body["locations"] == []
        assert body["cached_at"] is None
        # ADR 002: anonymous endpoints set s-maxage so the edge can cache.
        assert "s-maxage=300" in resp.headers["cache-control"]
        assert "stale-while-revalidate=86400" in resp.headers["cache-control"]

    def test_returns_latest_ok_payload(self, app_client):
        client, session = app_client
        row = RefreshRun(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="ok",
            payload={
                "locations": [
                    {"id": "tomintoul", "name": "Tomintoul", "best_score": 87.4}
                ],
                "ranked_count": 1,
                "total_locations": 30,
                "min_display_score": 60,
                "cached_at": "2026-04-26T22:00:00+00:00",
            },
        )
        session.add(row)
        session.commit()

        resp = client.get("/api/stars/best")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ranked_count"] == 1
        assert body["locations"][0]["id"] == "tomintoul"

    def test_error_only_history_returns_empty(self, app_client):
        client, session = app_client
        row = RefreshRun(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="error",
            error="MET Norway 503",
        )
        session.add(row)
        session.commit()

        resp = client.get("/api/stars/best")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ranked_count"] == 0
