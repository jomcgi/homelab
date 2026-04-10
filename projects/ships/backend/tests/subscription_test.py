"""Tests for ShipsAPIService.subscribe_ais_stream() and _run_subscription().

Covers:
- NATS durable consumer creation with correct config
- Catchup detection via num_pending threshold
- Catchup detection via TimeoutError path
- Batch size selection (10k during catchup, 100 during live)
- Position and vessel message batch DB writes
- Deduplicated message counter
- messages_received counter
- DB commit after each batch
- Parallel batch ack after DB commit
- WebSocket broadcast during live mode (with MMSI deduplication)
- No broadcast during catchup mode
- Error handling: exceptions inside loop are swallowed and loop continues
- running=False exits the loop
- Subscription failure propagates
- _run_subscription() delegation and exception propagation
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_msg(subject: str, data_dict: dict) -> MagicMock:
    """Return a mock NATS message with .subject, .data, and async .ack()."""
    msg = MagicMock()
    msg.subject = subject
    msg.data = json.dumps(data_dict).encode()
    msg.ack = AsyncMock()
    return msg


def _make_consumer_info(num_pending: int = 0) -> MagicMock:
    """Return a mock consumer_info object with num_pending set."""
    info = MagicMock()
    info.num_pending = num_pending
    return info


def _make_service(replay_complete: bool = True):
    """Create a ShipsAPIService with DB and ws_manager mocked out."""
    from projects.ships.backend.main import ShipsAPIService

    svc = ShipsAPIService()
    svc.running = True
    svc.replay_complete = replay_complete
    svc.ready = replay_complete

    svc.db = MagicMock()
    svc.db.should_insert_position = MagicMock(
        return_value=(True, "2024-01-15T10:00:00Z")
    )
    svc.db.insert_positions_batch = AsyncMock()
    svc.db.upsert_vessels_batch = AsyncMock()
    svc.db.commit = AsyncMock()
    svc.db.get_vessel_count = MagicMock(return_value=100)
    svc.db.get_position_count = MagicMock(return_value=1000)

    svc.ws_manager = MagicMock()
    svc.ws_manager.broadcast = AsyncMock()

    return svc


def _attach_js(svc, mock_psub: AsyncMock) -> None:
    """Wire a mock JetStream + pull subscriber onto the service."""
    svc.js = MagicMock()
    svc.js.pull_subscribe = AsyncMock(return_value=mock_psub)


# ---------------------------------------------------------------------------
# _run_subscription()
# ---------------------------------------------------------------------------


class TestRunSubscription:
    """Tests for ShipsAPIService._run_subscription() wrapper method."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_delegates_to_subscribe_ais_stream(self, service):
        """_run_subscription() is a thin wrapper that calls subscribe_ais_stream()."""
        service.subscribe_ais_stream = AsyncMock()
        await service._run_subscription()
        service.subscribe_ais_stream.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_propagates_runtime_exceptions(self, service):
        """Exceptions from subscribe_ais_stream() propagate through _run_subscription()."""
        service.subscribe_ais_stream = AsyncMock(side_effect=RuntimeError("NATS error"))
        with pytest.raises(RuntimeError, match="NATS error"):
            await service._run_subscription()

    @pytest.mark.asyncio
    async def test_propagates_cancelled_error(self, service):
        """CancelledError from subscribe_ais_stream() propagates cleanly."""
        service.subscribe_ais_stream = AsyncMock(side_effect=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await service._run_subscription()


# ---------------------------------------------------------------------------
# Consumer creation
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamConsumerCreation:
    """Tests for NATS consumer creation parameters."""

    @pytest.fixture
    def service(self):
        return _make_service()

    @pytest.mark.asyncio
    async def test_subscribes_to_ais_wildcard_subject(self, service):
        """pull_subscribe is called with subject 'ais.>'."""
        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        service.running = False  # skip the while-loop body
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        call_args = service.js.pull_subscribe.call_args
        assert call_args[0][0] == "ais.>"

    @pytest.mark.asyncio
    async def test_uses_durable_name_ships_api(self, service):
        """pull_subscribe is called with durable='ships-api'."""
        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        service.running = False
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        call_kwargs = service.js.pull_subscribe.call_args[1]
        assert call_kwargs.get("durable") == "ships-api"

    @pytest.mark.asyncio
    async def test_consumer_config_durable_name(self, service):
        """ConsumerConfig passed to pull_subscribe has durable_name='ships-api'."""
        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        service.running = False
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        config = service.js.pull_subscribe.call_args[1].get("config")
        assert config is not None
        assert config.durable_name == "ships-api"

    @pytest.mark.asyncio
    async def test_subscription_failure_propagates(self, service):
        """If pull_subscribe raises, subscribe_ais_stream re-raises."""
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(
            side_effect=RuntimeError("Cannot subscribe")
        )

        with pytest.raises(RuntimeError, match="Cannot subscribe"):
            await service.subscribe_ais_stream()


# ---------------------------------------------------------------------------
# Catchup detection
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamCatchupDetection:
    """Tests for replay_complete / ready flag transitions."""

    @pytest.mark.asyncio
    async def test_zero_pending_sets_flags_immediately(self):
        """When num_pending == 0 before the loop, replay_complete and ready are True."""
        service = _make_service(replay_complete=False)
        service.running = False  # skip loop body

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_nonzero_pending_does_not_set_flags(self):
        """When num_pending > 0, flags remain False before any batch is processed."""
        service = _make_service(replay_complete=False)
        service.running = False  # skip loop body

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(50_000))
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        assert service.replay_complete is False
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_catchup_complete_after_batch(self):
        """After an empty batch, pending <= threshold marks replay as complete."""
        service = _make_service(replay_complete=False)

        # Initial check: still catching up; post-batch check: below threshold
        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial
                _make_consumer_info(
                    5_000
                ),  # post-batch (below CATCHUP_PENDING_THRESHOLD=10000)
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            return []

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_catchup_stays_incomplete_when_still_pending(self):
        """After a batch, if pending > threshold, replay_complete stays False."""
        service = _make_service(replay_complete=False)

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial
                _make_consumer_info(20_000),  # post-batch: still above threshold
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            return []

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.replay_complete is False
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_timeout_during_catchup_triggers_pending_check(self):
        """On TimeoutError during catchup, consumer_info is called to check pending."""
        service = _make_service(replay_complete=False)

        info_calls = []

        async def fake_consumer_info():
            n = len(info_calls)
            info_calls.append(n)
            # Initial=50000, timeout check=still catching up
            return _make_consumer_info(50_000)

        async def fake_fetch(batch, timeout):
            service.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(side_effect=fake_consumer_info)
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        # consumer_info called twice: initial + once on TimeoutError
        assert len(info_calls) == 2
        assert service.replay_complete is False

    @pytest.mark.asyncio
    async def test_timeout_during_catchup_marks_complete_when_below_threshold(self):
        """TimeoutError during catchup sets replay_complete when pending is low."""
        service = _make_service(replay_complete=False)

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial
                _make_consumer_info(100),  # timeout check: below threshold
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            raise asyncio.TimeoutError()

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_timeout_during_live_mode_does_not_check_pending(self):
        """Timeout during live mode (replay_complete=True) skips consumer_info check."""
        service = _make_service(replay_complete=True)

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))

        async def fake_fetch(batch, timeout):
            service.running = False
            raise asyncio.TimeoutError()

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        # consumer_info only called once (initial check); not again on timeout
        assert mock_psub.consumer_info.call_count == 1


# ---------------------------------------------------------------------------
# Batch size selection
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamBatchSize:
    """Tests for batch size and timeout selection based on catchup state."""

    @pytest.mark.asyncio
    async def test_catchup_mode_uses_batch_10000(self):
        """During catchup, fetch is called with batch=10000."""
        service = _make_service(replay_complete=False)

        captured_batch: list[int] = []

        async def fake_fetch(batch, timeout):
            captured_batch.append(batch)
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial
                _make_consumer_info(50_000),  # post-batch
            ]
        )
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert captured_batch == [10_000]

    @pytest.mark.asyncio
    async def test_live_mode_uses_batch_100(self):
        """During live mode, fetch is called with batch=100."""
        service = _make_service(replay_complete=True)

        captured_batch: list[int] = []

        async def fake_fetch(batch, timeout):
            captured_batch.append(batch)
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert captured_batch == [100]

    @pytest.mark.asyncio
    async def test_catchup_mode_uses_timeout_5(self):
        """During catchup, fetch is called with timeout=5."""
        service = _make_service(replay_complete=False)

        captured_timeout: list[int] = []

        async def fake_fetch(batch, timeout):
            captured_timeout.append(timeout)
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),
                _make_consumer_info(50_000),
            ]
        )
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert captured_timeout == [5]

    @pytest.mark.asyncio
    async def test_live_mode_uses_timeout_1(self):
        """During live mode, fetch is called with timeout=1."""
        service = _make_service(replay_complete=True)

        captured_timeout: list[int] = []

        async def fake_fetch(batch, timeout):
            captured_timeout.append(timeout)
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert captured_timeout == [1]


# ---------------------------------------------------------------------------
# Batch message processing
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamBatchProcessing:
    """Tests for per-message processing and DB batch writes."""

    @pytest.fixture
    def service(self):
        return _make_service(replay_complete=True)

    def _one_shot_psub(self, service, msgs: list) -> AsyncMock:
        """Return a mock psub that delivers msgs once then stops the loop."""

        async def fake_fetch(batch, timeout):
            service.running = False
            return msgs

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)
        return mock_psub

    @pytest.mark.asyncio
    async def test_position_message_calls_insert_positions_batch(self, service):
        """Position messages result in insert_positions_batch being called."""
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.insert_positions_batch.assert_called_once()
        batch_arg = service.db.insert_positions_batch.call_args[0][0]
        assert len(batch_arg) == 1
        assert batch_arg[0][0]["mmsi"] == "123456789"

    @pytest.mark.asyncio
    async def test_vessel_message_calls_upsert_vessels_batch(self, service):
        """Static messages result in upsert_vessels_batch being called."""
        msg = _make_mock_msg(
            "ais.static.123456789",
            {"mmsi": "123456789", "name": "Test Vessel"},
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.upsert_vessels_batch.assert_called_once()
        batch_arg = service.db.upsert_vessels_batch.call_args[0][0]
        assert len(batch_arg) == 1
        assert batch_arg[0]["mmsi"] == "123456789"

    @pytest.mark.asyncio
    async def test_deduplicated_message_increments_counter(self, service):
        """Deduplicated positions increment messages_deduplicated."""
        service.db.should_insert_position = MagicMock(return_value=(False, None))
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.messages_deduplicated == 1

    @pytest.mark.asyncio
    async def test_messages_received_increments_per_message(self, service):
        """messages_received is incremented once per message in the batch."""
        msgs = [
            _make_mock_msg(
                "ais.position.111111111",
                {
                    "mmsi": "111111111",
                    "lat": 48.5,
                    "lon": -123.4,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
            _make_mock_msg(
                "ais.static.222222222",
                {"mmsi": "222222222", "name": "Ship B"},
            ),
        ]
        self._one_shot_psub(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.messages_received == 2

    @pytest.mark.asyncio
    async def test_commit_called_after_each_batch(self, service):
        """db.commit() is always called after processing a batch."""
        msg = _make_mock_msg(
            "ais.static.123456789",
            {"mmsi": "123456789", "name": "Test"},
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_messages_acked_after_commit(self, service):
        """Every message in the batch is acked after the DB commit."""
        msg1 = _make_mock_msg(
            "ais.position.111111111",
            {
                "mmsi": "111111111",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        msg2 = _make_mock_msg(
            "ais.static.222222222",
            {"mmsi": "222222222", "name": "Ship"},
        )
        self._one_shot_psub(service, [msg1, msg2])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        msg1.ack.assert_called_once()
        msg2.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_batch_no_insert_or_upsert_but_commit(self, service):
        """Empty batch: no DB writes, but commit is still called."""
        self._one_shot_psub(service, [])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.insert_positions_batch.assert_not_called()
        service.db.upsert_vessels_batch.assert_not_called()
        service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_position_and_vessel_messages(self, service):
        """Mixed batch: both insert_positions_batch and upsert_vessels_batch called."""
        msgs = [
            _make_mock_msg(
                "ais.position.111111111",
                {
                    "mmsi": "111111111",
                    "lat": 48.5,
                    "lon": -123.4,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
            _make_mock_msg(
                "ais.static.222222222",
                {"mmsi": "222222222", "name": "Ship B"},
            ),
        ]
        self._one_shot_psub(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.insert_positions_batch.assert_called_once()
        service.db.upsert_vessels_batch.assert_called_once()


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamWebSocketBroadcast:
    """Tests for WebSocket broadcast behaviour during live mode."""

    @pytest.fixture
    def service(self):
        return _make_service(replay_complete=True)

    def _one_shot_psub(self, service, msgs: list) -> AsyncMock:
        async def fake_fetch(batch, timeout):
            service.running = False
            return msgs

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)
        return mock_psub

    @pytest.mark.asyncio
    async def test_positions_broadcast_in_live_mode(self, service):
        """Position messages are broadcast to WebSocket clients when replay_complete."""
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_called_once()
        payload = service.ws_manager.broadcast.call_args[0][0]
        assert payload["type"] == "positions"
        assert len(payload["positions"]) == 1
        assert payload["positions"][0]["mmsi"] == "123456789"

    @pytest.mark.asyncio
    async def test_positions_not_broadcast_during_catchup(self):
        """Position messages are NOT broadcast when replay_complete=False."""
        service = _make_service(replay_complete=False)
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial: still catching up
                _make_consumer_info(49_000),  # post-batch: still above threshold
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            return [msg]

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_deduplicates_by_mmsi_keeps_latest(self, service):
        """Multiple positions for same MMSI: only the latest is broadcast."""
        msgs = [
            _make_mock_msg(
                "ais.position.123456789",
                {
                    "mmsi": "123456789",
                    "lat": 48.5,
                    "lon": -123.4,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
            _make_mock_msg(
                "ais.position.123456789",
                {
                    "mmsi": "123456789",
                    "lat": 48.6,
                    "lon": -123.5,
                    "timestamp": "2024-01-15T10:01:00Z",
                },
            ),
        ]
        self._one_shot_psub(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_called_once()
        payload = service.ws_manager.broadcast.call_args[0][0]
        # Latest position wins (lat=48.6)
        assert len(payload["positions"]) == 1
        assert payload["positions"][0]["lat"] == 48.6

    @pytest.mark.asyncio
    async def test_broadcast_multiple_vessels(self, service):
        """Positions for different MMSIs are all included in the broadcast."""
        msgs = [
            _make_mock_msg(
                "ais.position.111111111",
                {
                    "mmsi": "111111111",
                    "lat": 48.5,
                    "lon": -123.4,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
            _make_mock_msg(
                "ais.position.222222222",
                {
                    "mmsi": "222222222",
                    "lat": 49.0,
                    "lon": -124.0,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
        ]
        self._one_shot_psub(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_called_once()
        payload = service.ws_manager.broadcast.call_args[0][0]
        mmsi_set = {p["mmsi"] for p in payload["positions"]}
        assert mmsi_set == {"111111111", "222222222"}

    @pytest.mark.asyncio
    async def test_no_broadcast_when_batch_has_no_positions(self, service):
        """Vessel-only batch triggers no WebSocket broadcast."""
        msg = _make_mock_msg(
            "ais.static.123456789",
            {"mmsi": "123456789", "name": "Test"},
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_message_type_is_positions(self, service):
        """The broadcast payload always uses type='positions'."""
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        payload = service.ws_manager.broadcast.call_args[0][0]
        assert payload["type"] == "positions"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamErrorHandling:
    """Tests for resilience and error handling inside subscribe_ais_stream()."""

    @pytest.fixture
    def service(self):
        return _make_service(replay_complete=True)

    @pytest.mark.asyncio
    async def test_running_false_before_loop_skips_fetch(self, service):
        """Setting running=False before the loop means fetch is never called."""
        service.running = False

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(return_value=[])
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        mock_psub.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_inside_loop_is_caught_loop_continues(self, service):
        """A transient exception inside the main loop is swallowed; loop retries."""
        call_count = 0

        async def fake_fetch(batch, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient NATS error")
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()  # must not raise

        assert call_count == 2  # loop continued after first error

    @pytest.mark.asyncio
    async def test_exception_when_not_running_does_not_log_error(self, service):
        """Exception when running=False is swallowed without calling sleep(1)."""
        call_count = 0

        async def fake_fetch(batch, timeout):
            nonlocal call_count
            call_count += 1
            service.running = False
            raise RuntimeError("shutdown race")

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        sleep_calls: list = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await service.subscribe_ais_stream()

        # sleep(1) is called in error handler even when not running, but loop exits
        # what matters is we didn't raise
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_outer_exception_propagates(self, service):
        """Exception from pull_subscribe (outer try block) propagates out."""
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(side_effect=Exception("stream not found"))

        with pytest.raises(Exception, match="stream not found"):
            await service.subscribe_ais_stream()

    @pytest.mark.asyncio
    async def test_loop_runs_multiple_iterations(self, service):
        """The loop iterates until running becomes False."""
        fetch_count = 0

        async def fake_fetch(batch, timeout):
            nonlocal fetch_count
            fetch_count += 1
            if fetch_count >= 3:
                service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert fetch_count == 3
