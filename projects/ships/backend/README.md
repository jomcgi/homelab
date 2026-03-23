# Ships API

REST and WebSocket API for AIS vessel data with SQLite persistence.

## Overview

Consumes vessel positions from NATS JetStream, stores them in SQLite, and serves data via REST API and WebSocket for real-time updates.

```mermaid
flowchart LR
    NATS[NATS JetStream] --> API[Ships API]
    API --> SQLite[(SQLite)]
    API --> REST[REST Clients]
    API --> WS[WebSocket Clients]
```

## Key Features

- **Stream replay** - Rebuilds database from NATS on startup
- **Position deduplication** - Skips redundant updates for stationary vessels
- **7-day retention** - Automatic cleanup of old position history
- **Moored detection** - Identifies vessels anchored in one location
- **Batch processing** - High-throughput message handling

## Stream Replay on Startup

Similar to trips_api, ships_api replays the NATS JetStream on startup to rebuild the SQLite database.

```mermaid
sequenceDiagram
    participant API as Ships API
    participant NATS as NATS JetStream
    participant DB as SQLite

    Note over API: Service starts
    API->>DB: Check last processed sequence
    DB-->>API: seq=12345 (or 0 if empty)
    API->>NATS: Subscribe from seq=12345
    activate NATS
    loop Replay messages
        NATS-->>API: AIS position update
        API->>API: Deduplicate
        API->>DB: Insert position
    end
    deactivate NATS
    Note over API: Replay complete
    API->>API: Start HTTP/WebSocket server
    API->>API: Start retention cleanup job
```

**Why SQLite instead of in-memory?**

- Position history retained (7 days)
- Faster startup on restarts (only replay new messages)
- Supports complex queries (bounding box, time range)

## Position Deduplication Logic

Ships often send redundant AIS updates when moored or stationary. Deduplication reduces database size and API noise.

```mermaid
flowchart TD
    START[New Position] --> FETCH[Fetch Last Position]
    FETCH --> CHECK{Last position<br/>exists?}
    CHECK -->|No| SAVE[Save Position]
    CHECK -->|Yes| DIST[Calculate Distance]
    DIST --> SPEED{Speed < 0.5 kn?}
    SPEED -->|Yes| MOORED{Distance < 100m?}
    SPEED -->|No| MOVING{Distance < 1000m?}
    MOORED -->|Yes| SKIP[Skip - Moored]
    MOORED -->|No| SAVE
    MOVING -->|Yes| SKIP2[Skip - Drifting]
    MOVING -->|No| SAVE
    SAVE --> BROADCAST[Broadcast WebSocket]
    SKIP --> END[Done]
    SKIP2 --> END
    BROADCAST --> END

    style SKIP fill:#FFB6C1
    style SKIP2 fill:#FFB6C1
    style SAVE fill:#90EE90
```

**Deduplication rules:**

| Condition         | Distance Threshold | Action                           |
| ----------------- | ------------------ | -------------------------------- |
| Speed < 0.5 knots | < 100m             | **Skip** - Moored at dock        |
| Speed < 0.5 knots | ≥ 100m             | **Save** - Moved to new mooring  |
| Speed ≥ 0.5 knots | < 1000m            | **Skip** - Normal drift/movement |
| Speed ≥ 0.5 knots | ≥ 1000m            | **Save** - Significant movement  |

**Why these thresholds?**

- 100m: Typical dock/mooring area size
- 1000m: Minimum distance for meaningful position updates
- 0.5 knots: AIS speed below this is often GPS noise

**Configuration:**

```yaml
# Environment variables
DEDUP_DISTANCE_METERS: 100 # Moored threshold
DEDUP_SPEED_THRESHOLD: 0.5 # Knots
```

## API Endpoints

### GET /api/vessels

List all known vessels.

**Response:**

Returns a flat list of vessels joined with their latest positions. Each entry contains columns from both `latest_positions` and `vessels` tables:

```json
{
  "count": 1,
  "vessels": [
    {
      "mmsi": "316001234",
      "lat": 49.2827,
      "lon": -123.1207,
      "speed": 12.5,
      "course": 180.0,
      "heading": 182,
      "nav_status": 0,
      "ship_name": "VESSEL NAME",
      "timestamp": "2024-01-15T12:00:00Z",
      "first_seen_at_location": "2024-01-15T10:00:00Z",
      "imo": "9123456",
      "call_sign": "CG1234",
      "ship_type": 70,
      "destination": "VANCOUVER",
      "dimension_a": 100,
      "dimension_b": 20,
      "dimension_c": 10,
      "dimension_d": 10,
      "draught": 5.5,
      "eta": "01-15 18:00"
    }
  ]
}
```

**Examples:**

```bash
# Get all vessels
curl https://ships-api.jomcgi.dev/api/vessels
```

### GET /api/vessels/{mmsi}

Get vessel details and current position.

**Response:**

Same flat structure as the vessels list, with additional computed fields for the single vessel:

```json
{
  "mmsi": "316001234",
  "lat": 49.2827,
  "lon": -123.1207,
  "speed": 12.5,
  "course": 180.0,
  "heading": 182,
  "nav_status": 0,
  "ship_name": "VESSEL NAME",
  "timestamp": "2024-01-15T12:00:00Z",
  "first_seen_at_location": "2024-01-15T10:00:00Z",
  "imo": "9123456",
  "call_sign": "CG1234",
  "ship_type": 70,
  "destination": "VANCOUVER",
  "dimension_a": 100,
  "dimension_b": 20,
  "dimension_c": 10,
  "dimension_d": 10,
  "draught": 5.5,
  "eta": "01-15 18:00",
  "time_at_location_seconds": 7200,
  "time_at_location_hours": 2.0,
  "is_moored": false
}
```

**Example:**

```bash
curl https://ships-api.jomcgi.dev/api/vessels/316001234
```

**Error responses:**

- `404 Not Found` - MMSI not in database

### GET /api/vessels/{mmsi}/track

Get position history for a vessel.

**Response:**

```json
{
  "mmsi": 316001234,
  "track": [
    {
      "lat": 49.2827,
      "lon": -123.1207,
      "speed": 12.5,
      "course": 180.0,
      "heading": 182,
      "nav_status": 0,
      "timestamp": "2024-01-15T12:00:00Z"
    }
  ],
  "count": 1
}
```

**Query parameters:**

- `limit` (optional) - Max positions to return (default: 1000)
- `since` (optional) - Duration like `1h`, `30m`, `2d`

**Examples:**

```bash
# Get all positions (last 7 days)
curl https://ships-api.jomcgi.dev/api/vessels/316001234/track

# Get positions from last hour
curl https://ships-api.jomcgi.dev/api/vessels/316001234/track?since=1h

# Get last 100 positions
curl https://ships-api.jomcgi.dev/api/vessels/316001234/track?limit=100
```

### WS /ws/live

WebSocket endpoint for real-time position updates.

**Message format:**

On connect, the server immediately sends a snapshot of all current vessel positions:

```json
{
  "type": "snapshot",
  "vessels": [
    {
      "mmsi": "316001234",
      "lat": 49.2827,
      "lon": -123.1207,
      "speed": 12.5,
      "course": 180.0,
      "heading": 182,
      "nav_status": 0,
      "ship_name": "VESSEL NAME",
      "timestamp": "2024-01-15T12:00:00Z"
    }
  ]
}
```

Subsequently, batched position updates are broadcast as vessels move:

```json
{
  "type": "positions",
  "positions": [
    {
      "mmsi": "316001234",
      "lat": 49.2827,
      "lon": -123.1207,
      "speed": 12.5,
      "course": 180.0,
      "heading": 182,
      "nav_status": 0,
      "ship_name": "VESSEL NAME",
      "timestamp": "2024-01-15T12:00:00Z"
    }
  ]
}
```

**Example client:**

```javascript
const ws = new WebSocket("wss://ships-api.jomcgi.dev/ws/live");

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "snapshot") {
    // Initial state — replace all markers
    msg.vessels.forEach((vessel) => updateMapMarker(vessel));
  } else if (msg.type === "positions") {
    // Incremental updates
    msg.positions.forEach((pos) => {
      console.log(`${pos.ship_name} at ${pos.lat}, ${pos.lon}`);
      updateMapMarker(pos);
    });
  }
};
```

### GET /health

Health check endpoint.

**Response:**

```json
{
  "status": "alive",
  "nats_connected": true,
  "vessel_count": 523,
  "cache_size": 523,
  "caught_up": true,
  "messages_processed": 18392
}
```

## Database Schema

### vessels

Vessel metadata from AIS Type 5 messages.

| Column         | Type | Description                  |
| -------------- | ---- | ---------------------------- |
| `mmsi`         | TEXT | Primary key, MMSI identifier |
| `imo`          | TEXT | IMO number                   |
| `call_sign`    | TEXT | Radio callsign               |
| `name`         | TEXT | Vessel name                  |
| `ship_type`    | INTEGER | AIS ship type code        |
| `dimension_a`  | INTEGER | Meters to bow             |
| `dimension_b`  | INTEGER | Meters to stern           |
| `dimension_c`  | INTEGER | Meters to port            |
| `dimension_d`  | INTEGER | Meters to starboard       |
| `destination`  | TEXT | Destination port             |
| `eta`          | TEXT | Estimated time of arrival    |
| `draught`      | REAL | Vessel draught (meters)      |
| `created_at`   | TEXT | First AIS message received   |
| `updated_at`   | TEXT | Most recent AIS message      |

### positions

Position history from AIS Type 1/2/3 messages.

| Column               | Type    | Description                  |
| -------------------- | ------- | ---------------------------- |
| `id`                 | INTEGER | Primary key, auto-increment  |
| `mmsi`               | TEXT    | Foreign key to vessels       |
| `lat`                | REAL    | Latitude                     |
| `lon`                | REAL    | Longitude                    |
| `speed`              | REAL    | Speed over ground (knots)    |
| `course`             | REAL    | Course over ground (degrees) |
| `heading`            | INTEGER | True heading (degrees)       |
| `nav_status`         | INTEGER | Navigational status code     |
| `rate_of_turn`       | INTEGER | Rate of turn                 |
| `position_accuracy`  | INTEGER | Position accuracy flag       |
| `ship_name`          | TEXT    | Vessel name from position msg|
| `timestamp`          | TEXT    | Position timestamp           |
| `received_at`        | TEXT    | When message was received    |

**Indexes:**

- `idx_positions_timestamp` - Time range queries
- `idx_positions_mmsi_timestamp` - Composite for history queries

### latest_positions

Materialized view of current vessel positions.

| Column                   | Type    | Description                    |
| ------------------------ | ------- | ------------------------------ |
| `mmsi`                   | TEXT    | Primary key                    |
| `lat`                    | REAL    | Current latitude               |
| `lon`                    | REAL    | Current longitude              |
| `speed`                  | REAL    | Current speed                  |
| `course`                 | REAL    | Current course                 |
| `heading`                | INTEGER | Current heading                |
| `nav_status`             | INTEGER | Current status                 |
| `ship_name`              | TEXT    | Vessel name                    |
| `timestamp`              | TEXT    | Last position timestamp        |
| `first_seen_at_location` | TEXT    | When arrived at current position|
| `updated_at`             | TEXT    | Last update time               |

**Updated via batch upsert whenever new positions are processed.**

## Data Retention

Position history is automatically cleaned up to prevent unbounded growth.

**Retention policy:**

- Keep positions for 7 days
- Run cleanup every 24 hours
- Delete in batches of 10,000

**Configuration:**

```yaml
POSITION_RETENTION_DAYS: 7
```

**Manual cleanup:**

```bash
# Via database directly
sqlite3 ships.db "DELETE FROM positions WHERE timestamp < datetime('now', '-7 days')"
```

## Configuration

Environment variables:

| Variable                  | Description                         | Default                 | Required |
| ------------------------- | ----------------------------------- | ----------------------- | -------- |
| `NATS_URL`                | NATS server URL                     | `nats://localhost:4222` | Yes      |
| `CORS_ORIGINS`            | Allowed CORS origins (comma-sep)    | `http://localhost:3000` | No       |
| `DB_PATH`                 | SQLite database path                | `/tmp/ships.db`         | No       |
| `POSITION_RETENTION_DAYS` | Days to keep positions              | `7`                     | No       |
| `DEDUP_DISTANCE_METERS`   | Deduplication threshold             | `100`                   | No       |
| `DEDUP_SPEED_THRESHOLD`   | Speed below which to dedupe (knots) | `0.5`                   | No       |

## Running Locally

```bash
# Start dependencies
docker run -d --name nats -p 4222:4222 nats:latest -js

# Run service
export NATS_URL=nats://localhost:4222
export DB_PATH=/tmp/ships.db
bazel run //projects/ships/backend:main

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/vessels
```

## Deployment

Deployed via ArgoCD to Kubernetes cluster.

**Resources:**

- Helm chart: `projects/ships/chart/`
- Overlay: `projects/ships/deploy/`
- Service URL: https://ships-api.jomcgi.dev

**Persistent storage:**

- Longhorn PVC mounted at `/data`
- Database path: `/data/ships.db`

## Observability

### Stats

Exposed at `/api/stats`:

```json
{
  "vessel_count": 523,
  "position_count": 18392,
  "cache_size": 523,
  "messages_received": 50000,
  "messages_deduplicated": 31608,
  "connected_clients": 2,
  "replay_complete": true,
  "retention_days": 7
}
```

### Traces

Instrumented with OpenTelemetry (auto-injected by Kyverno):

- HTTP request traces
- NATS message processing
- WebSocket connections

View in SigNoz: https://signoz.jomcgi.dev

### Logs

Standard Python logging:

```
2024-01-15 12:00:00 - ships_api - INFO - Catchup complete. 18392 positions loaded.
2024-01-15 12:00:01 - ships_api - INFO - WebSocket client connected. Total: 1
```

## Ship Type Codes

Common AIS ship type codes:

| Code  | Description       |
| ----- | ----------------- |
| 30    | Fishing           |
| 31-32 | Towing            |
| 36    | Sailing           |
| 37    | Pleasure Craft    |
| 40-49 | High Speed Craft  |
| 50    | Pilot Vessel      |
| 51    | Search and Rescue |
| 52    | Tug               |
| 60-69 | Passenger         |
| 70-79 | Cargo             |
| 80-89 | Tanker            |

Full list: [AIS Ship Type Codes](https://api.vtexplorer.com/docs/ref-aistypes.html)

## Navigational Status Codes

| Code | Description                |
| ---- | -------------------------- |
| 0    | Under way using engine     |
| 1    | At anchor                  |
| 2    | Not under command          |
| 3    | Restricted manoeuvrability |
| 5    | Moored                     |
| 8    | Under way sailing          |
| 15   | Not defined                |

## Related Services

- **ships.jomcgi.dev** - Frontend map viewer (WebSocket client)
- **ais-ingest** - Receives AIS messages from SDR and publishes to NATS
- **trips_api** - Similar architecture for GPS trip tracking
