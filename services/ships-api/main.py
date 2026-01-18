"""
Ships API Service

Serves AIS vessel data via REST API and WebSocket.
- Replays NATS JetStream on startup to build in-memory vessel cache
- Subscribes to live updates and broadcasts to WebSocket clients
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration from environment
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")


class VesselCache:
    """In-memory cache for vessel positions, keyed by MMSI."""

    def __init__(self):
        self.vessels: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def update(self, mmsi: str, data: dict) -> None:
        """Update vessel position in cache."""
        async with self.lock:
            self.vessels[mmsi] = data

    async def get(self, mmsi: str) -> dict | None:
        """Get vessel by MMSI."""
        async with self.lock:
            return self.vessels.get(mmsi)

    async def get_all(self) -> list[dict]:
        """Get all vessels."""
        async with self.lock:
            return list(self.vessels.values())

    async def count(self) -> int:
        """Get vessel count."""
        async with self.lock:
            return len(self.vessels)


class WebSocketManager:
    """Manages WebSocket connections for live updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept new WebSocket connection."""
        await websocket.accept()
        async with self.lock:
            self.active_connections.append(websocket)
        logger.info(
            f"WebSocket client connected. Total: {len(self.active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove disconnected WebSocket."""
        async with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket client disconnected. Total: {len(self.active_connections)}"
        )

    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connected clients."""
        async with self.lock:
            connections = self.active_connections.copy()

        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            await self.disconnect(connection)

    async def client_count(self) -> int:
        """Get number of connected clients."""
        async with self.lock:
            return len(self.active_connections)


class ShipsAPIService:
    """Ships API service with NATS integration."""

    def __init__(self):
        self.nc: nats.NATS | None = None
        self.js: nats.js.JetStreamContext | None = None
        self.cache = VesselCache()
        self.ws_manager = WebSocketManager()
        self.running = False
        self.ready = False
        self.replay_task: asyncio.Task | None = None
        self.messages_received = 0
        self.replay_complete = False
        self.replay_count = 0

    async def connect_nats(self) -> None:
        """Connect to NATS."""
        logger.info(f"Connecting to NATS at {NATS_URL}")
        self.nc = await nats.connect(NATS_URL)
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS")

    async def replay_stream(self) -> None:
        """Replay the ais stream to build initial vessel cache (runs in background)."""
        logger.info("Starting AIS stream replay in background...")

        try:
            # Create ephemeral consumer starting from the beginning
            consumer_config = ConsumerConfig(
                deliver_policy=DeliverPolicy.ALL,
                ack_wait=30,
            )

            # Subscribe with pull consumer for replay
            psub = await self.js.pull_subscribe(
                "ais.position.>",
                durable=None,
                config=consumer_config,
            )

            while self.running:
                try:
                    # Fetch messages in batches
                    msgs = await psub.fetch(batch=100, timeout=2)
                    if not msgs:
                        break

                    for msg in msgs:
                        await self._process_message(msg.data, broadcast=False)
                        await msg.ack()
                        self.replay_count += 1

                    # Log progress periodically
                    if self.replay_count % 1000 == 0:
                        logger.info(f"Replay progress: {self.replay_count} messages")

                except asyncio.TimeoutError:
                    # No more messages to replay
                    break
                except Exception as e:
                    logger.warning(f"Error during replay: {e}")
                    break

            await psub.unsubscribe()
            vessel_count = await self.cache.count()
            logger.info(
                f"Replay complete. Loaded {self.replay_count} positions for {vessel_count} vessels"
            )
            self.replay_complete = True

        except Exception as e:
            logger.error(f"Failed to replay stream: {e}")
            # Mark as complete anyway so we can still receive live updates
            self.replay_complete = True

    async def subscribe_live(self) -> None:
        """Subscribe to live vessel position updates."""
        logger.info("Subscribing to live AIS updates...")

        try:
            # Create push consumer for live updates
            consumer_config = ConsumerConfig(
                deliver_policy=DeliverPolicy.NEW,
                ack_wait=30,
            )

            psub = await self.js.pull_subscribe(
                "ais.position.>",
                durable=None,
                config=consumer_config,
            )

            self.ready = True
            logger.info("Subscribed to live updates")

            while self.running:
                try:
                    msgs = await psub.fetch(batch=10, timeout=1)
                    for msg in msgs:
                        await self._process_message(msg.data)
                        await msg.ack()
                        self.messages_received += 1
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error receiving message: {e}")
                    break

        except Exception as e:
            logger.error(f"Failed to subscribe to live updates: {e}")
            self.ready = False

    async def _process_message(self, data: bytes, broadcast: bool = True) -> None:
        """Process a vessel position message."""
        try:
            position = json.loads(data)
            mmsi = position.get("mmsi")
            if mmsi:
                await self.cache.update(mmsi, position)
                # Broadcast to WebSocket clients (skip during replay)
                if broadcast and self.replay_complete:
                    await self.ws_manager.broadcast(position)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse message: {e}")

    async def start(self) -> None:
        """Start the Ships API service."""
        self.running = True

        # Connect to NATS
        await self.connect_nats()

        # Start replay in background (non-blocking so liveness checks work)
        self.replay_task = asyncio.create_task(self._replay_and_subscribe())

        logger.info("Ships API service started (replay running in background)")

    async def _replay_and_subscribe(self) -> None:
        """Replay stream then start live subscription."""
        # Replay historical data first
        await self.replay_stream()

        # Only mark ready after replay completes
        self.ready = True
        logger.info("Service ready - replay complete")

        # Start live subscription
        await self.subscribe_live()

    async def stop(self) -> None:
        """Stop the Ships API service."""
        logger.info("Stopping Ships API service...")
        self.running = False
        self.ready = False

        # Cancel background task
        if self.replay_task:
            self.replay_task.cancel()
            try:
                await self.replay_task
            except asyncio.CancelledError:
                pass

        if self.nc:
            await self.nc.close()
            logger.info("NATS connection closed")

        logger.info("Ships API service stopped")


# Global service instance
service = ShipsAPIService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    try:
        await service.start()
    except Exception as e:
        logger.error(f"Failed to start service: {e}")

    yield

    await service.stop()


# Create FastAPI app
app = FastAPI(
    title="Ships API",
    description="Real-time vessel tracking API",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Liveness probe - returns 200 if the service is alive."""
    vessel_count = await service.cache.count()
    return {
        "status": "alive",
        "nats_connected": service.nc is not None and service.nc.is_connected,
        "vessel_count": vessel_count,
        "replay_complete": service.replay_complete,
        "replay_count": service.replay_count,
    }


@app.get("/ready")
async def ready(response: Response):
    """Readiness probe - returns 200 only when ready to serve traffic."""
    vessel_count = await service.cache.count()
    if not service.ready:
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": "replay_in_progress" if not service.replay_complete else "starting",
            "vessel_count": vessel_count,
            "replay_count": service.replay_count,
        }
    return {
        "status": "ready",
        "vessel_count": vessel_count,
    }


@app.get("/api/vessels")
async def list_vessels():
    """List all vessels with latest positions."""
    vessels = await service.cache.get_all()
    return {
        "count": len(vessels),
        "vessels": vessels,
    }


@app.get("/api/vessels/{mmsi}")
async def get_vessel(mmsi: str):
    """Get single vessel by MMSI."""
    vessel = await service.cache.get(mmsi)
    if vessel is None:
        return {"error": "Vessel not found"}, 404
    return vessel


@app.get("/api/stats")
async def get_stats():
    """Get service statistics."""
    vessel_count = await service.cache.count()
    client_count = await service.ws_manager.client_count()
    return {
        "vessel_count": vessel_count,
        "messages_received": service.messages_received,
        "connected_clients": client_count,
        "replay_complete": service.replay_complete,
    }


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """WebSocket endpoint for real-time vessel updates."""
    await service.ws_manager.connect(websocket)
    try:
        # Send current vessels on connect
        vessels = await service.cache.get_all()
        await websocket.send_json(
            {
                "type": "snapshot",
                "vessels": vessels,
            }
        )

        # Keep connection alive, updates are pushed via broadcast
        while True:
            # Wait for client messages (ping/pong or close)
            try:
                data = await websocket.receive_text()
                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    finally:
        await service.ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
