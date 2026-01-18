"""
Ships API Service

Serves AIS vessel data via REST API and WebSocket.
- Replays NATS JetStream on startup to build SQLite database
- Subscribes to live updates and broadcasts to WebSocket clients
- Stores full vessel metadata and position history
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite
import nats
from nats.js.api import ConsumerConfig, DeliverPolicy
from fastapi import FastAPI, Query, Response, WebSocket, WebSocketDisconnect
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
DB_PATH = os.getenv("DB_PATH", "/tmp/ships.db")

# SQL Schema
SCHEMA = """
-- Vessel metadata (updated from static data messages)
CREATE TABLE IF NOT EXISTS vessels (
    mmsi TEXT PRIMARY KEY,
    imo TEXT,
    call_sign TEXT,
    name TEXT,
    ship_type INTEGER,
    dimension_a INTEGER,
    dimension_b INTEGER,
    dimension_c INTEGER,
    dimension_d INTEGER,
    destination TEXT,
    eta TEXT,
    draught REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Position history (append-only)
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mmsi TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    speed REAL,
    course REAL,
    heading INTEGER,
    nav_status INTEGER,
    rate_of_turn INTEGER,
    position_accuracy INTEGER,
    ship_name TEXT,
    timestamp TEXT NOT NULL,
    received_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient latest position and track queries
CREATE INDEX IF NOT EXISTS idx_positions_mmsi_timestamp
ON positions(mmsi, timestamp DESC);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_positions_timestamp
ON positions(timestamp DESC);
"""


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to database and initialize schema."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrent performance
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")

        # Create schema
        await self.db.executescript(SCHEMA)
        await self.db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.close()

    async def insert_position(self, data: dict) -> None:
        """Insert a position record."""
        await self.db.execute(
            """
            INSERT INTO positions (
                mmsi, lat, lon, speed, course, heading,
                nav_status, rate_of_turn, position_accuracy,
                ship_name, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("mmsi"),
                data.get("lat"),
                data.get("lon"),
                data.get("speed"),
                data.get("course"),
                data.get("heading"),
                data.get("nav_status"),
                data.get("rate_of_turn"),
                data.get("position_accuracy"),
                data.get("ship_name"),
                data.get("timestamp"),
            ),
        )

    async def upsert_vessel(self, data: dict) -> None:
        """Insert or update vessel metadata."""
        await self.db.execute(
            """
            INSERT INTO vessels (
                mmsi, imo, call_sign, name, ship_type,
                dimension_a, dimension_b, dimension_c, dimension_d,
                destination, eta, draught, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(mmsi) DO UPDATE SET
                imo = COALESCE(excluded.imo, vessels.imo),
                call_sign = COALESCE(excluded.call_sign, vessels.call_sign),
                name = COALESCE(excluded.name, vessels.name),
                ship_type = COALESCE(excluded.ship_type, vessels.ship_type),
                dimension_a = COALESCE(excluded.dimension_a, vessels.dimension_a),
                dimension_b = COALESCE(excluded.dimension_b, vessels.dimension_b),
                dimension_c = COALESCE(excluded.dimension_c, vessels.dimension_c),
                dimension_d = COALESCE(excluded.dimension_d, vessels.dimension_d),
                destination = COALESCE(excluded.destination, vessels.destination),
                eta = COALESCE(excluded.eta, vessels.eta),
                draught = COALESCE(excluded.draught, vessels.draught),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                data.get("mmsi"),
                data.get("imo"),
                data.get("call_sign"),
                data.get("name"),
                data.get("ship_type"),
                data.get("dimension_a"),
                data.get("dimension_b"),
                data.get("dimension_c"),
                data.get("dimension_d"),
                data.get("destination"),
                data.get("eta"),
                data.get("draught"),
            ),
        )

    async def commit(self) -> None:
        """Commit pending changes."""
        await self.db.commit()

    async def get_latest_positions(self) -> list[dict]:
        """Get latest position for each vessel."""
        cursor = await self.db.execute(
            """
            SELECT p.*, v.imo, v.call_sign, v.ship_type, v.destination,
                   v.dimension_a, v.dimension_b, v.dimension_c, v.dimension_d,
                   v.draught
            FROM positions p
            INNER JOIN (
                SELECT mmsi, MAX(timestamp) as max_ts
                FROM positions
                GROUP BY mmsi
            ) latest ON p.mmsi = latest.mmsi AND p.timestamp = latest.max_ts
            LEFT JOIN vessels v ON p.mmsi = v.mmsi
            ORDER BY p.timestamp DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_vessel(self, mmsi: str) -> dict | None:
        """Get vessel with latest position."""
        cursor = await self.db.execute(
            """
            SELECT p.*, v.imo, v.call_sign, v.ship_type, v.destination,
                   v.dimension_a, v.dimension_b, v.dimension_c, v.dimension_d,
                   v.draught, v.eta
            FROM positions p
            LEFT JOIN vessels v ON p.mmsi = v.mmsi
            WHERE p.mmsi = ?
            ORDER BY p.timestamp DESC
            LIMIT 1
            """,
            (mmsi,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_vessel_track(
        self, mmsi: str, since: timedelta | None = None, limit: int = 1000
    ) -> list[dict]:
        """Get position history for a vessel."""
        if since:
            since_time = (datetime.utcnow() - since).isoformat()
            cursor = await self.db.execute(
                """
                SELECT lat, lon, speed, course, heading, nav_status, timestamp
                FROM positions
                WHERE mmsi = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (mmsi, since_time, limit),
            )
        else:
            cursor = await self.db.execute(
                """
                SELECT lat, lon, speed, course, heading, nav_status, timestamp
                FROM positions
                WHERE mmsi = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (mmsi, limit),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_vessel_count(self) -> int:
        """Get count of unique vessels."""
        cursor = await self.db.execute(
            "SELECT COUNT(DISTINCT mmsi) FROM positions"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_position_count(self) -> int:
        """Get total position count."""
        cursor = await self.db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        return row[0] if row else 0


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

        for connection in disconnected:
            await self.disconnect(connection)

    async def client_count(self) -> int:
        """Get number of connected clients."""
        async with self.lock:
            return len(self.active_connections)


class ShipsAPIService:
    """Ships API service with NATS integration and SQLite storage."""

    def __init__(self):
        self.nc: nats.NATS | None = None
        self.js: nats.js.JetStreamContext | None = None
        self.db = Database(DB_PATH)
        self.ws_manager = WebSocketManager()
        self.running = False
        self.ready = False
        self.replay_task: asyncio.Task | None = None
        self.messages_received = 0
        self.replay_complete = False
        self.replay_count = 0
        self._pending_commits = 0
        self._commit_interval = 100  # Commit every N inserts

    async def connect_nats(self) -> None:
        """Connect to NATS."""
        logger.info(f"Connecting to NATS at {NATS_URL}")
        self.nc = await nats.connect(NATS_URL)
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS")

    async def replay_stream(self) -> None:
        """Replay the ais stream to build database (runs in background)."""
        logger.info("Starting AIS stream replay...")

        try:
            consumer_config = ConsumerConfig(
                deliver_policy=DeliverPolicy.ALL,
                ack_wait=30,
            )

            # Replay position messages
            psub = await self.js.pull_subscribe(
                "ais.>",  # Both position and static
                durable=None,
                config=consumer_config,
            )

            while self.running:
                try:
                    msgs = await psub.fetch(batch=100, timeout=2)
                    if not msgs:
                        break

                    for msg in msgs:
                        await self._process_message(msg.subject, msg.data, broadcast=False)
                        await msg.ack()
                        self.replay_count += 1
                        self._pending_commits += 1

                        # Batch commits for performance
                        if self._pending_commits >= self._commit_interval:
                            await self.db.commit()
                            self._pending_commits = 0

                    if self.replay_count % 1000 == 0:
                        logger.info(f"Replay progress: {self.replay_count} messages")

                except asyncio.TimeoutError:
                    break
                except Exception as e:
                    logger.warning(f"Error during replay: {e}")
                    break

            # Final commit
            if self._pending_commits > 0:
                await self.db.commit()
                self._pending_commits = 0

            await psub.unsubscribe()
            vessel_count = await self.db.get_vessel_count()
            position_count = await self.db.get_position_count()
            logger.info(
                f"Replay complete. {position_count} positions for {vessel_count} vessels"
            )
            self.replay_complete = True

        except Exception as e:
            logger.error(f"Failed to replay stream: {e}")
            self.replay_complete = True

    async def subscribe_live(self) -> None:
        """Subscribe to live vessel updates."""
        logger.info("Subscribing to live AIS updates...")

        try:
            consumer_config = ConsumerConfig(
                deliver_policy=DeliverPolicy.NEW,
                ack_wait=30,
            )

            psub = await self.js.pull_subscribe(
                "ais.>",
                durable=None,
                config=consumer_config,
            )

            logger.info("Subscribed to live updates")

            while self.running:
                try:
                    msgs = await psub.fetch(batch=10, timeout=1)
                    for msg in msgs:
                        await self._process_message(msg.subject, msg.data)
                        await msg.ack()
                        self.messages_received += 1

                    # Commit after each batch of live messages
                    if msgs:
                        await self.db.commit()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error receiving message: {e}")
                    break

        except Exception as e:
            logger.error(f"Failed to subscribe to live updates: {e}")

    async def _process_message(
        self, subject: str, data: bytes, broadcast: bool = True
    ) -> None:
        """Process a NATS message."""
        try:
            payload = json.loads(data)
            mmsi = payload.get("mmsi")
            if not mmsi:
                return

            if subject.startswith("ais.position."):
                await self.db.insert_position(payload)
                if broadcast and self.replay_complete:
                    await self.ws_manager.broadcast(payload)

            elif subject.startswith("ais.static."):
                await self.db.upsert_vessel(payload)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse message: {e}")

    async def start(self) -> None:
        """Start the Ships API service."""
        self.running = True

        # Initialize database
        await self.db.connect()

        # Connect to NATS
        await self.connect_nats()

        # Start replay in background
        self.replay_task = asyncio.create_task(self._replay_and_subscribe())

        logger.info("Ships API service started (replay running in background)")

    async def _replay_and_subscribe(self) -> None:
        """Replay stream then start live subscription."""
        await self.replay_stream()
        self.ready = True
        logger.info("Service ready - replay complete")
        await self.subscribe_live()

    async def stop(self) -> None:
        """Stop the Ships API service."""
        logger.info("Stopping Ships API service...")
        self.running = False
        self.ready = False

        if self.replay_task:
            self.replay_task.cancel()
            try:
                await self.replay_task
            except asyncio.CancelledError:
                pass

        if self.nc:
            await self.nc.close()
            logger.info("NATS connection closed")

        await self.db.close()
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
    description="Real-time vessel tracking API with historical data",
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
    vessel_count = await service.db.get_vessel_count()
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
    vessel_count = await service.db.get_vessel_count()
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
    vessels = await service.db.get_latest_positions()
    return {
        "count": len(vessels),
        "vessels": vessels,
    }


@app.get("/api/vessels/{mmsi}")
async def get_vessel(mmsi: str):
    """Get single vessel by MMSI with latest position."""
    vessel = await service.db.get_vessel(mmsi)
    if vessel is None:
        return {"error": "Vessel not found"}, 404
    return vessel


@app.get("/api/vessels/{mmsi}/track")
async def get_vessel_track(
    mmsi: str,
    since: str | None = Query(None, description="Duration like '1h', '30m', '2d'"),
    limit: int = Query(1000, ge=1, le=10000),
):
    """Get position history for a vessel to plot route."""
    # Parse duration
    duration = None
    if since:
        try:
            if since.endswith("h"):
                duration = timedelta(hours=int(since[:-1]))
            elif since.endswith("m"):
                duration = timedelta(minutes=int(since[:-1]))
            elif since.endswith("d"):
                duration = timedelta(days=int(since[:-1]))
        except ValueError:
            pass

    track = await service.db.get_vessel_track(mmsi, since=duration, limit=limit)
    return {
        "mmsi": mmsi,
        "count": len(track),
        "track": track,
    }


@app.get("/api/stats")
async def get_stats():
    """Get service statistics."""
    vessel_count = await service.db.get_vessel_count()
    position_count = await service.db.get_position_count()
    client_count = await service.ws_manager.client_count()
    return {
        "vessel_count": vessel_count,
        "position_count": position_count,
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
        vessels = await service.db.get_latest_positions()
        await websocket.send_json(
            {
                "type": "snapshot",
                "vessels": vessels,
            }
        )

        # Keep connection alive, updates are pushed via broadcast
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    finally:
        await service.ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
