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
from contextlib import asynccontextmanager
from datetime import timedelta

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
        stream_config = StreamConfig(
            name="ais",
            subjects=["ais.>"],
            max_age=int(timedelta(hours=24).total_seconds() * 1e9),  # nanoseconds
            storage=StorageType.FILE,
            discard=DiscardPolicy.OLD,
            description="AIS position reports from AISStream.io",
        )
        await self.js.add_stream(stream_config)
        logger.info("Created/updated 'ais' stream with 24h retention")

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

            # Only process PositionReport messages
            if msg_type != "PositionReport":
                return

            # Extract the position report
            position = message.get("Message", {}).get("PositionReport", {})
            metadata = message.get("MetaData", {})

            if not position or not metadata:
                return

            mmsi = str(metadata.get("MMSI", ""))
            if not mmsi:
                return

            # Build the position data
            data = {
                "mmsi": mmsi,
                "lat": position.get("Latitude"),
                "lon": position.get("Longitude"),
                "speed": position.get("Sog"),  # Speed over ground
                "course": position.get("Cog"),  # Course over ground
                "heading": position.get("TrueHeading"),
                "timestamp": metadata.get("time_utc"),
                "ship_name": metadata.get("ShipName", "").strip(),
            }

            # Skip if coordinates are invalid
            if data["lat"] is None or data["lon"] is None:
                return

            await self.publish_position(mmsi, data)
            logger.debug(f"Published position for MMSI {mmsi}")

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def subscribe_to_aisstream(self) -> None:
        """Connect to AISStream and process messages with reconnection logic."""
        reconnect_delay = INITIAL_RECONNECT_DELAY

        while self.running:
            try:
                logger.info(f"Connecting to AISStream at {AISSTREAM_URL}")
                async with websockets.connect(AISSTREAM_URL) as ws:
                    # Send subscription message within 3 seconds
                    subscription = {
                        "APIKey": AISSTREAM_API_KEY,
                        "BoundingBoxes": json.loads(BOUNDING_BOX),
                        "FilterMessageTypes": ["PositionReport"],
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
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if self.running:
                self.ready = False
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
