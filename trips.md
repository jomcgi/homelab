# Yukon Trip Tracker - Image Hosting Stack Specification

## Overview

Self-hosted image hosting infrastructure for `trips.jomcgi.dev` to serve 10,000+ GoPro images with live updates during the trip.

### Goals
- Host 10k+ 3.5MB JPEG images without emptying wallet
- Serve multiple image sizes (thumbnail, preview, full) with high quality
- Live updates via WebSocket when new images are uploaded during trip
- Leverage Cloudflare edge caching for cost/performance
- Run entirely on homelab Kubernetes cluster with Longhorn storage

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser                                        │
│                     trips.jomcgi.dev (React App)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                           │
                    │ Images                    │ Metadata + WebSocket
                    ▼                           ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│   img.trips.jomcgi.dev      │   │   api.trips.jomcgi.dev      │
│   (Cloudflare cached)       │   │                             │
└─────────────────────────────┘   └─────────────────────────────┘
                    │                           │
                    │ Cloudflare Tunnel         │
                    ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ namespace: trips                                                            │
│  ┌─────────────────────┐   ┌─────────────┐   ┌─────────────────────┐       │
│  │     trips-nginx     │   │  imgproxy   │   │     trips-api       │       │
│  │  /full/* → seaweedfs│   │  (resize)   │   │  GET /api/points    │       │
│  │  /thumb/* → imgproxy│   │             │   │  WS  /ws/live       │       │
│  └─────────────────────┘   └─────────────┘   └─────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
         │                                              │
         │ cross-namespace                              │ cross-namespace
         ▼                                              ▼
┌─────────────────────────────┐       ┌─────────────────────────────┐
│ namespace: seaweedfs        │       │ namespace: nats             │
│  ┌─────────────────────┐    │       │  ┌─────────────────────┐    │
│  │ SeaweedFS (S3 API)  │    │       │  │ NATS (JetStream)    │    │
│  │ Longhorn: 100Gi     │    │       │  │ Longhorn: 10Gi      │    │
│  └─────────────────────┘    │       │  └─────────────────────┘    │
└─────────────────────────────┘       └─────────────────────────────┘
        ▲                                    ▲
        │                                    │
        └────────────┬───────────────────────┘
                     │
              ┌──────────────┐
              │Upload Script │
              │ (EXIF→S3→NATS)│
              └──────────────┘
```

### Data Flow

1. **Upload**: GoPro images → Upload script extracts EXIF (GPS, timestamp) → Uploads to SeaweedFS → Publishes metadata to NATS
2. **Initial Load**: React app fetches `/api/points` → API server returns all points from NATS stream replay
3. **Live Updates**: React app connects to `/ws/live` → API server subscribes to NATS → Broadcasts new points to all clients
4. **Image Serving**: Browser requests `/thumb/...` → Cloudflare cache miss → nginx → imgproxy → SeaweedFS → Response cached at edge

---

## Stage 1: Namespace Strategy

### Context
Following homelab patterns, infrastructure components get dedicated namespaces for isolation and reusability.

### Namespace Layout
| Namespace | Purpose | Components |
|-----------|---------|------------|
| `seaweedfs` | Object storage | Master, Volume, Filer (S3 API) |
| `nats` | Message streaming | NATS server with JetStream |
| `trips` | Trip application | imgproxy, nginx, API server |

### Why Separate Namespaces
- **Reusability**: SeaweedFS/NATS are shared infrastructure for multiple projects
- **Isolation**: Independent scaling, resource quotas, RBAC
- **Lifecycle**: Upgrade infrastructure without affecting apps
- **Consistency**: Matches existing homelab patterns (signoz, longhorn, etc.)

### Shared Infrastructure Pattern

SeaweedFS and NATS are deployed once and used by multiple projects:

```
┌─────────────────────────────────────────────────────────────┐
│                    Shared Infrastructure                     │
│  ┌─────────────────────┐       ┌─────────────────────┐      │
│  │ seaweedfs namespace │       │   nats namespace    │      │
│  │   S3 API :8333      │       │   NATS :4222        │      │
│  └─────────────────────┘       └─────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
          │                              │
          │ buckets                      │ streams
          ▼                              ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  trips namespace │  │ project-b ns     │  │ project-c ns     │
│  bucket: trips   │  │ bucket: proj-b   │  │ stream: EVENTS   │
│  stream: POINTS  │  │                  │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

**For new projects using this infrastructure:**
- SeaweedFS: Create a new bucket, use `seaweedfs-filer.seaweedfs.svc.cluster.local:8333`
- NATS: Create a new stream, use `nats.nats.svc.cluster.local:4222`

### Tasks
- [ ] Namespaces created automatically via ArgoCD `CreateNamespace=true`
- [ ] Add labels: `app.kubernetes.io/part-of: yukon-tracker` to all three

### Acceptance Criteria
- `kubectl get ns seaweedfs nats trips` succeeds
- All namespaces have correct labels

---

## Stage 2: SeaweedFS Deployment

### Context
SeaweedFS provides S3-compatible object storage for the trip images. Using SeaweedFS instead of MinIO due to MinIO's recent license/feature changes. SeaweedFS is Apache 2.0 licensed and lightweight.

### Configuration Requirements
- **Storage class**: `longhorn`
- **Volume storage**: 100Gi (holds ~25k full-res images with headroom)
- **Master storage**: 1Gi
- **Filer storage**: 5Gi
- **S3 API**: Enabled on port 8333
- **Auth**: Disabled for simplicity (internal cluster only)
- **Replicas**: 1 each for master, volume, filer (homelab, not HA)

### Tasks
- [ ] Add SeaweedFS Helm repo: `https://seaweedfs.github.io/seaweedfs/helm`
- [ ] Create Helm values file with above configuration
- [ ] Deploy SeaweedFS to `seaweedfs` namespace
- [ ] Verify S3 API is accessible: `curl http://seaweedfs-filer.seaweedfs.svc:8333`
- [ ] Create `trip-images` bucket

### Helm Values Structure
```yaml
# SeaweedFS Helm chart: https://github.com/seaweedfs/seaweedfs/tree/master/k8s/charts/seaweedfs
global:
  storageClass: longhorn

master:
  replicas: 1
  persistence:
    enabled: true
    size: 1Gi
    storageClass: longhorn

volume:
  replicas: 1
  dataDirs:
    - name: data
      type: persistentVolumeClaim
      size: 100Gi
      storageClass: longhorn
      maxVolumes: 0  # Auto-calculate

filer:
  replicas: 1
  persistence:
    enabled: true
    size: 5Gi
    storageClass: longhorn
  s3:
    enabled: true
    port: 8333
    enableAuth: false
```

**Note**: Service names depend on Helm release name. With `helm install seaweedfs ...`:
- Master: `seaweedfs-master:9333`
- Filer: `seaweedfs-filer:8888`
- S3 API: `seaweedfs-filer:8333`

### Acceptance Criteria
- All SeaweedFS pods running
- Can create bucket via mc/aws cli
- Can upload and retrieve test file via S3 API

---

## Stage 3: NATS with JetStream Deployment

### Context
NATS JetStream provides persistent message streaming for trip point metadata. The stream acts as the source of truth - API server replays it on startup and subscribes for live updates.

### Configuration Requirements
- **Storage class**: `longhorn`
- **File store**: 10Gi PVC
- **Memory store**: 256Mi
- **Cluster**: Single replica (JetStream works fine without clustering)

**Note**: WebSocket is not needed - the API server handles WebSocket connections to browsers and communicates with NATS via the standard client port (4222).

### Stream Configuration
- **Name**: `TRIP_POINTS`
- **Subjects**: `trip.points.>`
- **Retention**: Limits (keep all messages)
- **Storage**: File
- **Max messages per subject**: 100000

### Tasks
- [ ] Add NATS Helm repo: `https://nats-io.github.io/k8s/helm/charts/`
- [ ] Create Helm values file with JetStream enabled
- [ ] Deploy NATS to `nats` namespace
- [ ] Create stream initialization Job (runs post-deploy)
- [ ] Verify stream exists: `nats stream info TRIP_POINTS`

### Helm Values Structure
```yaml
# NATS Helm chart: https://github.com/nats-io/k8s
config:
  jetstream:
    enabled: true
    fileStore:
      enabled: true
      dir: /data
      pvc:
        enabled: true
        size: 10Gi
        storageClassName: longhorn
    memoryStore:
      enabled: true
      maxSize: 256Mi
```

**Note**: Service name with `helm install nats ...`: `nats.nats.svc.cluster.local:4222`

### Stream Init Job
The job should:
1. Wait for NATS to be ready
2. Create `TRIP_POINTS` stream with correct config
3. Be idempotent (handle stream already exists)

### Acceptance Criteria
- NATS pod running
- `TRIP_POINTS` stream exists
- Can publish and consume test message

---

## Stage 4: imgproxy Deployment

### Context
imgproxy handles on-demand image resizing. Uses libvips for high-quality Lanczos resampling. Cloudflare caches the resized images at the edge, so imgproxy only processes each size once.

### Configuration Requirements
- **S3 endpoint**: `http://seaweedfs-filer.seaweedfs.svc.cluster.local:8333`
- **Quality**: 90 default, WebP 92, JPEG 90
- **Security**: `IMGPROXY_ALLOW_INSECURE_URLS=true` (internal only)
- **Concurrency**: 4
- **Max source resolution**: 50MP
- **Strip metadata**: true (for thumbnails, saves bytes)
- **Keep color profile**: true (accurate colors)

### Environment Variables
```
# S3 Configuration (SeaweedFS in seaweedfs namespace)
IMGPROXY_USE_S3=true
IMGPROXY_S3_ENDPOINT=http://seaweedfs-filer.seaweedfs.svc.cluster.local:8333
IMGPROXY_S3_REGION=us-east-1
# Empty credentials work with SeaweedFS auth disabled
AWS_ACCESS_KEY_ID=anonymous
AWS_SECRET_ACCESS_KEY=anonymous

# Image Processing
IMGPROXY_QUALITY=90
IMGPROXY_FORMAT_QUALITY=webp=92,avif=90,jpeg=90
IMGPROXY_ENABLE_WEBP_DETECTION=true
IMGPROXY_ENFORCE_WEBP=false
IMGPROXY_CONCURRENCY=4
IMGPROXY_MAX_SRC_RESOLUTION=50
IMGPROXY_STRIP_METADATA=true
IMGPROXY_STRIP_COLOR_PROFILE=false

# Security (internal cluster only)
IMGPROXY_ALLOW_INSECURE_URLS=true
```

### Tasks
- [ ] Create imgproxy Deployment with above env vars
- [ ] Create imgproxy Service on port 8080
- [ ] Add health checks on `/health`
- [ ] Set resource limits: requests 100m/256Mi, limits 1000m/1Gi

### Acceptance Criteria
- imgproxy pod running
- Health endpoint returns 200
- Can resize test image: `curl "http://imgproxy:8080/unsafe/fit/300/300/plain/s3://trip-images/test.jpg"`

---

## Stage 5: nginx Routing Layer

### Context
nginx routes image requests to the appropriate backend:
- `/full/*` → SeaweedFS directly (original images)
- `/thumb/*` → imgproxy (300px thumbnails)
- `/preview/*` → imgproxy (1200px previews)
- `/gallery/*` → imgproxy (600px gallery size)

All responses get `Cache-Control: public, max-age=31536000, immutable` header.

### URL Rewriting
```
/thumb/2025-yukon/img.jpg → imgproxy: /unsafe/fit/300/300/sm/0/q:85/plain/s3://trip-images/2025-yukon/img.jpg
/preview/2025-yukon/img.jpg → imgproxy: /unsafe/fit/1200/1200/sm/0/q:90/plain/s3://trip-images/2025-yukon/img.jpg
/gallery/2025-yukon/img.jpg → imgproxy: /unsafe/fit/600/600/sm/0/q:88/plain/s3://trip-images/2025-yukon/img.jpg
/full/2025-yukon/img.jpg → seaweedfs: /trip-images/2025-yukon/img.jpg
```

### Upstream Configuration
```nginx
upstream seaweedfs {
    server seaweedfs-filer.seaweedfs.svc.cluster.local:8333;
}

upstream imgproxy {
    server trips-imgproxy.trips.svc.cluster.local:8080;
}
```

### Tasks
- [ ] Create ConfigMap with nginx.conf
- [ ] Configure upstream blocks for seaweedfs (cross-namespace) and imgproxy
- [ ] Configure location blocks with rewrites
- [ ] Add cache-control headers
- [ ] Create nginx Deployment mounting the ConfigMap
- [ ] Create nginx Service on port 80
- [ ] Add health endpoint at `/health`

### Acceptance Criteria
- nginx pod running
- `/health` returns 200
- `/full/test.jpg` proxies to SeaweedFS
- `/thumb/test.jpg` proxies through imgproxy with correct resize params

---

## Stage 6: API Server

### Context
FastAPI server that:
1. On startup: Replays entire NATS stream to build in-memory cache
2. Serves REST API for initial data load
3. Subscribes to NATS for new points
4. Broadcasts new points to WebSocket clients

### Endpoints
- `GET /health` - Health check with stats
- `GET /api/points` - All points (optional: `?limit=N&offset=N&trip_id=X`)
- `GET /api/points/{id}` - Single point
- `GET /api/stats` - Trip statistics (counts, wildlife sightings)
- `POST /api/upload` - Upload image (extracts EXIF, stores in S3, publishes to NATS)
- `WS /ws/live` - WebSocket for live updates

### Upload Endpoint
```
POST /api/upload
Authorization: Bearer <TRIP_API_KEY>
Content-Type: multipart/form-data

image: <file>
trip_id: 2025-yukon (optional, defaults to current trip)
```

Response:
```json
{"id": 1234, "lat": 49.28, "lng": -123.12, "image_url": "/full/2025-yukon/img_001234.jpg"}
```

The upload endpoint:
1. Validates API key (from environment variable or 1Password secret)
2. Extracts EXIF GPS coordinates and timestamp
3. Uploads image to SeaweedFS with sequential filename
4. Publishes point metadata to NATS
5. Returns the created point

This enables mobile uploads without kubectl access.

### WebSocket Protocol
```json
// On connect
{"type": "connected", "cached_points": 1234}

// New point broadcast
{"type": "new_point", "point": {...}}

// Keepalive
Client: "ping"
Server: "pong"
```

### Point Schema
```json
{
  "id": 1,
  "lat": 49.2827,
  "lng": -123.1207,
  "timestamp": "2025-06-15T14:30:00Z",
  "image_url": "/full/2025-yukon/img_000001.jpg",
  "thumb_url": "/thumb/2025-yukon/img_000001.jpg",
  "location": "Vancouver",
  "animal": null
}
```

### Tasks
- [ ] Create FastAPI application with NATS client
- [ ] Implement stream replay on startup (ordered consumer, deliver all)
- [ ] Implement live subscription (deliver new only)
- [ ] Implement WebSocket connection manager
- [ ] Implement REST endpoints
- [ ] Add CORS for `trips.jomcgi.dev` and localhost dev
- [ ] Create Dockerfile (python:3.12-slim, uvicorn)
- [ ] Create Kubernetes Deployment and Service
- [ ] Configure `NATS_URL=nats://nats.nats.svc.cluster.local:4222`

### Dependencies
- fastapi
- uvicorn[standard]
- nats-py
- pydantic
- python-multipart (for file uploads)
- pillow (for EXIF extraction)
- boto3 (for S3 uploads to SeaweedFS)
- opentelemetry-instrumentation-fastapi
- opentelemetry-exporter-otlp

### Observability

The `trips` namespace will automatically receive:
- **Linkerd sidecar injection** - All HTTP traffic traced automatically
- **OTEL environment variables** - Injected by Kyverno policy

The API server should initialize OTEL tracing on startup:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# After creating FastAPI app
FastAPIInstrumentor.instrument_app(app)
```

Traces will be exported to SigNoz via the OTEL collector.

### Acceptance Criteria
- API pod running and healthy
- `/api/points` returns empty array (no data yet)
- `/api/stats` returns stats
- WebSocket connects and receives `connected` message
- After publishing test point to NATS, it appears in API and broadcasts to WS

---

## Stage 7: Upload Script

### Context
Python script to process GoPro images:
1. Extract EXIF data (GPS coordinates, timestamp)
2. Upload original image to SeaweedFS
3. Publish metadata to NATS

Supports single file, directory batch, and `--watch` mode for live upload during trip.

### Deployment Options

**Option A: Mobile-friendly upload endpoint** (recommended for trip)

Expose an authenticated upload API via Cloudflare Tunnel:

```yaml
# Add to cloudflare-tunnel values.yaml
ingress:
  routes:
    - hostname: upload.trips.jomcgi.dev
      service: http://trips-api.trips.svc.cluster.local:8000
```

```bash
# Upload from phone or laptop - works anywhere with internet
curl -X POST https://upload.trips.jomcgi.dev/api/upload \
  -H "Authorization: Bearer $TRIP_API_KEY" \
  -F "image=@IMG_0001.JPG"
```

The API server handles EXIF extraction, S3 upload, and NATS publishing.

**Option B: Local with port-forwarding** (backup/batch upload)
```bash
# Terminal 1: Port-forward to SeaweedFS (in seaweedfs namespace)
kubectl port-forward svc/seaweedfs-filer 8333:8333 -n seaweedfs

# Terminal 2: Port-forward to NATS (in nats namespace)
kubectl port-forward svc/nats 4222:4222 -n nats

# Terminal 3: Run upload script
python upload.py --watch /path/to/DCIM/ \
  --s3-endpoint http://localhost:8333 \
  --nats-url nats://localhost:4222
```

**Option C: Kubernetes Job** (for batch uploads)
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: trip-upload
  namespace: trips  # Runs in trips namespace, accesses cross-namespace services
spec:
  template:
    spec:
      containers:
      - name: upload
        image: ghcr.io/jomcgi/trip-upload:latest
        env:
        - name: S3_ENDPOINT
          value: http://seaweedfs-filer.seaweedfs.svc.cluster.local:8333
        - name: NATS_URL
          value: nats://nats.nats.svc.cluster.local:4222
        volumeMounts:
        - name: images
          mountPath: /images
      volumes:
      - name: images
        hostPath:
          path: /mnt/gopro  # Mount USB/SD card here
      restartPolicy: Never
```

### EXIF Extraction
- GPSLatitude + GPSLatitudeRef → decimal latitude
- GPSLongitude + GPSLongitudeRef → decimal longitude
- DateTimeOriginal → ISO timestamp

### S3 Upload
- Bucket: `trip-images`
- Key format: `{trip_id}/{filename}` (e.g., `2025-yukon/IMG_0001.JPG`)
- Content-Type: `image/jpeg`

### NATS Publish
- Subject: `trip.points.{id}`
- Payload: JSON point object

### CLI Interface
```bash
# Single image
python upload.py /path/to/image.jpg

# Directory
python upload.py /path/to/DCIM/

# Watch mode (live during trip)
python upload.py --watch /path/to/DCIM/

# Options
--trip-id TEXT      Trip identifier (default: 2025-yukon)
--start-id INT      Starting point ID (default: 1)
--s3-endpoint TEXT  SeaweedFS endpoint
--nats-url TEXT     NATS URL
```

### Failure Handling

The upload script must be resilient to network issues:

```python
# Local SQLite queue for pending uploads
# - On failure: queue locally, retry with exponential backoff
# - On success: remove from queue
# - On startup: process any queued items first

class UploadQueue:
    def __init__(self, db_path="~/.trip-upload-queue.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pending (
                path TEXT PRIMARY KEY,
                trip_id TEXT,
                attempts INT DEFAULT 0,
                last_attempt TIMESTAMP
            )
        """)

    def add(self, path, trip_id): ...
    def mark_complete(self, path): ...
    def get_pending(self): ...
```

### Tasks
- [ ] Create upload.py with argument parsing
- [ ] Implement EXIF extraction using Pillow
- [ ] Implement S3 upload using boto3
- [ ] Implement NATS publishing
- [ ] Implement directory batch processing
- [ ] Implement watch mode with file detection
- [ ] Add local SQLite queue for failed uploads
- [ ] Add retry with exponential backoff (max 5 attempts)
- [ ] Add duplicate detection (skip already-uploaded files)
- [ ] Add progress logging with ETA
- [ ] Create requirements.txt (boto3, Pillow, nats-py, requests)

### Acceptance Criteria
- Can upload single test image
- Point appears in NATS stream
- Point appears in API response
- WebSocket clients receive broadcast
- Batch upload processes multiple files
- Watch mode detects and uploads new files

---

## Stage 8: Cloudflare Tunnel Configuration

### Context
Cloudflare tunnel exposes the services to the internet. Need two hostnames:
- `img.trips.jomcgi.dev` → trips-nginx (images)
- `api.trips.jomcgi.dev` → trips-api (metadata + WebSocket)

### Tunnel Ingress Config

Add to `overlays/prod/cloudflare-tunnel/values.yaml`:

```yaml
ingress:
  routes:
    # ... existing routes ...
    - hostname: img.trips.jomcgi.dev
      service: http://trips-nginx.trips.svc.cluster.local:80
    - hostname: api.trips.jomcgi.dev
      service: http://trips-api.trips.svc.cluster.local:8000
```

### Cloudflare Caching Rules

Configure via Cloudflare Dashboard (Cache Rules):
- **Match**: `img.trips.jomcgi.dev/*`
- **Cache eligibility**: Eligible for cache
- **Edge TTL**: Override - 1 year (31536000)
- **Browser TTL**: Override - 1 year

**Note**: nginx already sets `Cache-Control: public, max-age=31536000, immutable` which Cloudflare will respect.

### DNS Configuration

Create CNAME records in Cloudflare DNS pointing to the tunnel:

| Hostname | Type | Target |
|----------|------|--------|
| `img.trips.jomcgi.dev` | CNAME | `<tunnel-id>.cfargotunnel.com` |
| `api.trips.jomcgi.dev` | CNAME | `<tunnel-id>.cfargotunnel.com` |
| `upload.trips.jomcgi.dev` | CNAME | `<tunnel-id>.cfargotunnel.com` |

Or use Cloudflare's automatic DNS management if the tunnel is configured with `--credentials-file`.

### Tasks
- [ ] Create DNS records for new hostnames
- [ ] Update Cloudflare tunnel config with new hostnames
- [ ] Configure cache rules for img subdomain
- [ ] Test image serving through tunnel
- [ ] Test API and WebSocket through tunnel

### Acceptance Criteria
- `https://img.trips.jomcgi.dev/health` returns 200
- `https://api.trips.jomcgi.dev/health` returns 200
- Image requests get cached (check CF-Cache-Status header)
- WebSocket connects successfully

---

## Stage 9: React App Integration

### Context
Update the existing React trip tracker app to use the new API instead of mock data.

### Changes Required

#### Data Fetching Hook
```typescript
// hooks/useTripData.ts
export function useTripData() {
  const [points, setPoints] = useState<TripPoint[]>([]);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    // Initial load
    fetch('https://api.trips.jomcgi.dev/api/points')
      .then(r => r.json())
      .then(data => setPoints(data.points));

    // WebSocket for live updates
    const ws = new WebSocket('wss://api.trips.jomcgi.dev/ws/live');
    ws.onopen = () => setIsLive(true);
    ws.onclose = () => setIsLive(false);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'new_point') {
        setPoints(prev => [...prev, msg.point]);
      }
    };

    return () => ws.close();
  }, []);

  return { points, isLive };
}
```

#### Image URL Updates
Replace mock image URLs with real endpoints:
```typescript
// Thumbnail for map/gallery
point.thumb_url  // or: `https://img.trips.jomcgi.dev/thumb/${point.image_url}`

// Preview for lightbox
`https://img.trips.jomcgi.dev/preview/${point.image_url}`

// Full resolution for download
`https://img.trips.jomcgi.dev${point.image_url}`
```

### Performance Considerations

With 10k+ points, the current app will have issues:

1. **Map markers**: Can't render 10k individual markers
   - Solution: Use marker clustering (e.g., `supercluster` library)
   - Or: Only show markers for wildlife sightings, use line for route

2. **Image filmstrip**: Rendering 10k thumbnails will lag
   - Solution: Virtual scrolling (already partially implemented with `visibleRange`)
   - Increase virtualization window

3. **Initial load**: 10k points JSON is ~1-2MB
   - Solution: Paginate or stream points
   - Or: Accept initial load time (cached by browser)

### Tasks
- [ ] Create `useTripData` hook with fetch + WebSocket
- [ ] Replace `generateDenseRoute()` mock data with API fetch
- [ ] Update image URLs:
  - Thumbnail: `https://img.trips.jomcgi.dev/thumb/${point.image_path}`
  - Preview: `https://img.trips.jomcgi.dev/preview/${point.image_path}`
  - Full: `https://img.trips.jomcgi.dev/full/${point.image_path}`
- [ ] Add loading state while fetching initial data
- [ ] Add error state if API unavailable
- [ ] Implement WebSocket reconnection with exponential backoff
- [ ] Add marker clustering for 10k+ points
- [ ] Optimize filmstrip virtualization for large datasets
- [ ] Remove mock `wildlifeSpots` array (use real data)
- [ ] Test with progressively larger datasets (100, 1k, 10k points)

### Acceptance Criteria
- App loads points from API on startup
- Loading indicator shown during fetch
- Error message if API down
- Images display correctly at all sizes
- Map performs smoothly with 10k+ points (no lag when panning)
- New points appear in real-time when uploaded
- WebSocket reconnects automatically on disconnect
- Filmstrip scrolls smoothly through entire dataset

---

## Stage 10: ArgoCD Integration

### Context
Create ArgoCD Applications for GitOps deployment of the stack.

### Directory Structure

Following the existing homelab overlay pattern (each service in its own namespace):

```
charts/
├── seaweedfs/                 # Wrapper chart → seaweedfs namespace
│   ├── Chart.yaml             # dependencies: seaweedfs from seaweedfs.github.io
│   └── values.yaml
├── nats/                      # Wrapper chart → nats namespace
│   ├── Chart.yaml             # dependencies: nats from nats-io.github.io
│   └── values.yaml
└── trips/                     # Custom chart → trips namespace
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── imgproxy-deployment.yaml
        ├── nginx-configmap.yaml
        ├── nginx-deployment.yaml
        ├── api-deployment.yaml
        └── services.yaml

overlays/
└── prod/
    ├── seaweedfs/             # → namespace: seaweedfs
    │   ├── application.yaml
    │   ├── kustomization.yaml
    │   ├── values.yaml
    │   ├── BUILD
    │   └── manifests/
    │       └── all.yaml
    ├── nats/                  # → namespace: nats
    │   ├── application.yaml
    │   ├── kustomization.yaml
    │   ├── values.yaml
    │   ├── BUILD
    │   └── manifests/
    │       └── all.yaml
    └── trips/                 # → namespace: trips
        ├── application.yaml
        ├── kustomization.yaml
        ├── values.yaml
        ├── BUILD
        └── manifests/
            └── all.yaml
```

### Example Chart.yaml (Wrapper Pattern)

```yaml
# charts/seaweedfs/Chart.yaml
apiVersion: v2
name: seaweedfs
description: SeaweedFS distributed object storage
type: application
version: 1.0.0
appVersion: "3.71"

dependencies:
  - name: seaweedfs
    version: "3.71.0"
    repository: https://seaweedfs.github.io/seaweedfs/helm
```

### Example Application.yaml

```yaml
# overlays/prod/seaweedfs/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: prod-seaweedfs
  namespace: argocd
  labels:
    app.kubernetes.io/part-of: yukon-tracker
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: charts/seaweedfs
    targetRevision: HEAD
    helm:
      releaseName: seaweedfs
      valueFiles:
        - values.yaml
        - ../../overlays/prod/seaweedfs/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: seaweedfs  # Dedicated namespace
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### Example BUILD File

```python
# overlays/prod/seaweedfs/BUILD
genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/seaweedfs:Chart.yaml",
        "//charts/seaweedfs:values.yaml",
        "//charts/seaweedfs:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template seaweedfs charts/seaweedfs --namespace seaweedfs --values charts/seaweedfs/values.yaml --values overlays/prod/seaweedfs/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-seaweedfs",
    tags = ["manual"],
    tools = ["@multitool//tools/helm"],
    visibility = ["//visibility:public"],
)
```

### Tasks
- [ ] Create wrapper Helm charts: `charts/seaweedfs/`, `charts/nats/`
- [ ] Create custom chart: `charts/trips/` for imgproxy, nginx, API
- [ ] Run `helm dependency update` for each wrapper chart
- [ ] Create overlay directories: `overlays/prod/{seaweedfs,nats,trips}/`
- [ ] Create ArgoCD Application manifests pointing to charts
- [ ] Create BUILD files for each overlay
- [ ] Add to `overlays/prod/kustomization.yaml`:
  ```yaml
  resources:
    # ... existing ...
    - ./seaweedfs
    - ./nats
    - ./trips
  ```
- [ ] Run `format` to render manifests
- [ ] Commit `manifests/all.yaml` files and push

### Deployment Ordering with Sync Waves

SeaweedFS and NATS must be healthy before trips-stack can start. Use ArgoCD sync waves:

```yaml
# overlays/prod/seaweedfs/application.yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"

# overlays/prod/nats/application.yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"

# overlays/prod/trips/application.yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "2"  # Deploys after wave 1
```

Wave 1 (seaweedfs, nats) syncs first. Wave 2 (trips) waits until wave 1 is healthy.

### Acceptance Criteria
- All three Applications sync successfully in order
- Changes to GitOps repo trigger updates
- Stack recovers from manual changes (self-heal)

---

## Appendix: Resource Estimates

### Trip Stack Resources

| Component | CPU Request | Memory Request | Storage |
|-----------|-------------|----------------|---------|
| imgproxy | 100m | 256Mi | - |
| nginx | 20m | 32Mi | - |
| trips-api | 50m | 64Mi | - |
| **Trip Total** | **170m** | **352Mi** | **-** |

### Shared Infrastructure Resources

| Component | CPU Request | Memory Request | Storage | Notes |
|-----------|-------------|----------------|---------|-------|
| SeaweedFS Master | 50m | 64Mi | 1Gi | Metadata only |
| SeaweedFS Volume | 100m | 128Mi | 100Gi | Expand as needed |
| SeaweedFS Filer | 100m | 128Mi | 5Gi | S3 API + index |
| NATS | 50m | 64Mi | 10Gi | All streams |
| **Infra Total** | **300m** | **384Mi** | **116Gi** | |

**Capacity Planning:**
- SeaweedFS 100Gi holds ~25k full-res images (3.5MB each) with headroom
- NATS 10Gi holds millions of small messages across all streams
- Both can be expanded via Longhorn PVC resize if needed

## Appendix: Testing Commands

```bash
# Check all pods across namespaces
kubectl get pods -n seaweedfs
kubectl get pods -n nats
kubectl get pods -n trips

# Test SeaweedFS S3 (in seaweedfs namespace)
kubectl run -it --rm aws-cli -n seaweedfs --image=amazon/aws-cli --restart=Never -- \
  --endpoint-url=http://seaweedfs-filer:8333 s3 ls

# Test NATS stream (in nats namespace)
kubectl exec -it deploy/nats-box -n nats -- nats stream info TRIP_POINTS

# Test imgproxy health (in trips namespace)
kubectl run -it --rm curl -n trips --image=curlimages/curl --restart=Never -- \
  http://trips-imgproxy:8080/health

# Test API health (in trips namespace)
kubectl run -it --rm curl -n trips --image=curlimages/curl --restart=Never -- \
  http://trips-api:8000/health

# Test cross-namespace connectivity from trips
kubectl run -it --rm curl -n trips --image=curlimages/curl --restart=Never -- \
  http://seaweedfs-filer.seaweedfs.svc.cluster.local:8333

# Test image resize through nginx
kubectl run -it --rm curl -n trips --image=curlimages/curl --restart=Never -- \
  -I http://trips-nginx/thumb/2025-yukon/test.jpg

# Port forward for local testing (note different namespaces)
kubectl port-forward svc/seaweedfs-filer 8333:8333 -n seaweedfs
kubectl port-forward svc/nats 4222:4222 -n nats
kubectl port-forward svc/trips-api 8000:8000 -n trips
kubectl port-forward svc/trips-nginx 8080:80 -n trips
```

## Appendix: Backup Strategy

### SeaweedFS Volume (Image Data)
Configure Longhorn recurring backup for the SeaweedFS volume PVC:

```yaml
apiVersion: longhorn.io/v1beta2
kind: RecurringJob
metadata:
  name: seaweedfs-backup
  namespace: longhorn-system
spec:
  cron: "0 2 * * *"  # Daily at 2 AM
  task: backup
  retain: 7
  concurrency: 1
  labels:
    recurring-job.longhorn.io/source: user
    recurring-job.longhorn.io/group: seaweedfs
```

Apply to PVC with label: `recurring-job.longhorn.io/group: seaweedfs`

### NATS JetStream
NATS streams can be replayed from the beginning, so backup is less critical. However, for disaster recovery:

```bash
# Export stream to file
nats stream backup TRIP_POINTS /backup/trip_points.tar.gz

# Restore from backup
nats stream restore TRIP_POINTS /backup/trip_points.tar.gz
```

## Appendix: Monitoring & Alerting

Critical during the trip - know immediately if something breaks.

### SigNoz Dashboard

Create a dashboard with:
- Upload rate (images/hour)
- Active WebSocket connections
- API response times (p50, p95)
- SeaweedFS storage usage
- Error rate by endpoint

### Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| API Down | No successful `/health` for 5 min | Critical |
| Upload Failures | Error rate > 10% for 5 min | Warning |
| Storage Full | SeaweedFS > 90% capacity | Warning |
| No Uploads | No new points for 2 hours during trip | Info |

Configure in SigNoz or via Alertmanager.

### Quick Health Check

```bash
# Run from anywhere with internet
curl -s https://api.trips.jomcgi.dev/health | jq .
# Expected: {"status": "healthy", "points": 1234, "connected_clients": 5}
```

---

## Appendix: Security Considerations

### Network Isolation
All services are internal-only (no direct internet exposure). Traffic flows:
1. Internet → Cloudflare Tunnel (TLS terminated)
2. Tunnel → nginx/api-server (internal HTTP)
3. Services → SeaweedFS/NATS (internal only)

### Container Security
All deployments should follow homelab security standards:

```yaml
securityContext:
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  runAsUser: 65532
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
```

### Upload Endpoint Authentication

The `/api/upload` endpoint requires a bearer token:

```yaml
# 1Password item: vaults/k8s-homelab/items/trips-api-key
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: trips-api-key
  namespace: trips
spec:
  itemPath: "vaults/k8s-homelab/items/trips-api-key"
```

The API server reads `TRIP_API_KEY` from the secret and validates uploads.

### Future Enhancements
- [ ] Add NetworkPolicy to restrict cross-namespace traffic to only required paths
- [ ] Add rate limiting to upload endpoint (prevent abuse)
- [ ] Enable SeaweedFS authentication for defense in depth