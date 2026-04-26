"""Tests for stars.service — refresh handler + last-good read."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

import stars.service as service
from stars.models import RefreshRun


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session with stars schema stripped (SQLite has no schemas)."""
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


def _fake_forecast(score_band: str = "clear") -> dict:
    """Build a MET-Norway-shaped forecast with one dark hour matching the requested band."""
    cloud = {"clear": 5.0, "overcast": 95.0}[score_band]
    # Pick a winter midnight to guarantee astronomical darkness in Scotland.
    t = (
        datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "properties": {
            "timeseries": [
                {
                    "time": t,
                    "data": {
                        "instant": {
                            "details": {
                                "cloud_area_fraction": cloud,
                                "relative_humidity": 50.0,
                                "wind_speed": 3.0,
                                "air_temperature": 5.0,
                                "dew_point_temperature": 0.0,
                                "air_pressure_at_sea_level": 1020.0,
                            }
                        },
                        "next_1_hours": {"summary": {"symbol_code": "clearsky_night"}},
                    },
                },
            ]
        }
    }


class TestBuildPayload:
    def test_ranks_clear_above_overcast(self):
        forecasts = {
            "galloway-forest": _fake_forecast("clear"),
            "tomintoul": _fake_forecast("overcast"),
        }
        payload = service.build_payload(forecasts)
        # Overcast should be filtered out by MIN_DISPLAY_SCORE (60); only clear shown.
        assert payload["ranked_count"] == 1
        assert payload["locations"][0]["id"] == "galloway-forest"
        assert payload["locations"][0]["best_score"] >= 90.0

    def test_includes_human_readable_name(self):
        forecasts = {"galloway-forest": _fake_forecast("clear")}
        payload = service.build_payload(forecasts)
        assert payload["locations"][0]["name"] == "Galloway Forest Park"

    def test_payload_includes_cached_at(self):
        payload = service.build_payload({})
        assert payload["cached_at"] is not None

    def test_unknown_location_id_is_dropped(self):
        forecasts = {"not-a-real-place": _fake_forecast("clear")}
        payload = service.build_payload(forecasts)
        assert payload["ranked_count"] == 0

    def test_total_locations_reflects_seed_size(self):
        payload = service.build_payload({})
        assert payload["total_locations"] >= 25


class TestRefreshHandlerSuccess:
    def test_writes_ok_row_with_payload(self, session):
        async def fake_fetch_all(locations):
            return {locations[0]["id"]: _fake_forecast("clear")}

        with patch.object(service, "_fetch_all", fake_fetch_all):
            asyncio.run(service.refresh_handler(session))

        rows = session.exec(select(RefreshRun)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "ok"
        assert row.completed_at is not None
        assert row.payload is not None
        assert row.payload["ranked_count"] >= 1

    def test_get_latest_payload_returns_most_recent_ok(self, session):
        # Stale ok row first
        stale = RefreshRun(
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status="ok",
            payload={"marker": "stale"},
        )
        # Newer ok row second
        fresh = RefreshRun(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="ok",
            payload={"marker": "fresh"},
        )
        session.add_all([stale, fresh])
        session.commit()

        payload = service.get_latest_payload(session)
        assert payload == {"marker": "fresh"}


class TestRefreshHandlerFailure:
    def test_writes_error_row_and_re_raises(self, session):
        async def boom(_locations):
            raise RuntimeError("network down")

        with patch.object(service, "_fetch_all", boom):
            with pytest.raises(RuntimeError, match="network down"):
                asyncio.run(service.refresh_handler(session))

        rows = session.exec(select(RefreshRun)).all()
        assert len(rows) == 1
        assert rows[0].status == "error"
        assert rows[0].error == "network down"
        assert rows[0].payload is None

    def test_failed_refresh_does_not_clobber_last_good_payload(self, session):
        # Pre-existing successful refresh
        good = RefreshRun(
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status="ok",
            payload={"marker": "good"},
        )
        session.add(good)
        session.commit()

        async def boom(_locations):
            raise RuntimeError("temporary failure")

        with patch.object(service, "_fetch_all", boom):
            with pytest.raises(RuntimeError):
                asyncio.run(service.refresh_handler(session))

        # Read path still serves the good payload.
        assert service.get_latest_payload(session) == {"marker": "good"}


class TestGetLatestPayloadEmpty:
    def test_returns_none_when_no_rows(self, session):
        assert service.get_latest_payload(session) is None

    def test_returns_none_when_only_error_rows(self, session):
        err = RefreshRun(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="error",
            error="boom",
        )
        session.add(err)
        session.commit()
        assert service.get_latest_payload(session) is None
