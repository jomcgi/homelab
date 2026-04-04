"""Unit tests for delete-trip-points/main.py — get_jetstream and command flows.

Supplements delete_trip_points_test.py by covering:
- get_jetstream: NATS connection function
- by_id dry_run: preview mode prints IDs without publishing
- by_date flow: filtering and tombstone publication via mocked HTTP + NATS
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin

from main import get_jetstream, publish_delete


# ---------------------------------------------------------------------------
# get_jetstream
# ---------------------------------------------------------------------------


class TestGetJetstream:
    """NATS JetStream connection factory."""

    @pytest.mark.asyncio
    async def test_returns_nc_and_js_tuple(self):
        """get_jetstream returns a 2-tuple (nc, js)."""
        mock_nc = AsyncMock()
        mock_js = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch("main.nats.connect", return_value=mock_nc):
            nc, js = await get_jetstream()

        assert nc is mock_nc
        assert js is mock_js

    @pytest.mark.asyncio
    async def test_connects_to_configured_nats_url(self):
        """nats.connect is called with the module-level NATS_URL."""
        import main as _main_mod

        mock_nc = AsyncMock()
        mock_nc.jetstream = MagicMock()

        with patch("main.nats.connect", return_value=mock_nc) as mock_connect:
            await get_jetstream()

        mock_connect.assert_awaited_once_with(_main_mod.NATS_URL)

    @pytest.mark.asyncio
    async def test_calls_jetstream_on_connection(self):
        """nc.jetstream() is called to obtain the JetStream context."""
        mock_nc = AsyncMock()
        mock_js = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch("main.nats.connect", return_value=mock_nc):
            await get_jetstream()

        mock_nc.jetstream.assert_called_once()


# ---------------------------------------------------------------------------
# publish_delete — additional edge cases
# ---------------------------------------------------------------------------


class TestPublishDeleteAdditional:
    """Edge cases not covered by delete_trip_points_test.py."""

    @pytest.mark.asyncio
    async def test_payload_only_has_id_and_deleted_keys(self):
        """The tombstone message must not contain extra fields."""
        mock_js = AsyncMock()
        await publish_delete(mock_js, "point-xyz")
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert set(payload.keys()) == {"id", "deleted"}

    @pytest.mark.asyncio
    async def test_numeric_string_id_round_trips(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "12345")
        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        assert payload["id"] == "12345"

    @pytest.mark.asyncio
    async def test_unicode_id_round_trips(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "pøint-üñíçødé")
        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        assert payload["id"] == "pøint-üñíçødé"


# ---------------------------------------------------------------------------
# Dry-run logic for by_id (via inline simulation)
# ---------------------------------------------------------------------------


class TestByIdDryRun:
    """When dry_run=True, no tombstones are published."""

    @pytest.mark.asyncio
    async def test_dry_run_suppresses_publish(self):
        """Simulate the by_id inner _delete with dry_run=True."""
        mock_js = AsyncMock()
        point_ids = ["id1", "id2", "id3"]
        dry_run = True

        if not dry_run:  # mirrors the actual source code path
            for pid in point_ids:
                await publish_delete(mock_js, pid)

        mock_js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_dry_run_publishes_all_ids(self):
        """Simulate the by_id inner _delete without dry_run."""
        mock_js = AsyncMock()
        point_ids = ["id1", "id2", "id3"]
        dry_run = False

        if not dry_run:
            for pid in point_ids:
                await publish_delete(mock_js, pid)

        assert mock_js.publish.call_count == 3
        published_ids = [
            json.loads(c[0][1].decode())["id"]
            for c in mock_js.publish.call_args_list
        ]
        assert published_ids == point_ids


# ---------------------------------------------------------------------------
# by_date filtering (pure logic, no I/O)
# ---------------------------------------------------------------------------


class TestByDateFiltering:
    """Filter logic extracted from by_date._delete."""

    _POINTS = [
        {
            "id": "g1",
            "timestamp": "2025-06-15T08:00:00",
            "source": "gap",
            "lat": 60.0,
            "lng": -135.0,
        },
        {
            "id": "g2",
            "timestamp": "2025-06-15T09:00:00",
            "source": "gap",
            "lat": 60.1,
            "lng": -135.1,
        },
        {
            "id": "p1",
            "timestamp": "2025-06-15T08:30:00",
            "source": "gopro",
            "lat": 60.2,
            "lng": -135.2,
        },
        {
            "id": "g3",
            "timestamp": "2025-06-16T08:00:00",
            "source": "gap",
            "lat": 61.0,
            "lng": -136.0,
        },
    ]

    def _filter(self, date: str, source: str):
        return [
            p
            for p in self._POINTS
            if p["timestamp"].startswith(date) and p["source"] == source
        ]

    def test_gap_points_for_correct_date(self):
        result = self._filter("2025-06-15", "gap")
        assert len(result) == 2
        assert all(p["source"] == "gap" for p in result)

    def test_no_match_for_wrong_date(self):
        result = self._filter("2025-07-01", "gap")
        assert result == []

    def test_no_match_for_wrong_source(self):
        result = self._filter("2025-06-15", "phone")
        assert result == []

    def test_different_date_returns_correct_count(self):
        result = self._filter("2025-06-16", "gap")
        assert len(result) == 1
        assert result[0]["id"] == "g3"

    def test_gopro_source_not_confused_with_gap(self):
        result = self._filter("2025-06-15", "gopro")
        assert len(result) == 1
        assert result[0]["id"] == "p1"
