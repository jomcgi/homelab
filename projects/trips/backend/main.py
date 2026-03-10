"""
Trips API Server

FastAPI server that:
1. On startup: Replays entire NATS stream to build in-memory cache
2. Serves REST API for initial data load
3. Subscribes to NATS for new points
4. Broadcasts new points to WebSocket clients
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import nats
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    UploadFile,
    File,
    Header,
    Depends,
    Security,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")
TRIP_API_KEY = os.getenv("TRIP_API_KEY", "")

# API key authentication
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    """Validate the X-API-Key header against the configured TRIP_API_KEY.

    When TRIP_API_KEY is empty (e.g. local dev), auth is disabled and all
    requests are allowed through. When it is set, every request must supply
    a matching X-API-Key header or receive a 401.
    """
    if not TRIP_API_KEY:
        # Auth not configured — allow through (dev / test mode).
        return ""
    if api_key == TRIP_API_KEY:
        return api_key
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


class TripPoint(BaseModel):
    id: str  # Deterministic ID derived from image key (e.g., "abc123def456")
    lat: float
    lng: float
    timestamp: str
    image: str | None = None  # Filename or None for gap points (route-only, no image)
    source: str = (
        "gopro"  # Image source: gopro, camera, phone, or "gap" for inferred routes
    )
    tags: list[str] = ["car"]  # User-defined tags; defaults to "car" for existing data
    elevation: float | None = None  # Elevation in meters (from NRCan CDEM API)
    # OPTICS - Camera exposure data from EXIF
    light_value: float | None = (
        None  # Exposure Value (EV) - e.g., 8.6 for dim conditions
    )
    iso: int | None = None  # ISO sensitivity - e.g., 393
    shutter_speed: str | None = None  # Shutter speed as string - e.g., "1/240"
    aperture: float | None = None  # F-number - e.g., 2.5
    focal_length_35mm: int | None = None  # Focal length in 35mm equivalent - e.g., 16


def is_valid_coordinates(lat: float, lng: float) -> bool:
    """Check if coordinates are valid (not null island, within valid ranges)."""
    # Reject null island (0, 0) - common GPS error
    if lat == 0.0 and lng == 0.0:
        return False
    # Reject out-of-range coordinates
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return False
    return True


class ConnectionManager:
    """Manages WebSocket connections for live updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
        # Broadcast updated viewer count to all clients
        await self.broadcast_viewer_count()

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
        # Broadcast updated viewer count to all clients
        await self.broadcast_viewer_count()

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    async def broadcast_viewer_count(self):
        """Broadcast current viewer count to all clients."""
        await self.broadcast(
            {"type": "viewer_count", "count": len(self.active_connections)}
        )


class TripsState:
    """In-memory state for trip points."""

    def __init__(self):
        self.points: dict[str, TripPoint] = {}
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[nats.js.JetStreamContext] = None
        self.subscription = None
        self.manager = ConnectionManager()
        self.ready = False

    async def connect(self):
        """Connect to NATS and replay stream."""
        logger.info(f"Connecting to NATS at {NATS_URL}")
        self.nc = await nats.connect(NATS_URL)
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS")

        # Replay existing messages from stream
        await self.replay_stream()

        # Subscribe to new messages
        await self.subscribe_live()

        self.ready = True
        logger.info(f"Ready with {len(self.points)} points cached")

    async def replay_stream(self):
        """Replay all messages from the trips stream."""
        try:
            # Use ephemeral consumer for replay (no durable name)
            # This ensures each pod restart gets all messages from the beginning
            consumer = await self.js.pull_subscribe(
                "trips.>",
                stream="trips",
                config=nats.js.api.ConsumerConfig(
                    deliver_policy=nats.js.api.DeliverPolicy.ALL,
                    ack_policy=nats.js.api.AckPolicy.NONE,  # No ack needed for replay
                ),
            )

            # Fetch all existing messages
            while True:
                try:
                    msgs = await consumer.fetch(batch=100, timeout=1)
                    for msg in msgs:
                        await self._process_message(msg.data)
                except nats.errors.TimeoutError:
                    break

            # Clean up ephemeral consumer
            await consumer.unsubscribe()

            logger.info(f"Replayed {len(self.points)} points from stream")

        except nats.js.errors.NotFoundError:
            logger.warning("Stream 'trips' not found - starting with empty cache")
        except Exception as e:
            logger.error(f"Error replaying stream: {e}")

    async def subscribe_live(self):
        """Subscribe to live updates."""
        try:
            # Use pod-specific durable name to avoid conflicts between replicas
            # HOSTNAME is set to pod name in Kubernetes
            pod_name = os.getenv("HOSTNAME", "unknown")
            consumer_name = f"trips-api-live-{pod_name}"

            self.subscription = await self.js.subscribe(
                "trips.>",
                durable=consumer_name,
                stream="trips",
                config=nats.js.api.ConsumerConfig(
                    deliver_policy=nats.js.api.DeliverPolicy.NEW,
                    inactive_threshold=3600.0,  # Auto-cleanup after 1 hour of inactivity
                ),
            )

            # Start background task to process messages
            asyncio.create_task(self._process_subscription())
            logger.info(f"Subscribed to live updates as {consumer_name}")

        except Exception as e:
            logger.error(f"Error subscribing to live updates: {e}")

    async def _process_subscription(self):
        """Process incoming messages from subscription."""
        async for msg in self.subscription.messages:
            try:
                point = await self._process_message(msg.data)
                await msg.ack()

                # Broadcast to WebSocket clients
                if point:
                    if isinstance(point, dict) and point.get("deleted"):
                        await self.manager.broadcast(
                            {"type": "delete_point", "id": point["id"]}
                        )
                    else:
                        await self.manager.broadcast(
                            {"type": "new_point", "point": point.model_dump()}
                        )
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def _process_message(self, data: bytes) -> Optional[TripPoint | dict]:
        """Process a single message and add to or remove from cache.

        Supports tombstone messages for deletion: {"id": "point_id", "deleted": true}
        """
        try:
            point_data = json.loads(data.decode())

            # Handle tombstone/delete messages
            if point_data.get("deleted"):
                point_id = point_data.get("id")
                if point_id and point_id in self.points:
                    del self.points[point_id]
                    logger.info(f"Deleted point {point_id}")
                    return {"id": point_id, "deleted": True}
                return None

            point = TripPoint(**point_data)
            # Skip points with invalid coordinates
            if not is_valid_coordinates(point.lat, point.lng):
                logger.warning(
                    f"Skipping point {point.id} with invalid coords: ({point.lat}, {point.lng})"
                )
                return None
            self.points[point.id] = point
            return point
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None

    async def close(self):
        """Close NATS connection."""
        if self.subscription:
            await self.subscription.unsubscribe()
        if self.nc:
            await self.nc.close()
        logger.info("NATS connection closed")

    def get_points(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> list[TripPoint]:
        """Get points with optional pagination, sorted by timestamp."""
        points = sorted(self.points.values(), key=lambda p: p.timestamp)
        if offset:
            points = points[offset:]
        if limit:
            points = points[:limit]
        return points

    def get_point(self, point_id: str) -> Optional[TripPoint]:
        """Get a single point by ID."""
        return self.points.get(point_id)

    def get_stats(self) -> dict:
        """Get trip statistics."""
        return {
            "total_points": len(self.points),
            "connected_clients": len(self.manager.active_connections),
        }


# Global state
state = TripsState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    try:
        await state.connect()
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        # Continue anyway - health check will report not ready

    yield

    # Shutdown
    await state.close()


# Create FastAPI app
app = FastAPI(
    title="Trips API",
    description="API for Yukon Trip Tracker",
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

# Try to add OTEL instrumentation
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry instrumentation enabled")
except ImportError:
    logger.info("OpenTelemetry not available - skipping instrumentation")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy" if state.ready else "starting",
        "points": len(state.points),
        "connected_clients": len(state.manager.active_connections),
    }


@app.get("/api/points")
async def get_points(
    limit: Optional[int] = None,
    offset: int = 0,
    _: str = Depends(require_api_key),
):
    """Get all trip points with optional pagination."""
    points = state.get_points(limit=limit, offset=offset)
    return {"points": [p.model_dump() for p in points], "total": len(state.points)}


@app.get("/api/points/{point_id}")
async def get_point(point_id: str, _: str = Depends(require_api_key)):
    """Get a single point by ID."""
    point = state.get_point(point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Point not found")
    return point.model_dump()


@app.get("/api/stats")
async def get_stats(_: str = Depends(require_api_key)):
    """Get trip statistics."""
    return state.get_stats()


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """WebSocket endpoint for live updates."""
    await state.manager.connect(websocket)

    # Send initial connected message
    await websocket.send_json({"type": "connected", "cached_points": len(state.points)})

    try:
        while True:
            # Handle ping/pong for keepalive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await state.manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
