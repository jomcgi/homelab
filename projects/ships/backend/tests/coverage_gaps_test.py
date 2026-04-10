"""
Coverage gap tests for Ships API backend.

Tests cover gaps not addressed by existing test files:
1. Database.should_insert_position() — speed/distance/moored-radius boundary conditions
   and None/malformed timestamp handling
2. ShipsAPIService.subscribe_ais_stream() — durable consumer config, batch-size
   switching, pending=0 startup path, catchup completion threshold,
   TimeoutError catchup check
3. cleanup_loop() — verifies the 3600-second sleep interval
4. get_vessel_track() endpoint — malformed 'since' strings that trigger ValueError
   or fall through without matching any unit suffix
5. websocket_live() endpoint — WebSocketDisconnect during receive, initial snapshot
   send, ping/pong, and cleanup-in-finally guarantee
"""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.backend.main import (
    CATCHUP_PENDING_THRESHOLD,
    DEDUP_DISTANCE_METERS,
    DEDUP_SPEED_THRESHOLD,
    INDEXES,
    MOORED_RADIUS_METERS,
    CachedPosition,
    Database,
    WebSocketManager,
    haversine_distance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bare_db():
    """Return a Database instance without a real SQLite connection."""
    db = Database.__new__(Database)
    db._position_cache = {}
    db._position_count = 0
    return db


def _cached(
    lat,
    lon,
    speed=0.0,
    timestamp="2024-06-01T10:00:00Z",
    first_seen="2024-06-01T08:00:00Z",
):
    return CachedPosition(
        lat=lat,
        lon=lon,
        speed=speed,
        timestamp=timestamp,
        first_seen_at_location=first_seen,
    )


# ---------------------------------------------------------------------------
# 1. Database.should_insert_position() boundary conditions
# ---------------------------------------------------------------------------


class TestShouldInsertPositionBoundaryConditions:
    """Boundary cases that exercise exact threshold values."""

    def test_speed_exactly_at_threshold_not_treated_as_moving(self):
        """Speed == DEDUP_SPEED_THRESHOLD is NOT above threshold → goes to distance check.

        The guard is `speed > DEDUP_SPEED_THRESHOLD`, so an exact match of 0.5
        should fall through to the distance/time checks (not fast-path insert).
        """
        db = _make_bare_db()
        db._position_cache["111"] = _cached(lat=48.5, lon=-123.4, speed=0.0)

        # Nearby position, speed exactly at threshold, within dedup distance and time
        data = {
            "mmsi": "111",
            "lat": 48.5,
            "lon": -123.4,
            "speed": DEDUP_SPEED_THRESHOLD,  # 0.5 — not ABOVE threshold
            "timestamp": "2024-06-01T10:01:00Z",
        }
        should_insert, _ = db.should_insert_position(data)
        # Distance ~0m, time 60s (< 300s) → deduplicated
        assert should_insert is False

    def test_distance_exactly_at_dedup_threshold_not_inserted(self):
        """Distance just below DEDUP_DISTANCE_METERS is NOT beyond threshold.

        `distance > DEDUP_DISTANCE_METERS` (strictly greater) means that a
        position within 100 m does not trigger the distance-insert path.
        It falls through to the time check, which also fails (60 s < 300 s),
        so the position is deduplicated (not inserted).
        """
        db = _make_bare_db()
        # Place last at origin
        db._position_cache["222"] = _cached(lat=0.0, lon=0.0, speed=0.0)

        # Move ~89 m north (0.0008° lat × 111 111 m/° ≈ 89 m) — clearly below 100 m
        # haversine(0,0, 0.0008,0) ≈ 89 m  →  89 > 100 is False → no distance insert
        data = {
            "mmsi": "222",
            "lat": 0.0008,
            "lon": 0.0,
            "speed": 0.0,
            "timestamp": "2024-06-01T10:01:00Z",  # Only 60s later (< 300s threshold)
        }
        should_insert, _ = db.should_insert_position(data)
        # 89 m ≤ 100 m threshold AND 60 s < 300 s threshold → deduplicated
        assert should_insert is False

    def test_moored_radius_exact_boundary_preserves_first_seen(self):
        """Slow vessel that moved exactly MOORED_RADIUS_METERS keeps first_seen.

        `distance <= MOORED_RADIUS_METERS` (500 m) → first_seen preserved.
        """
        db = _make_bare_db()
        original_first_seen = "2024-06-01T08:00:00Z"
        db._position_cache["333"] = _cached(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            first_seen=original_first_seen,
        )

        # Move approximately MOORED_RADIUS_METERS north but staying inside (≤500m)
        # 0.0045° lat ≈ 500 m; use a tiny fraction less to stay ≤ 500m
        data = {
            "mmsi": "333",
            "lat": 48.5044,  # ~490m north — inside 500m moored radius
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-06-01T10:01:00Z",
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        # Still inside moored radius → first_seen preserved
        assert first_seen == original_first_seen

    def test_none_timestamp_in_data_triggers_insert(self):
        """Explicitly None timestamp in data triggers insert rather than raising.

        When data["timestamp"] is None, None.replace(...) raises AttributeError.
        The except clause catches (ValueError, TypeError, AttributeError) and
        returns (True, timestamp) so the position is always inserted safely.
        """
        db = _make_bare_db()
        db._position_cache["444"] = _cached(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
        )

        # Same position (< dedup distance), speed=0, timestamp explicitly None
        data = {
            "mmsi": "444",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": None,
        }
        # Must not raise; should insert because timestamp parsing fails
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True

    def test_none_last_timestamp_triggers_insert(self):
        """CachedPosition with timestamp=None triggers insert (AttributeError caught)."""
        db = _make_bare_db()
        db._position_cache["555"] = CachedPosition(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp=None,  # type: ignore[arg-type]  — simulating corrupt cache
            first_seen_at_location="2024-06-01T08:00:00Z",
        )

        data = {
            "mmsi": "555",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-06-01T10:01:00Z",
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True

    def test_empty_string_timestamp_in_data_triggers_insert(self):
        """Empty-string timestamp (default when key absent) triggers insert via ValueError."""
        db = _make_bare_db()
        db._position_cache["666"] = _cached(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
        )

        # No timestamp key → data.get("timestamp", "") returns ""
        data = {
            "mmsi": "666",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            # timestamp key absent on purpose
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True


# ---------------------------------------------------------------------------
# 2. ShipsAPIService.subscribe_ais_stream() / _run_subscription()
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamConsumerConfig:
    """Verify durable consumer configuration passed to pull_subscribe."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_pull_subscribe_uses_durable_ships_api(self, service):
        """pull_subscribe is called with durable='ships-api'."""
        captured = {}

        async def capture_pull_subscribe(subject, durable, config):
            captured["subject"] = subject
            captured["durable"] = durable
            captured["config"] = config
            raise RuntimeError("stop-test")

        service.js = MagicMock()
        service.js.pull_subscribe = capture_pull_subscribe
        service.running = True

        with pytest.raises(RuntimeError, match="stop-test"):
            await service.subscribe_ais_stream()

        assert captured["subject"] == "ais.>"
        assert captured["durable"] == "ships-api"

    @pytest.mark.asyncio
    async def test_consumer_config_fields(self, service):
        """ConsumerConfig has correct ack_wait and max_ack_pending."""
        from nats.js.api import DeliverPolicy

        captured = {}

        async def capture_pull_subscribe(subject, durable, config):
            captured["config"] = config
            raise RuntimeError("stop-test")

        service.js = MagicMock()
        service.js.pull_subscribe = capture_pull_subscribe
        service.running = True

        with pytest.raises(RuntimeError, match="stop-test"):
            await service.subscribe_ais_stream()

        cfg = captured["config"]
        assert cfg.durable_name == "ships-api"
        assert cfg.deliver_policy == DeliverPolicy.ALL
        assert cfg.ack_wait == 120
        assert cfg.max_ack_pending == 10000


class TestSubscribeAisStreamPendingBehavior:
    """Verify pending=0 startup path and batch-size switching."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        svc = ShipsAPIService()
        svc.db = MagicMock()
        svc.db.get_vessel_count = MagicMock(return_value=0)
        svc.db.get_position_count = MagicMock(return_value=0)
        svc.db.insert_positions_batch = AsyncMock(return_value=0)
        svc.db.upsert_vessels_batch = AsyncMock()
        svc.db.commit = AsyncMock()
        svc.ws_manager = MagicMock()
        svc.ws_manager.broadcast = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_zero_pending_on_startup_sets_ready_true_immediately(self, service):
        """When consumer reports 0 pending messages, ready=True is set before the loop."""
        mock_sub = AsyncMock()
        mock_info = MagicMock()
        mock_info.num_pending = 0
        mock_sub.consumer_info = AsyncMock(return_value=mock_info)

        async def fetch_and_stop(*args, **kwargs):
            service.running = False
            raise asyncio.TimeoutError()

        mock_sub.fetch = fetch_and_stop
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(return_value=mock_sub)
        service.running = True

        await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_batch_size_10000_during_catchup(self, service):
        """fetch is called with batch=10000 while replay_complete=False."""
        mock_sub = AsyncMock()
        # More pending than threshold → catchup mode
        mock_info = MagicMock()
        mock_info.num_pending = CATCHUP_PENDING_THRESHOLD + 1
        mock_sub.consumer_info = AsyncMock(return_value=mock_info)

        fetch_batch_sizes = []

        async def fetch_side_effect(batch, timeout):
            fetch_batch_sizes.append(batch)
            service.running = False
            raise asyncio.TimeoutError()

        mock_sub.fetch = fetch_side_effect
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(return_value=mock_sub)
        service.running = True

        await service.subscribe_ais_stream()

        assert len(fetch_batch_sizes) >= 1
        assert fetch_batch_sizes[0] == 10000

    @pytest.mark.asyncio
    async def test_batch_size_100_when_live(self, service):
        """fetch is called with batch=100 after replay_complete=True (pending=0)."""
        mock_sub = AsyncMock()
        mock_info = MagicMock()
        mock_info.num_pending = 0
        mock_sub.consumer_info = AsyncMock(return_value=mock_info)

        fetch_batch_sizes = []

        async def fetch_side_effect(batch, timeout):
            fetch_batch_sizes.append(batch)
            service.running = False
            raise asyncio.TimeoutError()

        mock_sub.fetch = fetch_side_effect
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(return_value=mock_sub)
        service.running = True

        await service.subscribe_ais_stream()

        # First fetch should use the live batch size
        assert len(fetch_batch_sizes) >= 1
        assert fetch_batch_sizes[0] == 100

    @pytest.mark.asyncio
    async def test_catchup_completion_after_batch_within_threshold(self, service):
        """After processing a batch, pending <= threshold marks replay complete."""
        mock_sub = AsyncMock()
        consumer_info_calls = 0

        async def consumer_info_side_effect():
            nonlocal consumer_info_calls
            consumer_info_calls += 1
            info = MagicMock()
            if consumer_info_calls == 1:
                # Before loop: many pending → enter catchup
                info.num_pending = CATCHUP_PENDING_THRESHOLD + 1000
            else:
                # After first batch: below threshold → catchup complete
                info.num_pending = CATCHUP_PENDING_THRESHOLD - 1
            return info

        mock_sub.consumer_info = consumer_info_side_effect

        fetch_count = 0

        async def fetch_side_effect(batch, timeout):
            nonlocal fetch_count
            fetch_count += 1
            if fetch_count == 1:
                return []  # empty batch → triggers catchup check
            # Second fetch (when live): stop the loop
            service.running = False
            raise asyncio.TimeoutError()

        mock_sub.fetch = fetch_side_effect
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(return_value=mock_sub)
        service.running = True

        await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_timeout_during_catchup_triggers_completion_check(self, service):
        """TimeoutError during catchup also checks consumer_info for completion."""
        mock_sub = AsyncMock()
        consumer_info_calls = 0

        async def consumer_info_side_effect():
            nonlocal consumer_info_calls
            consumer_info_calls += 1
            info = MagicMock()
            if consumer_info_calls == 1:
                # Before loop: many pending
                info.num_pending = CATCHUP_PENDING_THRESHOLD + 5000
            else:
                # During TimeoutError handler: below threshold
                info.num_pending = CATCHUP_PENDING_THRESHOLD // 2
            return info

        mock_sub.consumer_info = consumer_info_side_effect

        async def fetch_side_effect(batch, timeout):
            # TimeoutError → triggers catchup check in except asyncio.TimeoutError
            service.running = False  # stop after this
            raise asyncio.TimeoutError()

        mock_sub.fetch = fetch_side_effect
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(return_value=mock_sub)
        service.running = True

        await service.subscribe_ais_stream()

        # The TimeoutError handler ran consumer_info and found pending ≤ threshold
        assert service.replay_complete is True
        assert service.ready is True


class TestRunSubscription:
    """Tests for ShipsAPIService._run_subscription()."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_run_subscription_calls_subscribe_ais_stream(self, service):
        """_run_subscription() delegates directly to subscribe_ais_stream()."""
        called = []

        async def fake_subscribe():
            called.append(True)

        service.subscribe_ais_stream = fake_subscribe
        await service._run_subscription()

        assert called == [True]


# ---------------------------------------------------------------------------
# 3. cleanup_loop() — sleep interval
# ---------------------------------------------------------------------------


class TestCleanupLoopInterval:
    """Verify cleanup_loop sleeps for exactly 3600 seconds per iteration."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_cleanup_loop_sleep_interval_is_3600(self, service):
        """cleanup_loop calls asyncio.sleep(3600) each iteration."""
        service.running = True
        service.db = MagicMock()
        service.db.cleanup_old_positions = AsyncMock()

        sleep_durations = []

        async def fake_sleep(duration):
            sleep_durations.append(duration)
            service.running = False  # stop after first sleep

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await service.cleanup_loop()

        assert len(sleep_durations) >= 1
        assert sleep_durations[0] == 3600


# ---------------------------------------------------------------------------
# 4. get_vessel_track() endpoint — malformed 'since' strings
# ---------------------------------------------------------------------------


class TestGetVesselTrackMalformedSince:
    """Malformed 'since' parameter variants that are not already tested."""

    @pytest.mark.asyncio
    async def test_since_value_error_prefix_returns_200(self, test_client):
        """'abch' ends with 'h' but int('abc') raises ValueError → duration=None → 200."""
        response = await test_client.get("/api/vessels/999999999/track?since=abch")
        assert response.status_code == 200
        data = response.json()
        assert data["mmsi"] == "999999999"
        assert "track" in data

    @pytest.mark.asyncio
    async def test_since_unknown_unit_returns_200(self, test_client):
        """'1x' has unknown suffix → no duration parsed → 200 with all positions."""
        response = await test_client.get("/api/vessels/999999999/track?since=1x")
        assert response.status_code == 200
        data = response.json()
        assert "track" in data

    @pytest.mark.asyncio
    async def test_since_zero_hours_returns_200(self, test_client):
        """'0h' is valid → timedelta(hours=0) → since_time ≈ now → returns 200."""
        response = await test_client.get("/api/vessels/999999999/track?since=0h")
        assert response.status_code == 200
        data = response.json()
        assert data["mmsi"] == "999999999"
        assert "track" in data

    @pytest.mark.asyncio
    async def test_since_letter_only_no_number_returns_200(self, test_client):
        """'h' alone: int('') raises ValueError → duration=None → 200."""
        response = await test_client.get("/api/vessels/999999999/track?since=h")
        assert response.status_code == 200
        data = response.json()
        assert "track" in data

    @pytest.mark.asyncio
    async def test_since_number_only_no_unit_returns_200(self, test_client):
        """'24' has no matching suffix → duration=None → 200 with full history."""
        response = await test_client.get("/api/vessels/999999999/track?since=24")
        assert response.status_code == 200
        data = response.json()
        assert "track" in data


# ---------------------------------------------------------------------------
# 5. websocket_live() endpoint — disconnect edge cases
# ---------------------------------------------------------------------------


class TestWebsocketLiveDisconnect:
    """Test websocket_live endpoint disconnect handling."""

    @pytest.mark.asyncio
    async def test_disconnect_during_receive_calls_manager_disconnect(self):
        """WebSocketDisconnect raised in receive_text must call ws_manager.disconnect."""
        from fastapi import WebSocketDisconnect

        import projects.ships.backend.main as main_module
        from projects.ships.backend.main import websocket_live

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws.send_json = AsyncMock()

        with (
            patch.object(main_module.service.ws_manager, "connect", AsyncMock()),
            patch.object(
                main_module.service.ws_manager, "disconnect", AsyncMock()
            ) as mock_disconnect,
            patch.object(
                main_module.service.db,
                "get_latest_positions",
                AsyncMock(return_value=[]),
            ),
        ):
            await websocket_live(mock_ws)

        mock_disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_snapshot_sent_on_connect(self):
        """websocket_live sends an initial snapshot immediately on connection."""
        import projects.ships.backend.main as main_module
        from projects.ships.backend.main import websocket_live
        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        # Disconnect after first receive so the loop terminates
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        sent_messages = []

        async def capture_send_json(msg):
            sent_messages.append(msg)

        mock_ws.send_json = capture_send_json

        sample_vessels = [{"mmsi": "123456789", "lat": 48.5, "lon": -123.4}]

        with (
            patch.object(main_module.service.ws_manager, "connect", AsyncMock()),
            patch.object(main_module.service.ws_manager, "disconnect", AsyncMock()),
            patch.object(
                main_module.service.db,
                "get_latest_positions",
                AsyncMock(return_value=sample_vessels),
            ),
        ):
            await websocket_live(mock_ws)

        assert len(sent_messages) == 1
        assert sent_messages[0]["type"] == "snapshot"
        assert sent_messages[0]["vessels"] == sample_vessels

    @pytest.mark.asyncio
    async def test_ping_receives_pong(self):
        """Sending 'ping' causes the endpoint to send back 'pong'."""
        import projects.ships.backend.main as main_module
        from projects.ships.backend.main import websocket_live
        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        # First receive returns "ping", second raises WebSocketDisconnect
        mock_ws.receive_text = AsyncMock(side_effect=["ping", WebSocketDisconnect()])
        mock_ws.send_json = AsyncMock()
        mock_ws.send_text = AsyncMock()

        with (
            patch.object(main_module.service.ws_manager, "connect", AsyncMock()),
            patch.object(main_module.service.ws_manager, "disconnect", AsyncMock()),
            patch.object(
                main_module.service.db,
                "get_latest_positions",
                AsyncMock(return_value=[]),
            ),
        ):
            await websocket_live(mock_ws)

        mock_ws.send_text.assert_called_once_with("pong")

    @pytest.mark.asyncio
    async def test_snapshot_send_failure_still_disconnects(self):
        """If initial send_json raises, the finally block still disconnects."""
        import projects.ships.backend.main as main_module
        from projects.ships.backend.main import websocket_live

        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=Exception("connection reset"))

        with (
            patch.object(main_module.service.ws_manager, "connect", AsyncMock()),
            patch.object(
                main_module.service.ws_manager, "disconnect", AsyncMock()
            ) as mock_disconnect,
            patch.object(
                main_module.service.db,
                "get_latest_positions",
                AsyncMock(return_value=[]),
            ),
        ):
            with pytest.raises(Exception, match="connection reset"):
                await websocket_live(mock_ws)

        # Even on exception, finally block must call disconnect
        mock_disconnect.assert_called_once_with(mock_ws)


# ---------------------------------------------------------------------------
# 6. Database.should_insert_position() — missing lat/lon keys
# ---------------------------------------------------------------------------


class TestShouldInsertPositionMissingCoordinates:
    """Test should_insert_position() when lat/lon keys are missing or zero."""

    def test_missing_lat_lon_keys_defaults_to_zero(self):
        """When lat/lon keys are absent, they default to 0 (equator/prime meridian).
        A position with no lat/lon but a cached vessel at the same origin
        is treated as close together, goes through time check."""
        db = _make_bare_db()
        # Cache a vessel at origin (0, 0) with a recent timestamp
        db._position_cache["777"] = _cached(
            lat=0.0,
            lon=0.0,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
        )

        # No lat/lon keys: defaults to 0.0 — same location as cache → distance ~0m
        # Timestamp only 30s later → below DEDUP_TIME_THRESHOLD → deduplicated
        data = {
            "mmsi": "777",
            # lat and lon keys absent — both default to 0
            "speed": 0.0,
            "timestamp": "2024-06-01T10:00:30Z",
        }
        should_insert, _ = db.should_insert_position(data)
        # Effectively at same location, within time threshold → deduplicated
        assert should_insert is False

    def test_missing_lat_key_first_vessel_inserts(self):
        """First position for a vessel with missing lat/lon still inserts (no cache entry)."""
        db = _make_bare_db()
        # No cache entry for this MMSI — first position always inserts

        data = {
            "mmsi": "888",
            # lat and lon keys absent — both default to 0
            "speed": 0.0,
            "timestamp": "2024-06-01T10:00:00Z",
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        assert first_seen == "2024-06-01T10:00:00Z"

    def test_lat_lon_zero_is_valid_equatorial_position(self):
        """lat=0, lon=0 is a valid equatorial position - should work with deduplication."""
        db = _make_bare_db()
        # Cache a vessel at origin
        db._position_cache["999"] = _cached(
            lat=0.0,
            lon=0.0,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
            first_seen="2024-06-01T09:00:00Z",
        )

        # Explicit lat=0, lon=0 — same location, well beyond time threshold
        data = {
            "mmsi": "999",
            "lat": 0.0,
            "lon": 0.0,
            "speed": 0.0,
            "timestamp": "2024-06-01T11:00:00Z",  # 1 hour later → beyond time threshold
        }
        should_insert, first_seen = db.should_insert_position(data)
        # Distance = 0 m (not > DEDUP_DISTANCE_METERS), but time > DEDUP_TIME_THRESHOLD → insert
        assert should_insert is True
        # Still within moored radius → first_seen preserved from cache
        assert first_seen == "2024-06-01T09:00:00Z"


# ---------------------------------------------------------------------------
# 6. haversine_distance() — antipodal points and zero distance
# ---------------------------------------------------------------------------


class TestHaversineDistanceAdditionalCases:
    """Edge cases for haversine_distance not covered by database_test.py."""

    def test_antipodal_points_across_equator(self):
        """Antipodal points (0°N 0°E) ↔ (0°N 180°E) ≈ half Earth's circumference.

        Half circumference = π × R ≈ 20,015 km.
        """
        distance = haversine_distance(0.0, 0.0, 0.0, 180.0)
        # Allow 0.1% tolerance for floating-point arithmetic
        assert distance == pytest.approx(20_015_087, rel=0.001)

    def test_antipodal_points_through_poles(self):
        """Antipodal points at (90°N 0°E) ↔ (90°S 0°E) (north to south pole)."""
        distance = haversine_distance(90.0, 0.0, -90.0, 0.0)
        assert distance == pytest.approx(20_015_087, rel=0.001)

    def test_zero_distance_at_prime_meridian_equator(self):
        """Zero distance for identical points at origin."""
        assert haversine_distance(0.0, 0.0, 0.0, 0.0) == pytest.approx(0, abs=0.01)

    def test_zero_distance_at_high_latitude(self):
        """Zero distance for identical points at high latitude."""
        assert haversine_distance(
            89.9999, -179.9999, 89.9999, -179.9999
        ) == pytest.approx(0, abs=0.01)

    def test_symmetry(self):
        """Distance from A→B equals distance from B→A."""
        lat1, lon1 = 48.5, -123.4
        lat2, lon2 = 47.6, -122.3
        assert haversine_distance(lat1, lon1, lat2, lon2) == pytest.approx(
            haversine_distance(lat2, lon2, lat1, lon1), rel=1e-9
        )


# ---------------------------------------------------------------------------
# 7. Database.drop_indexes() and create_indexes()
# ---------------------------------------------------------------------------


class TestDatabaseIndexOperations:
    """Tests for Database.drop_indexes() and create_indexes()."""

    @pytest.mark.asyncio
    async def test_drop_indexes_calls_execute_for_each_drop_statement(self):
        """drop_indexes executes four DROP INDEX statements and commits."""
        db = Database.__new__(Database)
        mock_conn = AsyncMock()
        db.db = mock_conn

        await db.drop_indexes()

        # Four DROP statements: 2 current + 2 legacy
        assert mock_conn.execute.call_count == 4
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_drop_indexes_uses_if_exists_to_be_idempotent(self):
        """All DROP statements use IF EXISTS so re-running is safe."""
        db = Database.__new__(Database)
        executed_sqls = []
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=lambda sql: executed_sqls.append(sql))
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        await db.drop_indexes()

        for sql in executed_sqls:
            assert "DROP INDEX IF EXISTS" in sql.upper()

    @pytest.mark.asyncio
    async def test_create_indexes_calls_execute_once_per_index(self):
        """create_indexes executes one CREATE statement per entry in INDEXES."""
        db = Database.__new__(Database)
        mock_conn = AsyncMock()
        db.db = mock_conn

        await db.create_indexes()

        assert mock_conn.execute.call_count == len(INDEXES)
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_indexes_uses_create_index_if_not_exists(self):
        """All CREATE statements use CREATE INDEX IF NOT EXISTS."""
        db = Database.__new__(Database)
        executed_sqls = []
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            side_effect=lambda sql: executed_sqls.append(sql)
        )
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        await db.create_indexes()

        for sql in executed_sqls:
            assert "CREATE INDEX IF NOT EXISTS" in sql.upper()

    @pytest.mark.asyncio
    async def test_drop_then_create_cycle_on_real_db(self):
        """drop_indexes followed by create_indexes works on a real in-memory DB."""
        import pytest_asyncio

        db = Database(":memory:")
        await db.connect()

        try:
            await db.drop_indexes()
            await db.create_indexes()

            # Verify required indexes exist after creation
            cursor = await db.db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'idx_positions%'"
            )
            rows = await cursor.fetchall()
            index_names = {r[0] for r in rows}

            assert "idx_positions_mmsi_timestamp" in index_names
            assert "idx_positions_timestamp" in index_names
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_drop_indexes_removes_indexes_from_real_db(self):
        """drop_indexes actually removes the position indexes from SQLite."""
        db = Database(":memory:")
        await db.connect()

        try:
            # Verify indexes exist after initial connect
            cursor = await db.db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'idx_positions%'"
            )
            before = {r[0] for r in await cursor.fetchall()}
            assert len(before) > 0  # indexes should exist initially

            await db.drop_indexes()

            cursor = await db.db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'idx_positions%'"
            )
            after = {r[0] for r in await cursor.fetchall()}
            assert len(after) == 0
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 8. Database cache accessor methods
# ---------------------------------------------------------------------------


class TestDatabaseCacheAccessors:
    """Tests for get_cached_position, get_vessel_count, get_position_count,
    get_cache_size — all operate on the in-memory state, not the DB."""

    # --- get_cached_position ---

    def test_get_cached_position_returns_none_when_cache_empty(self):
        """Returns None for unknown MMSI."""
        db = _make_bare_db()
        assert db.get_cached_position("123456789") is None

    def test_get_cached_position_returns_none_for_missing_mmsi(self):
        """Returns None for MMSI not in cache even when other entries exist."""
        db = _make_bare_db()
        db._position_cache["111111111"] = _cached(lat=48.5, lon=-123.4)
        assert db.get_cached_position("999999999") is None

    def test_get_cached_position_returns_cached_entry(self):
        """Returns the exact CachedPosition object stored for a known MMSI."""
        db = _make_bare_db()
        entry = _cached(lat=48.5, lon=-123.4, speed=5.0)
        db._position_cache["123456789"] = entry
        result = db.get_cached_position("123456789")
        assert result is entry  # identity check, not just equality

    def test_get_cached_position_returns_correct_lat_lon(self):
        """Returned entry has the correct lat/lon values."""
        db = _make_bare_db()
        db._position_cache["999"] = _cached(lat=49.123, lon=-124.567)
        result = db.get_cached_position("999")
        assert result is not None
        assert result.lat == pytest.approx(49.123)
        assert result.lon == pytest.approx(-124.567)

    # --- get_vessel_count ---

    def test_get_vessel_count_returns_zero_when_empty(self):
        """Returns 0 when position cache is empty."""
        db = _make_bare_db()
        assert db.get_vessel_count() == 0

    def test_get_vessel_count_returns_one_after_single_entry(self):
        """Returns 1 after one MMSI is added to the cache."""
        db = _make_bare_db()
        db._position_cache["111111111"] = _cached(lat=48.5, lon=-123.4)
        assert db.get_vessel_count() == 1

    def test_get_vessel_count_returns_correct_count_for_multiple(self):
        """Returns correct count for multiple distinct MMSIs."""
        db = _make_bare_db()
        for mmsi in ["111", "222", "333", "444"]:
            db._position_cache[mmsi] = _cached(lat=48.5, lon=-123.4)
        assert db.get_vessel_count() == 4

    # --- get_position_count ---

    def test_get_position_count_returns_zero_initially(self):
        """Returns 0 when _position_count is not incremented."""
        db = _make_bare_db()
        assert db.get_position_count() == 0

    def test_get_position_count_reflects_cached_counter(self):
        """Returns the value of the _position_count field directly."""
        db = _make_bare_db()
        db._position_count = 1234
        assert db.get_position_count() == 1234

    def test_get_position_count_is_independent_of_cache_size(self):
        """Position count is tracked separately from the in-memory cache size."""
        db = _make_bare_db()
        db._position_count = 100
        # Cache has 2 entries, but position_count is 100
        db._position_cache["111"] = _cached(lat=48.5, lon=-123.4)
        db._position_cache["222"] = _cached(lat=49.0, lon=-124.0)
        assert db.get_position_count() == 100
        assert db.get_vessel_count() == 2  # cache size != position count

    # --- get_cache_size ---

    def test_get_cache_size_returns_zero_when_empty(self):
        """Returns 0 when position cache is empty."""
        db = _make_bare_db()
        assert db.get_cache_size() == 0

    def test_get_cache_size_equals_vessel_count(self):
        """get_cache_size and get_vessel_count both count the cache dict."""
        db = _make_bare_db()
        for mmsi in ["111", "222", "333"]:
            db._position_cache[mmsi] = _cached(lat=48.5, lon=-123.4)
        assert db.get_cache_size() == 3
        assert db.get_cache_size() == db.get_vessel_count()

    def test_get_cache_size_after_update(self):
        """Adding an entry to the cache is reflected in get_cache_size."""
        db = _make_bare_db()
        db._position_cache["111"] = _cached(lat=48.5, lon=-123.4)
        assert db.get_cache_size() == 1
        db._position_cache["222"] = _cached(lat=49.0, lon=-124.0)
        assert db.get_cache_size() == 2


# ---------------------------------------------------------------------------
# 9. WebSocketManager.client_count()
# ---------------------------------------------------------------------------


class TestWebSocketManagerClientCount:
    """Tests for WebSocketManager.client_count()."""

    @pytest.mark.asyncio
    async def test_client_count_zero_on_creation(self):
        """Freshly created manager has 0 clients."""
        mgr = WebSocketManager()
        assert await mgr.client_count() == 0

    @pytest.mark.asyncio
    async def test_client_count_one_after_single_connect(self):
        """After one connect, client_count() returns 1."""
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        await mgr.connect(ws)
        assert await mgr.client_count() == 1

    @pytest.mark.asyncio
    async def test_client_count_reflects_multiple_connections(self):
        """client_count returns the total number of connected clients."""
        mgr = WebSocketManager()
        sockets = []
        for _ in range(5):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            await mgr.connect(ws)
            sockets.append(ws)
        assert await mgr.client_count() == 5

    @pytest.mark.asyncio
    async def test_client_count_decrements_after_disconnect(self):
        """Disconnecting a client decrements the count."""
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        await mgr.connect(ws)
        await mgr.disconnect(ws)
        assert await mgr.client_count() == 0

    @pytest.mark.asyncio
    async def test_client_count_partial_disconnect(self):
        """Disconnecting one of several clients decrements by exactly one."""
        mgr = WebSocketManager()
        ws1, ws2, ws3 = (AsyncMock() for _ in range(3))
        for ws in (ws1, ws2, ws3):
            ws.accept = AsyncMock()
            await mgr.connect(ws)

        await mgr.disconnect(ws2)
        assert await mgr.client_count() == 2

    @pytest.mark.asyncio
    async def test_client_count_disconnect_nonexistent_does_not_raise(self):
        """Disconnecting a websocket that was never connected is a no-op."""
        mgr = WebSocketManager()
        ws = AsyncMock()
        # No connect call — should not raise
        await mgr.disconnect(ws)
        assert await mgr.client_count() == 0


# ---------------------------------------------------------------------------
# 10. HTTP endpoint: GET /api/stats
# ---------------------------------------------------------------------------


class TestGetStatsEndpoint:
    """Integration tests for the GET /api/stats endpoint."""

    @pytest.mark.asyncio
    async def test_stats_returns_200(self, test_client):
        """Stats endpoint returns HTTP 200."""
        response = await test_client.get("/api/stats")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_stats_response_has_all_required_fields(self, test_client):
        """Stats response contains every expected field."""
        response = await test_client.get("/api/stats")
        data = response.json()
        expected_fields = {
            "vessel_count",
            "position_count",
            "cache_size",
            "messages_received",
            "messages_deduplicated",
            "connected_clients",
            "replay_complete",
            "retention_days",
        }
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_stats_fields_have_correct_types(self, test_client):
        """All numeric/boolean stats fields have the expected Python types."""
        response = await test_client.get("/api/stats")
        data = response.json()
        assert isinstance(data["vessel_count"], int)
        assert isinstance(data["position_count"], int)
        assert isinstance(data["cache_size"], int)
        assert isinstance(data["messages_received"], int)
        assert isinstance(data["messages_deduplicated"], int)
        assert isinstance(data["connected_clients"], int)
        assert isinstance(data["replay_complete"], bool)
        assert isinstance(data["retention_days"], int)

    @pytest.mark.asyncio
    async def test_stats_connected_clients_zero_when_no_ws(self, test_client):
        """connected_clients is 0 when no WebSocket connections are active."""
        response = await test_client.get("/api/stats")
        data = response.json()
        assert data["connected_clients"] == 0

    @pytest.mark.asyncio
    async def test_stats_replay_complete_true_when_ready(self, test_client):
        """replay_complete mirrors service.replay_complete (True in test fixture)."""
        from projects.ships.backend.main import service

        # The test_client fixture sets replay_complete = True
        assert service.replay_complete is True

        response = await test_client.get("/api/stats")
        data = response.json()
        assert data["replay_complete"] is True

    @pytest.mark.asyncio
    async def test_stats_vessel_and_cache_count_match_with_data(
        self, test_client_with_data
    ):
        """After inserting 3 vessels, vessel_count and cache_size both equal 3."""
        response = await test_client_with_data.get("/api/stats")
        data = response.json()
        assert data["vessel_count"] == 3
        assert data["cache_size"] == 3

    @pytest.mark.asyncio
    async def test_stats_retention_days_is_positive(self, test_client):
        """retention_days reflects the POSITION_RETENTION_DAYS env variable (> 0)."""
        from projects.ships.backend.main import POSITION_RETENTION_DAYS

        response = await test_client.get("/api/stats")
        data = response.json()
        assert data["retention_days"] == POSITION_RETENTION_DAYS
        assert data["retention_days"] > 0


# ---------------------------------------------------------------------------
# 11. HTTP endpoint: GET /api/vessels — structural checks
# ---------------------------------------------------------------------------


class TestListVesselsEndpointStructure:
    """Additional structural tests for GET /api/vessels not in api_test.py."""

    @pytest.mark.asyncio
    async def test_list_vessels_count_equals_length_of_vessels_array(
        self, test_client_with_data
    ):
        """The 'count' field always equals len(vessels)."""
        response = await test_client_with_data.get("/api/vessels")
        data = response.json()
        assert data["count"] == len(data["vessels"])

    @pytest.mark.asyncio
    async def test_list_vessels_each_vessel_has_mmsi_lat_lon(
        self, test_client_with_data
    ):
        """Each vessel in the list has at minimum mmsi, lat, and lon."""
        response = await test_client_with_data.get("/api/vessels")
        for vessel in response.json()["vessels"]:
            assert "mmsi" in vessel
            assert "lat" in vessel
            assert "lon" in vessel


# ---------------------------------------------------------------------------
# 12. HTTP endpoint: GET /api/vessels/{mmsi} — analytics fields
# ---------------------------------------------------------------------------


class TestGetVesselEndpointAnalytics:
    """Tests for mooring analytics fields returned by GET /api/vessels/{mmsi}."""

    @pytest.mark.asyncio
    async def test_get_vessel_with_first_seen_has_time_at_location(
        self, test_client_with_data
    ):
        """When first_seen_at_location is set, time_at_location_* fields are present."""
        from projects.ships.backend.main import service

        # Insert a vessel whose first_seen_at_location is set to a known time
        ts = "2024-01-01T00:00:00+00:00"
        await service.db.insert_positions_batch(
            [
                (
                    {
                        "mmsi": "777777777",
                        "lat": 49.0,
                        "lon": -124.0,
                        "speed": 0.0,
                        "timestamp": ts,
                    },
                    ts,  # first_seen_at_location = same as timestamp
                )
            ]
        )
        await service.db.commit()

        response = await test_client_with_data.get("/api/vessels/777777777")
        data = response.json()
        assert data["mmsi"] == "777777777"
        assert "time_at_location_seconds" in data
        assert "time_at_location_hours" in data
        assert "is_moored" in data
        # The vessel has been "at location" for a long time → should be moored
        assert data["is_moored"] is True

    @pytest.mark.asyncio
    async def test_get_vessel_returns_lat_lon_speed(self, test_client_with_data):
        """Found vessel includes lat, lon, speed, and timestamp fields."""
        response = await test_client_with_data.get("/api/vessels/111111111")
        assert response.status_code == 200
        data = response.json()
        assert data["mmsi"] == "111111111"
        assert isinstance(data["lat"], float)
        assert isinstance(data["lon"], float)
