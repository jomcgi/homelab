# Migration: Local Script to API-Based Upload

> **Status:** ⚠️ PLANNED - Not yet implemented. Architecture documented for future work.

## Current Architecture

```
Local Machine                         Kubernetes (port-forwarded)
┌────────────────────┐               ┌──────────────┐
│ publish-trip-images│               │              │
│ - Scan images      │──S3 upload───>│ SeaweedFS    │
│ - Extract EXIF     │               └──────────────┘
│ - Upload to S3     │               ┌──────────────┐
│ - Publish to NATS  │──publish─────>│ NATS         │
│ - Track in SQLite  │               └──────────────┘
└────────────────────┘
```

**Pain points:**

- Requires SSH + port-forwarding to cluster
- Local dependencies on NATS and S3 clients
- Slow iteration when testing

## Target Architecture

```
Local Machine                    Cloudflare           Kubernetes
┌──────────────┐                ┌──────────┐         ┌─────────────────┐
│ Thin Client  │───POST────────>│ Access   │────────>│ trips-api       │
│ - Scan dir   │  /api/images   │ (Zero    │         │ - Extract EXIF  │
│ - POST image │                │  Trust)  │         │ - Upload to S3  │
└──────────────┘<───200/201─────└──────────┘<────────│ - Publish NATS  │
                                                     └─────────────────┘
```

**Benefits:**

- No port-forwarding or SSH required
- Zero Trust auth via Cloudflare Access
- All processing logic server-side
- Idempotent uploads (hash-based dedup)

## API Design

### `POST /api/images`

**Headers:**

- `CF-Access-Client-Id` + `CF-Access-Client-Secret` (service token from Cloudflare Access)
- `X-Image-Source`: `gopro` | `camera` | `phone` (optional, default: `gopro`)

**Body:** `multipart/form-data` with image file

**Responses:**
| Status | Meaning | Body |
|--------|---------|------|
| 201 | Uploaded (new or replaced) | `{ id, lat, lng, timestamp, image, uploaded: true }` |
| 200 | Unchanged (same content hash) | `{ id, lat, lng, timestamp, image, uploaded: false }` |
| 401 | Unauthorized | `{ detail: "..." }` |
| 400 | Bad request (not an image) | `{ detail: "..." }` |

### Idempotency

The same image always produces the same S3 key via `uuid5(source:timestamp:filename)`:

- **Same key + same hash** → 200, skip upload
- **Same key + different hash** → 201, overwrite (handles rotation/edits)
- **New key** → 201, upload

## Migration Timeline

```mermaid
gantt
    title API Migration Phases
    dateFormat YYYY-MM-DD
    section Phase 1
    Add EXIF extraction to trips-api        :p1, 2026-02-15, 3d
    Add S3 upload logic                     :p2, after p1, 2d
    Add POST /api/images endpoint           :p3, after p2, 2d
    Test with curl                          :p4, after p3, 1d
    section Phase 2
    Setup Cloudflare Access                 :p5, after p4, 1d
    Create service token                    :p6, after p5, 1d
    Test auth flow                          :p7, after p6, 1d
    section Phase 3
    Simplify local script                   :p8, after p7, 3d
    Test end-to-end upload                  :p9, after p8, 2d
    section Phase 4
    Remove GHA workflows                    :p10, after p9, 1d
    Clean up dependencies                   :p11, after p10, 1d
```

**Estimated Duration:** 3-4 weeks (assumes 1-2 hour sessions per phase)

---

## Migration Checklist

### Phase 1: Server-Side (trips-api)

- [ ] Add dependencies to `services/trips_api/BUILD`: `pillow`, `boto3`
- [ ] Add EXIF extraction functions (port from local script)
- [ ] Add S3 client and upload logic (port from local script)
- [ ] Add `POST /api/images` endpoint with:
  - [ ] Multipart file handling
  - [ ] EXIF extraction (lat, lng, timestamp)
  - [ ] Deterministic key generation
  - [ ] S3 upload with hash-based dedup
  - [ ] NATS publish
- [ ] Add environment variables: `SEAWEEDFS_ENDPOINT`, `SEAWEEDFS_ACCESS_KEY`, `SEAWEEDFS_SECRET_KEY`
- [ ] Update Helm values with new env vars
- [ ] Test endpoint locally with curl

### Phase 2: Cloudflare Access

- [ ] Create Cloudflare Access application for `trips-api.jomcgi.dev/api/images`
- [ ] Create service token for local client
- [ ] Test auth flow with curl

### Phase 3: Client-Side (publish-trip-images)

- [ ] Simplify script to thin client:
  - [ ] Remove NATS client code
  - [ ] Remove S3 client code
  - [ ] Remove EXIF extraction (server handles it)
  - [ ] Add `httpx` or `requests` for HTTP uploads
  - [ ] Add Cloudflare Access token handling
- [ ] Keep SQLite queue for:
  - [ ] Tracking upload progress
  - [ ] Retry logic on failures
  - [ ] Resumable uploads
- [ ] Update environment variables: `TRIPS_API_URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`

### Phase 4: Cleanup

- [ ] Remove unused dependencies from local script
- [ ] Update this README with new usage instructions
- [ ] Test full flow: scan → upload → verify on map

## Environment Variables

### Server (trips-api)

```bash
SEAWEEDFS_ENDPOINT=http://seaweedfs-s3:8333
SEAWEEDFS_BUCKET=trips
# If auth enabled:
SEAWEEDFS_ACCESS_KEY=...
SEAWEEDFS_SECRET_KEY=...
```

### Client (local)

```bash
TRIPS_API_URL=https://trips-api.jomcgi.dev
CF_ACCESS_CLIENT_ID=<from cloudflare>
CF_ACCESS_CLIENT_SECRET=<from cloudflare>
```

## Testing

```bash
# Test server endpoint (after port-forward for initial dev)
curl -X POST http://localhost:8000/api/images \
  -H "X-Image-Source: gopro" \
  -F "file=@/path/to/image.jpg"

# Test with Cloudflare Access (production)
curl -X POST https://trips-api.jomcgi.dev/api/images \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "X-Image-Source: gopro" \
  -F "file=@/path/to/image.jpg"
```
