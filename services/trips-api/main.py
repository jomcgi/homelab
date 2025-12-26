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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
TRIP_API_KEY = os.getenv("TRIP_API_KEY", "")


class TripPoint(BaseModel):
    id: int
    lat: float
    lng: float
    timestamp: str
    image_url: str
    thumb_url: str
    location: Optional[str] = None
    animal: Optional[str] = None


class ConnectionManager:
    """Manages WebSocket connections for live updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


class TripsState:
    """In-memory state for trip points."""

    def __init__(self):
        self.points: dict[int, TripPoint] = {}
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
            # Get consumer for replay (deliver all)
            consumer = await self.js.pull_subscribe(
                "trips.>",
                durable="trips-api-replay",
                stream="trips"
            )

            # Fetch all existing messages
            while True:
                try:
                    msgs = await consumer.fetch(batch=100, timeout=1)
                    for msg in msgs:
                        await self._process_message(msg.data)
                        await msg.ack()
                except nats.errors.TimeoutError:
                    break

            logger.info(f"Replayed {len(self.points)} points from stream")

        except nats.js.errors.StreamNotFoundError:
            logger.warning("Stream 'trips' not found - starting with empty cache")
        except Exception as e:
            logger.error(f"Error replaying stream: {e}")

    async def subscribe_live(self):
        """Subscribe to live updates."""
        try:
            self.subscription = await self.js.subscribe(
                "trips.>",
                durable="trips-api-live",
                stream="trips",
                deliver_policy=nats.js.api.DeliverPolicy.NEW
            )

            # Start background task to process messages
            asyncio.create_task(self._process_subscription())
            logger.info("Subscribed to live updates")

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
                    await self.manager.broadcast({
                        "type": "new_point",
                        "point": point.model_dump()
                    })
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def _process_message(self, data: bytes) -> Optional[TripPoint]:
        """Process a single message and add to cache."""
        try:
            point_data = json.loads(data.decode())
            point = TripPoint(**point_data)
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

    def get_points(self, limit: Optional[int] = None, offset: int = 0) -> list[TripPoint]:
        """Get points with optional pagination."""
        points = sorted(self.points.values(), key=lambda p: p.id)
        if offset:
            points = points[offset:]
        if limit:
            points = points[:limit]
        return points

    def get_point(self, point_id: int) -> Optional[TripPoint]:
        """Get a single point by ID."""
        return self.points.get(point_id)

    def get_stats(self) -> dict:
        """Get trip statistics."""
        points = list(self.points.values())
        wildlife_count = sum(1 for p in points if p.animal)

        return {
            "total_points": len(points),
            "wildlife_sightings": wildlife_count,
            "connected_clients": len(self.manager.active_connections)
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
    lifespan=lifespan
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
        "connected_clients": len(state.manager.active_connections)
    }


@app.get("/api/points")
async def get_points(limit: Optional[int] = None, offset: int = 0):
    """Get all trip points with optional pagination."""
    points = state.get_points(limit=limit, offset=offset)
    return {
        "points": [p.model_dump() for p in points],
        "total": len(state.points)
    }


@app.get("/api/points/{point_id}")
async def get_point(point_id: int):
    """Get a single point by ID."""
    point = state.get_point(point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Point not found")
    return point.model_dump()


@app.get("/api/stats")
async def get_stats():
    """Get trip statistics."""
    return state.get_stats()


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """WebSocket endpoint for live updates."""
    await state.manager.connect(websocket)

    # Send initial connected message
    await websocket.send_json({
        "type": "connected",
        "cached_points": len(state.points)
    })

    try:
        while True:
            # Handle ping/pong for keepalive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        state.manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
