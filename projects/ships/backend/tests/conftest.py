"""
Pytest fixtures for Ships API tests.

Provides:
- Async test client for FastAPI
- Mock database with in-memory SQLite
- Mock NATS connection
- Sample vessel/position data
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set environment variables before importing main
os.environ["NATS_URL"] = "nats://localhost:4222"
os.environ["DB_PATH"] = ":memory:"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"


@pytest.fixture
def sample_position_data() -> dict:
    """Sample AIS position message data."""
    return {
        "mmsi": "123456789",
        "lat": 51.5074,
        "lon": -0.1278,
        "speed": 12.5,
        "course": 180.0,
        "heading": 175,
        "nav_status": 0,
        "rate_of_turn": 0,
        "position_accuracy": 1,
        "ship_name": "TEST VESSEL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_vessel_data() -> dict:
    """Sample AIS static message data."""
    return {
        "mmsi": "123456789",
        "imo": "IMO1234567",
        "call_sign": "CALL1",
        "name": "TEST VESSEL",
        "ship_type": 70,
        "dimension_a": 100,
        "dimension_b": 50,
        "dimension_c": 20,
        "dimension_d": 10,
        "destination": "LONDON",
        "eta": "2025-01-15T12:00:00Z",
        "draught": 8.5,
    }


@pytest.fixture
def multiple_vessels_data() -> list[dict]:
    """Multiple vessel position data for testing list endpoints."""
    base_time = datetime.now(timezone.utc)
    return [
        {
            "mmsi": "111111111",
            "lat": 51.5074,
            "lon": -0.1278,
            "speed": 10.0,
            "course": 90.0,
            "heading": 85,
            "nav_status": 0,
            "ship_name": "VESSEL ONE",
            "timestamp": base_time.isoformat(),
        },
        {
            "mmsi": "222222222",
            "lat": 52.2053,
            "lon": 0.1218,
            "speed": 15.0,
            "course": 270.0,
            "heading": 268,
            "nav_status": 0,
            "ship_name": "VESSEL TWO",
            "timestamp": base_time.isoformat(),
        },
        {
            "mmsi": "333333333",
            "lat": 53.4808,
            "lon": -2.2426,
            "speed": 0.0,
            "course": 0.0,
            "heading": 0,
            "nav_status": 1,
            "ship_name": "VESSEL THREE",
            "timestamp": base_time.isoformat(),
        },
    ]


@pytest.fixture
def track_data() -> list[dict]:
    """Position history for track testing."""
    base_time = datetime.now(timezone.utc)
    return [
        {
            "mmsi": "123456789",
            "lat": 51.5074 + i * 0.01,
            "lon": -0.1278 + i * 0.01,
            "speed": 12.0,
            "course": 45.0,
            "heading": 43,
            "nav_status": 0,
            "ship_name": "TEST VESSEL",
            "timestamp": base_time.replace(hour=i).isoformat(),
        }
        for i in range(10)
    ]


class MockNATSMessage:
    """Mock NATS message for testing."""

    def __init__(self, subject: str, data: dict):
        self.subject = subject
        self.data = json.dumps(data).encode()
        self._acked = False

    async def ack(self):
        self._acked = True


class MockNATSSubscription:
    """Mock NATS pull subscription."""

    def __init__(self, messages: list[MockNATSMessage] | None = None):
        self.messages = messages or []
        self._fetch_count = 0

    async def fetch(self, batch: int = 100, timeout: float = 1.0):
        if self._fetch_count >= len(self.messages):
            raise asyncio.TimeoutError()
        start = self._fetch_count
        end = min(start + batch, len(self.messages))
        self._fetch_count = end
        return self.messages[start:end]

    async def consumer_info(self):
        info = MagicMock()
        info.num_pending = max(0, len(self.messages) - self._fetch_count)
        return info


class MockJetStreamContext:
    """Mock NATS JetStream context."""

    def __init__(self, subscription: MockNATSSubscription | None = None):
        self.subscription = subscription or MockNATSSubscription()

    async def pull_subscribe(self, subject: str, durable: str, config=None):
        return self.subscription


class MockNATSConnection:
    """Mock NATS connection."""

    def __init__(self):
        self._connected = True
        self._js = MockJetStreamContext()

    @property
    def is_connected(self):
        return self._connected

    def jetstream(self):
        return self._js

    async def close(self):
        self._connected = False


@pytest.fixture
def mock_nats_connection():
    """Provide a mock NATS connection."""
    return MockNATSConnection()


@pytest.fixture
def mock_nats_subscription():
    """Provide a mock NATS subscription."""
    return MockNATSSubscription()


@pytest_asyncio.fixture
async def test_db():
    """Create a test database instance with in-memory SQLite."""
    from projects.ships.backend.main import Database

    db = Database(":memory:")
    await db.connect()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked NATS."""
    # Patch NATS connection before importing app
    with patch("main.nats.connect") as mock_connect:
        mock_nc = MockNATSConnection()
        mock_connect.return_value = mock_nc

        # Import app after patching
        from projects.ships.backend.main import app, service

        # Manually initialize for testing without NATS subscription loop
        service.running = True
        service.ready = True
        service.replay_complete = True
        service.nc = mock_nc
        service.js = mock_nc.jetstream()

        # Initialize database with in-memory SQLite
        service.db.db_path = ":memory:"
        await service.db.connect()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Cleanup
        await service.db.close()
        service.running = False


@pytest_asyncio.fixture
async def test_client_with_data(
    test_client: AsyncClient, multiple_vessels_data: list[dict]
) -> AsyncClient:
    """Test client with pre-populated vessel data."""
    from projects.ships.backend.main import service

    # Insert test data
    positions = [(v, v["timestamp"]) for v in multiple_vessels_data]
    await service.db.insert_positions_batch(positions)
    await service.db.commit()

    return test_client


@pytest.fixture
def mock_websocket():
    """Mock WebSocket for testing."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock(return_value="ping")
    return ws
