"""
Ships API Service

Serves AIS vessel data via REST API and WebSocket.
- Replays NATS JetStream on startup to build SQLite database
- Subscribes to live updates and broadcasts to WebSocket clients
- Stores full vessel metadata and position history (7-day retention)
- Deduplicates positions for stationary vessels

Performance optimizations:
- In-memory position cache for fast deduplication (no DB reads per message)
- Batch message acknowledgments to reduce NATS round-trips
- Batch DB writes with executemany for high throughput
"""

import asyncio
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
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

# Catchup threshold - consider "caught up" when pending is below this
# With ~200 msg/min arrival rate, 10k pending = ~50 min of data, acceptable lag
CATCHUP_PENDING_THRESHOLD = int(os.getenv("CATCHUP_PENDING_THRESHOLD", "10000"))

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

-- Indexes are created separately after catchup completes for faster bulk inserts
"""

# Only indexes actually needed by queries:
# - (mmsi, timestamp) for track queries: WHERE mmsi=? ORDER BY timestamp ASC
# - (timestamp) for cleanup: DELETE WHERE timestamp < ?
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_positions_mmsi_timestamp ON positions(mmsi, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp)",
]


@dataclass
class CachedPosition:
    """In-memory cache entry for latest vessel position."""

    lat: float
    lon: float
    speed: float | None
    timestamp: str
    first_seen_at_location: str | None


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
    """Async SQLite database wrapper with in-memory position cache."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None
        self._read_db: aiosqlite.Connection | None = None
        # In-memory cache for deduplication - avoids DB reads per message
        self._position_cache: dict[str, CachedPosition] = {}
        # Cached position count to avoid full table scans
        self._position_count: int = 0

    async def connect(self) -> None:
        """Connect to database and initialize schema."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

        # Aggressive SQLite tuning for high-throughput ingestion
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute(
            "PRAGMA synchronous=OFF"
        )  # Skip fsync (WAL provides crash safety)
        await self.db.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
        await self.db.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
        await self.db.execute("PRAGMA cache_size=-512000")  # 512MB cache
        await self.db.execute(
            "PRAGMA wal_autocheckpoint=1000"
        )  # Smaller checkpoints, less blocking
        await self.db.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks

        # Create schema and indexes
        await self.db.executescript(SCHEMA)
        for idx_sql in INDEXES:
            await self.db.execute(idx_sql)
        await self.db.commit()

        # Separate read-only connection so API reads don't block writes
        self._read_db = await aiosqlite.connect(
            f"file:{self.db_path}?mode=ro", uri=True
        )
        self._read_db.row_factory = aiosqlite.Row
        await self._read_db.execute("PRAGMA mmap_size=268435456")
        await self._read_db.execute("PRAGMA cache_size=-512000")

        logger.info(f"Database initialized at {self.db_path}")

        # Load existing positions into memory cache
        await self._load_position_cache()
        # Initialize position count from DB
        cursor = await self._read_db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        self._position_count = row[0] if row else 0

    async def _load_position_cache(self) -> None:
        """Load latest positions from DB into memory cache."""
        cursor = await self.db.execute(
            "SELECT mmsi, lat, lon, speed, timestamp, first_seen_at_location "
            "FROM latest_positions"
        )
        rows = await cursor.fetchall()
        for row in rows:
            self._position_cache[row["mmsi"]] = CachedPosition(
                lat=row["lat"],
                lon=row["lon"],
                speed=row["speed"],
                timestamp=row["timestamp"],
                first_seen_at_location=row["first_seen_at_location"],
            )
        logger.info(f"Loaded {len(self._position_cache)} positions into memory cache")

    async def close(self) -> None:
        """Close database connections."""
        if self._read_db:
            await self._read_db.close()
        if self.db:
            await self.db.close()

    async def drop_indexes(self) -> None:
        """Drop indexes for faster bulk inserts during catchup."""
        logger.info("Dropping indexes for bulk insert performance...")
        # Drop any existing indexes on positions table
        await self.db.execute("DROP INDEX IF EXISTS idx_positions_mmsi_timestamp")
        await self.db.execute("DROP INDEX IF EXISTS idx_positions_timestamp")
        # Also drop legacy indexes that may exist from old schema
        await self.db.execute("DROP INDEX IF EXISTS idx_positions_mmsi_timestamp_asc")
        await self.db.execute("DROP INDEX IF EXISTS idx_positions_received_at")
        await self.db.commit()
        logger.info("Indexes dropped")

    async def create_indexes(self) -> None:
        """Create indexes after catchup for query performance."""
        logger.info("Creating indexes for query performance...")
        for idx_sql in INDEXES:
            await self.db.execute(idx_sql)
        await self.db.commit()
        logger.info("Indexes created")

    def get_cached_position(self, mmsi: str) -> CachedPosition | None:
        """Get cached latest position for deduplication (no DB access)."""
        return self._position_cache.get(mmsi)

    def should_insert_position(self, data: dict) -> tuple[bool, str | None]:
        """Check if position should be inserted (deduplication logic).

        Returns (should_insert, first_seen_at_location).
        Uses in-memory cache - no DB access.
        """
        mmsi = data.get("mmsi")
        if not mmsi:
            return False, None

        lat = data.get("lat", 0)
        lon = data.get("lon", 0)
        timestamp = data.get("timestamp", "")

        last = self._position_cache.get(mmsi)
        if not last:
            return True, timestamp  # First position for this vessel

        # Always insert if speed is above threshold (vessel is moving)
        speed = data.get("speed") or 0
        if speed > DEDUP_SPEED_THRESHOLD:
            # Check if moved significantly to reset first_seen
            distance = haversine_distance(last.lat, last.lon, lat, lon)
            first_seen = (
                last.first_seen_at_location
                if distance <= MOORED_RADIUS_METERS
                else timestamp
            )
            return True, first_seen

        # Calculate distance from last position
        distance = haversine_distance(last.lat, last.lon, lat, lon)

        # Insert if moved more than threshold
        if distance > DEDUP_DISTANCE_METERS:
            first_seen = (
                last.first_seen_at_location
                if distance <= MOORED_RADIUS_METERS
                else timestamp
            )
            return True, first_seen

        # Check time since last update
        try:
            last_ts = datetime.fromisoformat(last.timestamp.replace("Z", "+00:00"))
            new_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_diff = (new_ts - last_ts).total_seconds()

            # Insert if enough time has passed (even for stationary vessels)
            if time_diff > DEDUP_TIME_THRESHOLD:
                # Still in same area, keep original first_seen
                return True, last.first_seen_at_location or timestamp
        except (ValueError, TypeError):
            return True, timestamp  # Insert if timestamp parsing fails

        return False, None

    def update_cache(self, mmsi: str, data: dict, first_seen: str | None) -> None:
        """Update the in-memory position cache."""
        self._position_cache[mmsi] = CachedPosition(
            lat=data.get("lat", 0),
            lon=data.get("lon", 0),
            speed=data.get("speed"),
            timestamp=data.get("timestamp", ""),
            first_seen_at_location=first_seen,
        )

    async def insert_positions_batch(
        self, positions: list[tuple[dict, str | None]]
    ) -> int:
        """Batch insert positions. Returns count inserted.

        Args:
            positions: List of (data_dict, first_seen_at_location) tuples
        """
        if not positions:
            return 0

        # Prepare batch data for positions table
        position_rows = []
        latest_rows = []

        for data, first_seen in positions:
            mmsi = data.get("mmsi")
            lat = data.get("lat")
            lon = data.get("lon")
            timestamp = data.get("timestamp")

            position_rows.append(
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
                )
            )

            latest_rows.append(
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
                )
            )

            # Update in-memory cache
            self.update_cache(mmsi, data, first_seen)

        # Batch insert into positions table
        await self.db.executemany(
            """
            INSERT INTO positions (
                mmsi, lat, lon, speed, course, heading,
                nav_status, rate_of_turn, position_accuracy,
                ship_name, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            position_rows,
        )

        # Batch upsert into latest_positions table
        await self.db.executemany(
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
            latest_rows,
        )

        self._position_count += len(positions)
        return len(positions)

    async def upsert_vessels_batch(self, vessels: list[dict]) -> None:
        """Batch insert or update vessel metadata."""
        if not vessels:
            return

        rows = [
            (
                v.get("mmsi"),
                v.get("imo"),
                v.get("call_sign"),
                v.get("name"),
                v.get("ship_type"),
                v.get("dimension_a"),
                v.get("dimension_b"),
                v.get("dimension_c"),
                v.get("dimension_d"),
                v.get("destination"),
                v.get("eta"),
                v.get("draught"),
            )
            for v in vessels
        ]

        await self.db.executemany(
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
            rows,
        )

    async def commit(self) -> None:
        """Commit pending changes."""
        await self.db.commit()

    async def cleanup_old_positions(self) -> int:
        """Delete positions older than retention period in batches.

        Deletes in batches of 10k rows to avoid long DB locks that could
        cause liveness probe timeouts and pod restarts.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=POSITION_RETENTION_DAYS)
        ).isoformat()
        total_deleted = 0
        batch_size = 10000

        while True:
            # Delete in small batches to avoid long locks
            cursor = await self.db.execute(
                "DELETE FROM positions WHERE rowid IN "
                "(SELECT rowid FROM positions WHERE timestamp < ? LIMIT ?)",
                (cutoff, batch_size),
            )
            deleted = cursor.rowcount
            await self.db.commit()
            total_deleted += deleted

            if deleted < batch_size:
                break

            # Yield to allow other operations (health checks, message processing)
            await asyncio.sleep(0.1)

        if total_deleted > 0:
            self._position_count = max(0, self._position_count - total_deleted)
            logger.info(
                f"Cleaned up {total_deleted} positions older than "
                f"{POSITION_RETENTION_DAYS} days"
            )

        return total_deleted

    async def get_latest_positions(self) -> list[dict]:
        """Get latest position for each vessel using cache table."""
        cursor = await self._read_db.execute(
            """
            SELECT lp.*, v.imo, v.call_sign, v.ship_type, v.destination,
                   v.dimension_a, v.dimension_b, v.dimension_c, v.dimension_d,
                   v.draught, v.eta
            FROM latest_positions lp
            LEFT JOIN vessels v ON lp.mmsi = v.mmsi
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_vessel(self, mmsi: str) -> dict | None:
        """Get vessel with latest position and analytics."""
        cursor = await self._read_db.execute(
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
            cursor = await self._read_db.execute(
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
            cursor = await self._read_db.execute(
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

    def get_vessel_count(self) -> int:
        """Get count of unique vessels from in-memory cache."""
        return len(self._position_cache)

    def get_position_count(self) -> int:
        """Get total position count from cached counter."""
        return self._position_count

    def get_cache_size(self) -> int:
        """Get current size of in-memory position cache."""
        return len(self._position_cache)


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
    """Ships API service with NATS integration and SQLite storage.

    Performance optimizations:
    - In-memory position cache for O(1) deduplication lookups
    - Batch message acknowledgments (ack after processing batch, not per message)
    - Batch DB writes with executemany
    """

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

        Performance: Processes messages in batches with batch acks.
        """
        logger.info("Subscribing to AIS stream with durable consumer...")

        try:
            # Durable consumer - NATS tracks position across restarts
            # max_ack_pending allows larger batches without NATS throttling
            consumer_config = ConsumerConfig(
                durable_name="ships-api",
                deliver_policy=DeliverPolicy.ALL,
                ack_wait=120,  # Longer ack wait for batch processing
                max_ack_pending=10000,  # Allow 10k unacked msgs (default 1000 throttles us)
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
                    # Large batches during catchup (not serving reads yet)
                    # Smaller batches when live to reduce DB lock duration
                    batch_size = 10000 if not self.replay_complete else 100
                    timeout = 5 if not self.replay_complete else 1

                    msgs = await psub.fetch(batch=batch_size, timeout=timeout)

                    # Process batch and collect DB operations
                    positions_to_insert: list[tuple[dict, str | None]] = []
                    vessels_to_upsert: list[dict] = []
                    positions_for_broadcast: list[dict] = []

                    for i, msg in enumerate(msgs):
                        result = self._process_message_sync(msg.subject, msg.data)
                        if result:
                            msg_type, data, first_seen = result
                            if msg_type == "position":
                                positions_to_insert.append((data, first_seen))
                                if self.replay_complete:
                                    positions_for_broadcast.append(data)
                            elif msg_type == "vessel":
                                vessels_to_upsert.append(data)
                            elif msg_type == "deduplicated":
                                self.messages_deduplicated += 1

                        self.messages_received += 1

                        # Yield to event loop periodically to allow health checks
                        if i % 500 == 0:
                            await asyncio.sleep(0)

                    # Batch DB writes
                    if positions_to_insert:
                        await self.db.insert_positions_batch(positions_to_insert)
                    if vessels_to_upsert:
                        await self.db.upsert_vessels_batch(vessels_to_upsert)

                    # Commit after batch
                    await self.db.commit()

                    # Batch ack all messages in parallel (after successful DB commit)
                    await asyncio.gather(*[msg.ack() for msg in msgs])

                    # Broadcast to WebSocket clients (after catchup)
                    # Send as batch with only latest position per vessel
                    if self.replay_complete and positions_for_broadcast:
                        # Dedupe: keep only latest position per MMSI
                        latest_by_mmsi: dict[str, dict] = {}
                        for pos in positions_for_broadcast:
                            latest_by_mmsi[pos["mmsi"]] = pos
                        # Send as single batched message
                        await self.ws_manager.broadcast(
                            {
                                "type": "positions",
                                "positions": list(latest_by_mmsi.values()),
                            }
                        )

                    # Log progress every 10k messages
                    if not self.replay_complete and self.messages_received % 10000 == 0:
                        info = await psub.consumer_info()
                        logger.info(
                            f"Catchup progress: {self.messages_received} processed, "
                            f"{info.num_pending} pending"
                        )

                    # Check catchup after each batch (especially important for small backlogs)
                    if not self.replay_complete:
                        info = await psub.consumer_info()
                        if info.num_pending <= CATCHUP_PENDING_THRESHOLD:
                            vessel_count = self.db.get_vessel_count()
                            position_count = self.db.get_position_count()
                            logger.info(
                                f"Catchup complete. {position_count} positions "
                                f"for {vessel_count} vessels"
                            )
                            self.replay_complete = True
                            self.ready = True

                except asyncio.TimeoutError:
                    # Timeout means no messages - check if we've caught up
                    if not self.replay_complete:
                        info = await psub.consumer_info()
                        if info.num_pending <= CATCHUP_PENDING_THRESHOLD:
                            vessel_count = self.db.get_vessel_count()
                            position_count = self.db.get_position_count()
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

    def _process_message_sync(
        self, subject: str, data: bytes
    ) -> tuple[str, dict, str | None] | None:
        """Process a NATS message synchronously (no async DB calls).

        Returns:
            None if message should be skipped
            ("position", data, first_seen) for position messages to insert
            ("vessel", data, None) for vessel messages
            ("deduplicated", {}, None) for deduplicated positions
        """
        try:
            payload = json.loads(data)
            mmsi = payload.get("mmsi")
            if not mmsi:
                return None

            if subject.startswith("ais.position."):
                should_insert, first_seen = self.db.should_insert_position(payload)
                if should_insert:
                    return ("position", payload, first_seen)
                return ("deduplicated", {}, None)

            elif subject.startswith("ais.static."):
                return ("vessel", payload, None)

            return None

        except json.JSONDecodeError:
            return None

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
    version="2.1.0",
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
    vessel_count = service.db.get_vessel_count()
    return {
        "status": "alive",
        "nats_connected": service.nc is not None and service.nc.is_connected,
        "vessel_count": vessel_count,
        "cache_size": service.db.get_cache_size(),
        "caught_up": service.replay_complete,
        "messages_processed": service.messages_received,
    }


@app.get("/ready")
async def ready(response: Response):
    """Readiness probe - returns 200 only when ready to serve traffic."""
    vessel_count = service.db.get_vessel_count()
    if not service.ready:
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": "catching_up" if not service.replay_complete else "starting",
            "vessel_count": vessel_count,
            "cache_size": service.db.get_cache_size(),
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
    vessel_count = service.db.get_vessel_count()
    position_count = service.db.get_position_count()
    client_count = await service.ws_manager.client_count()
    return {
        "vessel_count": vessel_count,
        "position_count": position_count,
        "cache_size": service.db.get_cache_size(),
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
