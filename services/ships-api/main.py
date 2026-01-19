"""
Ships API Service

Serves AIS vessel data via REST API and WebSocket.
- Replays NATS JetStream on startup to build SQLite database
- Subscribes to live updates and broadcasts to WebSocket clients
- Stores full vessel metadata and position history (7-day retention)
- Deduplicates positions for stationary vessels
"""

import asyncio
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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

# Position retention (days)
POSITION_RETENTION_DAYS = int(os.getenv("POSITION_RETENTION_DAYS", "7"))

# Deduplication settings
# Skip position if within this distance (meters) and speed below threshold
DEDUP_DISTANCE_METERS = float(os.getenv("DEDUP_DISTANCE_METERS", "100"))
DEDUP_SPEED_THRESHOLD = float(os.getenv("DEDUP_SPEED_THRESHOLD", "0.5"))  # knots
DEDUP_TIME_THRESHOLD = int(os.getenv("DEDUP_TIME_THRESHOLD", "300"))  # seconds

# Moored detection settings
MOORED_RADIUS_METERS = float(os.getenv("MOORED_RADIUS_METERS", "500"))
MOORED_MIN_DURATION_HOURS = float(os.getenv("MOORED_MIN_DURATION_HOURS", "1"))

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

-- Position history (append-only, 7-day retention)
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

-- Latest position cache for fast lookups and deduplication
CREATE TABLE IF NOT EXISTS latest_positions (
    mmsi TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    speed REAL,
    course REAL,
    heading INTEGER,
    nav_status INTEGER,
    ship_name TEXT,
    timestamp TEXT NOT NULL,
    first_seen_at_location TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient latest position and track queries
CREATE INDEX IF NOT EXISTS idx_positions_mmsi_timestamp
ON positions(mmsi, timestamp DESC);

-- Index for time-based queries and cleanup
CREATE INDEX IF NOT EXISTS idx_positions_timestamp
ON positions(timestamp DESC);

-- Index for track queries (ASC order matches query pattern)
CREATE INDEX IF NOT EXISTS idx_positions_mmsi_timestamp_asc
ON positions(mmsi, timestamp ASC);

-- Index for retention cleanup
CREATE INDEX IF NOT EXISTS idx_positions_received_at
ON positions(received_at);
"""


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula."""
    R = 6371000  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


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
        # Increase cache for better performance with large datasets
        await self.db.execute("PRAGMA cache_size=-64000")  # 64MB cache

        # Create schema
        await self.db.executescript(SCHEMA)
        await self.db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.close()

    async def get_latest_position(self, mmsi: str) -> dict | None:
        """Get cached latest position for deduplication."""
        cursor = await self.db.execute(
            "SELECT * FROM latest_positions WHERE mmsi = ?",
            (mmsi,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def should_insert_position(self, data: dict) -> bool:
        """Check if position should be inserted (deduplication logic)."""
        mmsi = data.get("mmsi")
        if not mmsi:
            return False

        last = await self.get_latest_position(mmsi)
        if not last:
            return True  # First position for this vessel

        # Always insert if speed is above threshold (vessel is moving)
        speed = data.get("speed") or 0
        if speed > DEDUP_SPEED_THRESHOLD:
            return True

        # Calculate distance from last position
        distance = haversine_distance(
            last["lat"], last["lon"], data.get("lat", 0), data.get("lon", 0)
        )

        # Insert if moved more than threshold
        if distance > DEDUP_DISTANCE_METERS:
            return True

        # Check time since last update
        try:
            last_ts = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00"))
            new_ts = datetime.fromisoformat(
                data.get("timestamp", "").replace("Z", "+00:00")
            )
            time_diff = (new_ts - last_ts).total_seconds()

            # Insert if enough time has passed (even for stationary vessels)
            if time_diff > DEDUP_TIME_THRESHOLD:
                return True
        except (ValueError, TypeError):
            return True  # Insert if timestamp parsing fails

        return False

    async def insert_position(self, data: dict) -> bool:
        """Insert a position record if not duplicate. Returns True if inserted."""
        if not await self.should_insert_position(data):
            return False

        mmsi = data.get("mmsi")
        lat = data.get("lat")
        lon = data.get("lon")
        timestamp = data.get("timestamp")

        # Insert into positions history
        await self.db.execute(
            """
            INSERT INTO positions (
                mmsi, lat, lon, speed, course, heading,
                nav_status, rate_of_turn, position_accuracy,
                ship_name, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mmsi,
                lat,
                lon,
                data.get("speed"),
                data.get("course"),
                data.get("heading"),
                data.get("nav_status"),
                data.get("rate_of_turn"),
                data.get("position_accuracy"),
                data.get("ship_name"),
                timestamp,
            ),
        )

        # Update latest position cache
        # Check if vessel has moved significantly to reset first_seen_at_location
        last = await self.get_latest_position(mmsi)
        first_seen = timestamp

        if last:
            distance = haversine_distance(last["lat"], last["lon"], lat, lon)
            if distance <= MOORED_RADIUS_METERS:
                # Still in same area, keep original first_seen time
                first_seen = last.get("first_seen_at_location") or timestamp

        await self.db.execute(
            """
            INSERT INTO latest_positions (
                mmsi, lat, lon, speed, course, heading, nav_status,
                ship_name, timestamp, first_seen_at_location, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(mmsi) DO UPDATE SET
                lat = excluded.lat,
                lon = excluded.lon,
                speed = excluded.speed,
                course = excluded.course,
                heading = excluded.heading,
                nav_status = excluded.nav_status,
                ship_name = COALESCE(excluded.ship_name, latest_positions.ship_name),
                timestamp = excluded.timestamp,
                first_seen_at_location = excluded.first_seen_at_location,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                mmsi,
                lat,
                lon,
                data.get("speed"),
                data.get("course"),
                data.get("heading"),
                data.get("nav_status"),
                data.get("ship_name"),
                timestamp,
                first_seen,
            ),
        )

        return True

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

    async def cleanup_old_positions(self) -> int:
        """Delete positions older than retention period. Returns count deleted."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=POSITION_RETENTION_DAYS)
        ).isoformat()

        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM positions WHERE timestamp < ?", (cutoff,)
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0

        if count > 0:
            await self.db.execute(
                "DELETE FROM positions WHERE timestamp < ?", (cutoff,)
            )
            await self.db.commit()
            logger.info(
                f"Cleaned up {count} positions older than {POSITION_RETENTION_DAYS} days"
            )

        return count

    async def get_latest_positions(self) -> list[dict]:
        """Get latest position for each vessel using cache table."""
        cursor = await self.db.execute(
            """
            SELECT lp.*, v.imo, v.call_sign, v.ship_type, v.destination,
                   v.dimension_a, v.dimension_b, v.dimension_c, v.dimension_d,
                   v.draught, v.eta
            FROM latest_positions lp
            LEFT JOIN vessels v ON lp.mmsi = v.mmsi
            ORDER BY lp.timestamp DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_vessel(self, mmsi: str) -> dict | None:
        """Get vessel with latest position and analytics."""
        cursor = await self.db.execute(
            """
            SELECT lp.*, v.imo, v.call_sign, v.ship_type, v.destination,
                   v.dimension_a, v.dimension_b, v.dimension_c, v.dimension_d,
                   v.draught, v.eta
            FROM latest_positions lp
            LEFT JOIN vessels v ON lp.mmsi = v.mmsi
            WHERE lp.mmsi = ?
            """,
            (mmsi,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        result = dict(row)

        # Calculate time at current location
        first_seen = result.get("first_seen_at_location")
        if first_seen:
            try:
                first_dt = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                duration = now - first_dt
                result["time_at_location_seconds"] = int(duration.total_seconds())
                result["time_at_location_hours"] = round(
                    duration.total_seconds() / 3600, 1
                )

                # Determine if moored (at location for > threshold)
                result["is_moored"] = (
                    duration.total_seconds() >= MOORED_MIN_DURATION_HOURS * 3600
                )
            except (ValueError, TypeError):
                result["time_at_location_seconds"] = None
                result["time_at_location_hours"] = None
                result["is_moored"] = None

        return result

    async def get_vessel_track(
        self, mmsi: str, since: timedelta | None = None, limit: int = 1000
    ) -> list[dict]:
        """Get position history for a vessel."""
        if since:
            since_time = (datetime.now(timezone.utc) - since).isoformat()
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
        cursor = await self.db.execute("SELECT COUNT(*) FROM latest_positions")
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
        self.subscription_task: asyncio.Task | None = None
        self.cleanup_task: asyncio.Task | None = None
        self.messages_received = 0
        self.messages_deduplicated = 0
        self.replay_complete = False
        self._pending_commits = 0
        self._commit_interval = (
            500  # Commit every N inserts (increased for global volume)
        )

    async def connect_nats(self) -> None:
        """Connect to NATS."""
        logger.info(f"Connecting to NATS at {NATS_URL}")
        self.nc = await nats.connect(NATS_URL)
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS")

    async def subscribe_ais_stream(self) -> None:
        """Subscribe to AIS stream using durable consumer.

        Uses a durable consumer so NATS tracks our position. On restart:
        - First run: processes all messages from the beginning
        - Subsequent runs: resumes from last acknowledged message

        This eliminates the need for separate replay/live phases.
        """
        logger.info("Subscribing to AIS stream with durable consumer...")

        try:
            # Durable consumer - NATS tracks position across restarts
            # deliver_policy=ALL only applies on first creation; after that
            # NATS resumes from last ack'd position
            consumer_config = ConsumerConfig(
                durable_name="ships-api",
                deliver_policy=DeliverPolicy.ALL,
                ack_wait=60,  # Longer ack wait for batch processing
            )

            psub = await self.js.pull_subscribe(
                "ais.>",
                durable="ships-api",
                config=consumer_config,
            )

            # Check if we're catching up or already live
            consumer_info = await psub.consumer_info()
            pending = consumer_info.num_pending
            if pending > 0:
                logger.info(f"Catching up on {pending} pending messages...")
            else:
                logger.info("Consumer is caught up, processing live messages")
                self.replay_complete = True
                self.ready = True

            while self.running:
                try:
                    # Use larger batches when catching up, smaller for live
                    batch_size = 500 if not self.replay_complete else 100
                    timeout = 2 if not self.replay_complete else 1

                    msgs = await psub.fetch(batch=batch_size, timeout=timeout)

                    for msg in msgs:
                        # Don't broadcast during catchup to avoid flooding clients
                        broadcast = self.replay_complete
                        await self._process_message(msg.subject, msg.data, broadcast)
                        await msg.ack()
                        self.messages_received += 1
                        self._pending_commits += 1

                        # Batch commits for performance
                        if self._pending_commits >= self._commit_interval:
                            await self.db.commit()
                            self._pending_commits = 0

                    # Commit remaining after each batch
                    if self._pending_commits > 0:
                        await self.db.commit()
                        self._pending_commits = 0

                    # Log progress during catchup
                    if not self.replay_complete and self.messages_received % 10000 == 0:
                        info = await psub.consumer_info()
                        logger.info(
                            f"Catchup progress: {self.messages_received} processed, "
                            f"{info.num_pending} pending"
                        )

                except asyncio.TimeoutError:
                    # Timeout means no messages - check if we've caught up
                    if not self.replay_complete:
                        info = await psub.consumer_info()
                        if info.num_pending == 0:
                            vessel_count = await self.db.get_vessel_count()
                            position_count = await self.db.get_position_count()
                            logger.info(
                                f"Catchup complete. {position_count} positions "
                                f"for {vessel_count} vessels"
                            )
                            self.replay_complete = True
                            self.ready = True
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error processing messages: {e}")
                    # Brief pause before retry
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Failed to subscribe to AIS stream: {e}")
            raise

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
                inserted = await self.db.insert_position(payload)
                if not inserted:
                    self.messages_deduplicated += 1
                elif broadcast and self.replay_complete:
                    await self.ws_manager.broadcast(payload)

            elif subject.startswith("ais.static."):
                await self.db.upsert_vessel(payload)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse message: {e}")

    async def cleanup_loop(self) -> None:
        """Periodic cleanup of old positions."""
        while self.running:
            try:
                await asyncio.sleep(3600)  # Run every hour
                if self.running:
                    await self.db.cleanup_old_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def start(self) -> None:
        """Start the Ships API service."""
        self.running = True

        # Initialize database
        await self.db.connect()

        # Connect to NATS
        await self.connect_nats()

        # Start AIS subscription (handles both catchup and live)
        self.subscription_task = asyncio.create_task(self._run_subscription())

        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self.cleanup_loop())

        logger.info("Ships API service started (durable subscription active)")

    async def _run_subscription(self) -> None:
        """Run the durable AIS stream subscription."""
        await self.subscribe_ais_stream()

    async def stop(self) -> None:
        """Stop the Ships API service."""
        logger.info("Stopping Ships API service...")
        self.running = False
        self.ready = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        if self.subscription_task:
            self.subscription_task.cancel()
            try:
                await self.subscription_task
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
    version="2.0.0",
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
        "caught_up": service.replay_complete,
        "messages_processed": service.messages_received,
    }


@app.get("/ready")
async def ready(response: Response):
    """Readiness probe - returns 200 only when ready to serve traffic."""
    vessel_count = await service.db.get_vessel_count()
    if not service.ready:
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": "catching_up" if not service.replay_complete else "starting",
            "vessel_count": vessel_count,
            "messages_processed": service.messages_received,
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
    """Get single vessel by MMSI with latest position and analytics."""
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
        "messages_deduplicated": service.messages_deduplicated,
        "connected_clients": client_count,
        "replay_complete": service.replay_complete,
        "retention_days": POSITION_RETENTION_DAYS,
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
