"""
Tests for AISIngestService reconnect delay cap and ConnectionClosed mid-loop.

Covers remaining gaps not addressed by subscribe_test.py:

1. Reconnect delay caps at MAX_RECONNECT_DELAY (60 s) — existing tests confirm
   the delay *increases* but don't verify it stops growing beyond 60 s.

2. ConnectionClosed raised during *message iteration* (not on __aenter__) —
   the existing subscribe_test.py raises on __aenter__; here we raise it inside
   the async-for loop to exercise the same outer except clause via a different
   code path.

3. AISSTREAM_API_KEY is included verbatim in the subscription message.
"""

import asyncio
import json
from unittest.mock import patch

import pytest
import websockets.exceptions

from projects.ships.ingest.main import (
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    RECONNECT_BACKOFF_FACTOR,
    AISIngestService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _EmptyWS:
    """WebSocket that returns no messages and exits the loop immediately."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, _msg):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _AlwaysFailWS:
    """WebSocket whose connect always raises a generic Exception."""

    async def __aenter__(self):
        raise Exception("connection refused")

    async def __aexit__(self, *args):
        pass


class _ConnectionClosedDuringIterWS:
    """WebSocket that raises ConnectionClosed during the async-for message loop."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, _msg):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise websockets.exceptions.ConnectionClosed(rcvd=None, sent=None)


# ---------------------------------------------------------------------------
# 1. Reconnect delay caps at MAX_RECONNECT_DELAY
# ---------------------------------------------------------------------------


class TestReconnectDelayCap:
    """Reconnect delay must not grow beyond MAX_RECONNECT_DELAY (60 s)."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_delay_caps_at_max_reconnect_delay(self, service):
        """After enough failures the delay stabilises at MAX_RECONNECT_DELAY."""
        service.running = True
        sleep_delays: list[float] = []

        # Enough iterations to guarantee we hit the cap
        # INITIAL=1.0, FACTOR=2.0 → 1,2,4,8,16,32,64(→60),60,60,...
        max_iterations = 10

        async def fake_sleep(delay: float):
            sleep_delays.append(delay)
            if len(sleep_delays) >= max_iterations:
                service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_AlwaysFailWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        # All delays must be ≤ MAX_RECONNECT_DELAY
        for d in sleep_delays:
            assert d <= MAX_RECONNECT_DELAY, (
                f"Delay {d} exceeds MAX_RECONNECT_DELAY={MAX_RECONNECT_DELAY}"
            )

        # Once capped, consecutive delays stay equal to MAX_RECONNECT_DELAY
        # (they don't keep growing)
        capped = [d for d in sleep_delays if d >= MAX_RECONNECT_DELAY]
        assert len(capped) >= 1, (
            "Expected at least one delay to reach MAX_RECONNECT_DELAY"
        )
        for d in capped:
            assert d == MAX_RECONNECT_DELAY, (
                f"Capped delay {d} ≠ MAX_RECONNECT_DELAY={MAX_RECONNECT_DELAY}"
            )

    @pytest.mark.asyncio
    async def test_delay_doubles_before_cap(self, service):
        """Delay doubles correctly before hitting the cap."""
        service.running = True
        sleep_delays: list[float] = []

        async def fake_sleep(delay: float):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 4:
                service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_AlwaysFailWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert len(sleep_delays) >= 2
        # First delay is INITIAL_RECONNECT_DELAY
        assert sleep_delays[0] == INITIAL_RECONNECT_DELAY
        # Second delay is INITIAL * FACTOR
        assert sleep_delays[1] == pytest.approx(
            INITIAL_RECONNECT_DELAY * RECONNECT_BACKOFF_FACTOR
        )


# ---------------------------------------------------------------------------
# 2. ConnectionClosed raised during message iteration
# ---------------------------------------------------------------------------


class TestConnectionClosedDuringIteration:
    """ConnectionClosed raised inside the async-for message loop is caught."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_connection_closed_mid_loop_does_not_propagate(self, service):
        """ConnectionClosed during message iteration is caught; loop continues."""
        service.running = True

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ConnectionClosedDuringIterWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            # Must not raise
            await service.subscribe_to_aisstream()

        assert service.running is False

    @pytest.mark.asyncio
    async def test_ready_reset_after_connection_closed_mid_loop(self, service):
        """After ConnectionClosed mid-iteration, ready is reset to False."""
        service.running = True
        service.ready = True  # pretend it was connected

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ConnectionClosedDuringIterWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert service.ready is False


# ---------------------------------------------------------------------------
# 3. AISSTREAM_API_KEY in subscription message
# ---------------------------------------------------------------------------


class TestSubscriptionApiKey:
    """AISSTREAM_API_KEY is included in the subscription message sent to the WS."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_api_key_included_in_subscription(self, service):
        """The subscription JSON contains the AISSTREAM_API_KEY value."""
        service.running = True
        sent_messages: list[str] = []

        class _CaptureSendWS(_EmptyWS):
            async def send(self, msg: str):
                sent_messages.append(msg)

        fake_key = "test-api-key-12345"
        async def fake_sleep(_):
            service.running = False

        with (
            patch("projects.ships.ingest.main.AISSTREAM_API_KEY", fake_key),
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_CaptureSendWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert len(sent_messages) == 1, "Expected exactly one message to be sent"
        payload = json.loads(sent_messages[0])
        assert payload["APIKey"] == fake_key, (
            f"Expected APIKey={fake_key!r}, got {payload.get('APIKey')!r}"
        )

    @pytest.mark.asyncio
    async def test_filter_message_types_in_subscription(self, service):
        """FilterMessageTypes contains both PositionReport and ShipStaticData."""
        service.running = True
        sent_messages: list[str] = []

        class _CaptureSendWS(_EmptyWS):
            async def send(self, msg: str):
                sent_messages.append(msg)

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_CaptureSendWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        payload = json.loads(sent_messages[0])
        assert "PositionReport" in payload["FilterMessageTypes"]
        assert "ShipStaticData" in payload["FilterMessageTypes"]
