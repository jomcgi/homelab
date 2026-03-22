"""
AIS Data Ingestion Service

Subscribes to AISStream.io WebSocket API, filters position reports
within a bounding box (Pacific Northwest coast), and publishes them
to NATS JetStream with 24h retention.
"""

import asyncio
import json
import logging
import os
import signal
import ssl
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import certifi
import nats
from nats.js.api import DiscardPolicy, StorageType, StreamConfig
import websockets
from fastapi import FastAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration from environment
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
AISSTREAM_URL = os.getenv("AISSTREAM_URL", "wss://stream.aisstream.io/v0/stream")
BOUNDING_BOX = os.getenv(
    "BOUNDING_BOX", "[[[46.876152, -129.552155], [51.413769, -121.213531]]]"
)

# WebSocket reconnection settings
INITIAL_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 60.0
RECONNECT_BACKOFF_FACTOR = 2.0


def format_eta(eta: dict | None) -> str | None:
    """Convert AISStream ETA dict to ISO timestamp string.

    AIS ETA (per ITU-R M.1371-5) has no year, only Month, Day, Hour, Minute.
    Unavailable values: Month=0, Day=0, Hour=24, Minute=60.

    We infer the year: if the date is in the past, assume next year.
    Returns ISO format: "2026-01-18T12:00:00Z"
    """
    if not eta or not isinstance(eta, dict):
        return None

    month = eta.get("Month", 0)
    day = eta.get("Day", 0)
    hour = eta.get("Hour", 24)
    minute = eta.get("Minute", 60)

    # Month=0 or Day=0 means unavailable
    if month == 0 or day == 0:
        return None

    # Hour=24 or Minute=60 means unavailable, default to 00:00
    if hour == 24:
        hour = 0
    if minute == 60:
        minute = 0

    # Infer year: if date is in the past, use next year
    now = datetime.now(timezone.utc)
    year = now.year

    try:
        eta_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        if eta_dt < now:
            eta_dt = datetime(year + 1, month, day, hour, minute, tzinfo=timezone.utc)
        return eta_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        # Invalid date (e.g., Feb 30)
        return None


class AISIngestService:
    """AIS data ingestion service."""

    def __init__(self):
        self.nc: nats.NATS | None = None
        self.js: nats.js.JetStreamContext | None = None
        self.running = False
        self.ready = False
        self.ws_task: asyncio.Task | None = None
        self.messages_published = 0
        self.last_message_time: str | None = None

    async def connect_nats(self) -> None:
        """Connect to NATS and create the AIS stream if it doesn't exist."""
        logger.info(f"Connecting to NATS at {NATS_URL}")
        self.nc = await nats.connect(NATS_URL)
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS")

        # Create or update the AIS stream (add_stream is idempotent if config matches)
        # Storage limits: 10GB max, 24h retention, whichever is hit first
        # Note: Reduced from 40GB to fit NATS JetStream storage quota
        stream_config = StreamConfig(
            name="ais",
            subjects=["ais.>"],
            max_age=86400,  # 24h in seconds (nats-py converts to nanoseconds)
            max_bytes=10 * 1024 * 1024 * 1024,  # 10GB hard limit
            storage=StorageType.FILE,
            discard=DiscardPolicy.OLD,
            description="AIS position reports from AISStream.io (global coverage)",
        )

        try:
            await self.js.add_stream(stream_config)
            logger.info("Created 'ais' stream with 24h retention, 10GB max")
        except nats.js.errors.BadRequestError as e:
            if "already in use" in str(e):
                # Stream exists with different config, update it
                await self.js.update_stream(stream_config)
                logger.info("Updated 'ais' stream with 24h retention, 10GB max")
            else:
                raise

    async def publish_position(self, mmsi: str, data: dict) -> None:
        """Publish a position report to NATS."""
        subject = f"ais.position.{mmsi}"
        payload = json.dumps(data).encode()

        # Use MMSI + timestamp as message ID for deduplication
        msg_id = f"{mmsi}-{data.get('timestamp', '')}"

        await self.js.publish(
            subject,
            payload,
            headers={"Nats-Msg-Id": msg_id},
        )
        self.messages_published += 1
        self.last_message_time = data.get("timestamp")

    async def process_message(self, raw_message: str) -> None:
        """Process a single AIS message from the WebSocket."""
        try:
            message = json.loads(raw_message)
            msg_type = message.get("MessageType")
            metadata = message.get("MetaData", {})

            mmsi = str(metadata.get("MMSI", ""))
            if not mmsi:
                return

            if msg_type == "PositionReport":
                await self._process_position_report(message, mmsi, metadata)
            elif msg_type == "ShipStaticData":
                await self._process_static_data(message, mmsi, metadata)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def _process_position_report(
        self, message: dict, mmsi: str, metadata: dict
    ) -> None:
        """Process a PositionReport message."""
        position = message.get("Message", {}).get("PositionReport", {})
        if not position:
            return

        # Build the position data with all available fields
        data = {
            "mmsi": mmsi,
            "lat": position.get("Latitude"),
            "lon": position.get("Longitude"),
            "speed": position.get("Sog"),  # Speed over ground
            "course": position.get("Cog"),  # Course over ground
            "heading": position.get("TrueHeading"),
            "nav_status": position.get("NavigationalStatus"),
            "rate_of_turn": position.get("RateOfTurn"),
            "position_accuracy": position.get("PositionAccuracy"),
            "timestamp": metadata.get("time_utc"),
            "ship_name": metadata.get("ShipName", "").strip(),
        }

        # Skip if coordinates are invalid
        if data["lat"] is None or data["lon"] is None:
            return

        await self.publish_position(mmsi, data)
        logger.debug(f"Published position for MMSI {mmsi}")

    async def _process_static_data(
        self, message: dict, mmsi: str, metadata: dict
    ) -> None:
        """Process a ShipStaticData message."""
        static = message.get("Message", {}).get("ShipStaticData", {})
        if not static:
            return

        # Extract dimensions (A=bow, B=stern, C=port, D=starboard to ref point)
        dimension = static.get("Dimension", {})

        data = {
            "mmsi": mmsi,
            "imo": static.get("ImoNumber"),
            "call_sign": static.get("CallSign", "").strip(),
            "name": static.get("Name", "").strip()
            or metadata.get("ShipName", "").strip(),
            "ship_type": static.get("Type"),
            "dimension_a": dimension.get("A"),
            "dimension_b": dimension.get("B"),
            "dimension_c": dimension.get("C"),
            "dimension_d": dimension.get("D"),
            "destination": static.get("Destination", "").strip(),
            "eta": format_eta(static.get("Eta")),
            "draught": static.get("MaximumStaticDraught"),
            "timestamp": metadata.get("time_utc"),
        }

        await self.publish_static(mmsi, data)
        logger.debug(f"Published static data for MMSI {mmsi}")

    async def publish_static(self, mmsi: str, data: dict) -> None:
        """Publish static vessel data to NATS."""
        subject = f"ais.static.{mmsi}"
        payload = json.dumps(data).encode()

        # Use MMSI + timestamp as message ID for deduplication
        msg_id = f"static-{mmsi}-{data.get('timestamp', '')}"

        await self.js.publish(
            subject,
            payload,
            headers={"Nats-Msg-Id": msg_id},
        )

    async def subscribe_to_aisstream(self) -> None:
        """Connect to AISStream and process messages with reconnection logic."""
        reconnect_delay = INITIAL_RECONNECT_DELAY

        # Create SSL context with certifi CA bundle (needed for minimal container images)
        ssl_context = ssl.create_default_context(cafile=certifi.where())

        while self.running:
            try:
                logger.info(f"Connecting to AISStream at {AISSTREAM_URL}")
                async with websockets.connect(AISSTREAM_URL, ssl=ssl_context) as ws:
                    # Send subscription message within 3 seconds
                    subscription = {
                        "APIKey": AISSTREAM_API_KEY,
                        "BoundingBoxes": json.loads(BOUNDING_BOX),
                        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                    }
                    await ws.send(json.dumps(subscription))
                    logger.info("Sent subscription to AISStream")

                    # Reset reconnect delay on successful connection
                    reconnect_delay = INITIAL_RECONNECT_DELAY
                    self.ready = True

                    # Process incoming messages
                    async for message in ws:
                        if not self.running:
                            break
                        await self.process_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                self.ready = False
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.ready = False

            if self.running:
                logger.info(f"Reconnecting in {reconnect_delay:.1f}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY
                )

    async def start(self) -> None:
        """Start the AIS ingestion service."""
        self.running = True

        # Connect to NATS first
        await self.connect_nats()

        # Start the WebSocket subscription in a background task
        self.ws_task = asyncio.create_task(self.subscribe_to_aisstream())
        logger.info("AIS ingestion service started")

    async def stop(self) -> None:
        """Stop the AIS ingestion service."""
        logger.info("Stopping AIS ingestion service...")
        self.running = False
        self.ready = False

        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass

        if self.nc:
            await self.nc.close()
            logger.info("NATS connection closed")

        logger.info("AIS ingestion service stopped")


# Global service instance
service = AISIngestService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    try:
        await service.start()
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        # Continue anyway - health check will report not ready

    yield

    # Shutdown
    await service.stop()


# Create FastAPI app
app = FastAPI(
    title="AIS Ingest",
    description="AIS data ingestion from AISStream.io to NATS",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check endpoint for liveness/readiness probes."""
    return {
        "status": "healthy" if service.ready else "starting",
        "nats_connected": service.nc is not None and service.nc.is_connected,
        "websocket_connected": service.ready,
        "messages_published": service.messages_published,
        "last_message_time": service.last_message_time,
    }


@app.get("/metrics")
async def metrics():
    """Basic metrics endpoint."""
    return {
        "messages_published": service.messages_published,
        "last_message_time": service.last_message_time,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
