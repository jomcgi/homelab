# Bosun Dashboard — Design Document

**Status:** Draft
**Date:** 2026-03-10
**Context:** Visual companion for the `agent-orchestrator` service. Runs at `ops.jomcgi.dev`.
**Scope:** API audit + extension proposals + real-time design + TypeScript data model. Frontend implementation is out of scope here.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current API Inventory](#2-current-api-inventory)
3. [Gaps & Observations](#3-gaps--observations)
4. [Proposed API Extensions](#4-proposed-api-extensions)
5. [Real-Time Update Design](#5-real-time-update-design)
6. [TypeScript Data Model](#6-typescript-data-model)
7. [UI State Matrix](#7-ui-state-matrix)
8. [Job Data Patterns & UX Insights](#8-job-data-patterns--ux-insights)
9. [Deployment Notes](#9-deployment-notes)

---

## 1. Overview

The **Bosun Dashboard** is a lightweight Vite + React + shadcn/ui SPA that provides a visual companion for the `agent-orchestrator`. It is **not** a chat interface — Claude.ai remains the conversational layer. The dashboard surfaces:

- Active / recent / historical jobs at a glance
- Job output and logs without consuming Claude context window
- A quick-submit form for pre-defined or simple tasks
- Real-time status progression as jobs move through their lifecycle

**Non-goals:** auth (handled by Cloudflare Zero Trust), chat UI, prompt engineering.

**Architecture position:**

```
Claude.ai ──► agent-orchestrator MCP ──► orchestrator REST API ──► NATS JetStream
                                                                         │
Bosun Dashboard ────────────────────────────► orchestrator REST API ◄───┘
                                              (new SSE endpoint)
```

---

## 2. Current API Inventory

All endpoints are served on port `8080` (default). No authentication middleware exists at the application layer — auth is entirely delegated to Cloudflare Zero Trust.

### 2.1 Base URL

```
http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080
```

Externally (via Cloudflare Tunnel): `https://ops.jomcgi.dev` (proposed).

---

### `POST /jobs` — Submit Job

Creates a new job and enqueues it to NATS JetStream.

**Request body:**

```json
{
  "task": "string (required) — free-text description of what the agent should do",
  "profile": "string (optional) — 'ci-debug' | 'code-fix' | '' (default: all tools)",
  "max_retries": 2,
  "source": "string (optional) — 'api' | 'github' | 'cli' (default: 'api')",
  "tags": ["string", "..."]
}
```

**Validation:**
- `task` must be non-empty after trimming whitespace → `400 Bad Request`
- `profile` must be empty or one of `{"ci-debug", "code-fix"}` → `400 Bad Request`
- `max_retries` is clamped to `[0, 10]`; default is `2` (from `MAX_RETRIES` env)
- If NATS publish fails, the KV entry is rolled back and `500` is returned

**Response `202 Accepted`:**

```json
{
  "id": "01JNP4K7V8XQHZD3M6T5B2W0YC",
  "status": "PENDING",
  "created_at": "2026-03-10T03:46:00Z"
}
```

**Error responses:**
- `400` — `{"error": "task is required"}` or `{"error": "unknown profile: <value>"}`
- `500` — `{"error": "failed to store job"}` or `{"error": "failed to enqueue job"}`

**Notable:** The response intentionally omits the full `JobRecord` — only `id`, `status`, `created_at` are returned. The full record (including `profile`, `tags`, `source`, `max_retries`) must be fetched via `GET /jobs/{id}`.

---

### `GET /jobs` — List Jobs

Returns jobs sorted **newest-first** using reverse ULID lexicographic ordering (ULIDs are time-prefixed, so this is chronological).

**Query parameters:**

| Parameter | Type   | Default | Description |
|-----------|--------|---------|-------------|
| `status`  | string | —       | Comma-separated status filter: `PENDING,RUNNING,SUCCEEDED,FAILED,CANCELLED` (case-insensitive) |
| `limit`   | int    | 20      | Max results per page, capped at 100 |
| `offset`  | int    | 0       | Pagination offset |
| `tags`    | string | —       | Comma-separated tag filter — job must have **all** listed tags (AND semantics) |

**Response `200 OK`:**

```json
{
  "jobs": [
    {
      "id": "01JNP4K7V8XQHZD3M6T5B2W0YC",
      "task": "Fix the failing CI build on main",
      "profile": "ci-debug",
      "status": "RUNNING",
      "created_at": "2026-03-10T03:46:00Z",
      "updated_at": "2026-03-10T03:47:15Z",
      "max_retries": 2,
      "source": "api",
      "tags": ["ci", "urgent"],
      "github_issue": 0,
      "debug_mode": false,
      "failure_summary": "",
      "attempts": [
        {
          "number": 1,
          "sandbox_claim_name": "orch-01jnp4k7v8xqhzd3m6t5b2w0yc-1",
          "exit_code": null,
          "output": "Starting goose...\n[tool_use] bash: go test ./...\n",
          "truncated": false,
          "started_at": "2026-03-10T03:47:00Z",
          "finished_at": null
        }
      ]
    }
  ],
  "total": 47
}
```

**Performance note:** The current implementation fetches **all matching keys** from the NATS KV bucket, then slices for pagination in-memory. This is fine for low job volumes (KV TTL is 7 days) but will degrade at scale.

---

### `GET /jobs/{id}` — Get Job

Returns the complete `JobRecord` for a single job. Response shape is identical to a single element from `GET /jobs`.

**Path parameter:** `id` — 26-character ULID

**Response `200 OK`:** Full `JobRecord` (see above)

**Error:** `404 Not Found` — `{"error": "job not found"}`

---

### `POST /jobs/{id}/cancel` — Cancel Job

Cancels a PENDING or RUNNING job by setting its status to `CANCELLED` in the KV store. The consumer checks for cancellation before each execution phase (pre-claim-creation, pre-pod-ready, pre-dispatch) and periodically during execution via the `cancelFn` callback.

**Note:** Cancellation is **cooperative** — a running job may not stop immediately. The sandbox pod continues until the next `cancelFn` poll (every 30s output flush cycle) or until the job completes naturally.

**Response `200 OK`:** Full updated `JobRecord`

**Errors:**
- `404 Not Found` — job doesn't exist
- `409 Conflict` — `{"error": "job cannot be cancelled in status SUCCEEDED"}` (terminal states)

---

### `GET /jobs/{id}/output` — Get Latest Output

Returns the output from the **most recent attempt only**. Output is capped at **32KB** (stored in NATS KV). The full output (up to 50MB) lives in pod logs / SigNoz.

Output is flushed to the KV store every **30 seconds** while the job is running, so this endpoint provides near-real-time output for running jobs when polled.

**Response `200 OK`:**

```json
{
  "attempt": 2,
  "exit_code": null,
  "output": "Starting attempt 2...\nRunning go test...\n",
  "truncated": false
}
```

**Errors:**
- `404 Not Found` — job not found, or job has no attempts yet (status is `PENDING`)

---

### `GET /health` — Health Check

Used by Kubernetes liveness/readiness probes.

**Response `200 OK`:**
```json
{"status": "ok"}
```

**Response `503 Service Unavailable`:**
```json
{"status": "unhealthy", "error": "..."}
```

---

### MCP Tool Layer

The `agent_orchestrator_mcp` Python service wraps the REST API as MCP tools. Tools map 1:1 to REST endpoints with minor differences:

| MCP Tool | REST Endpoint | Differences |
|----------|--------------|-------------|
| `submit_job(task, profile?, max_retries?, source?)` | `POST /jobs` | No `tags` parameter exposed |
| `list_jobs(status?, limit?, offset?)` | `GET /jobs` | No `tags` parameter exposed |
| `get_job(job_id)` | `GET /jobs/{id}` | Identical |
| `cancel_job(job_id)` | `POST /jobs/{id}/cancel` | Identical |
| `get_job_output(job_id)` | `GET /jobs/{id}/output` | Identical |

**Gap:** The MCP `submit_job` and `list_jobs` tools do not expose the `tags` field, which is supported by the REST API.

---

### Runner API (Internal — not exposed externally)

The `agent-runner` process runs inside each sandbox pod on port `8081` and is accessed only by the orchestrator over in-cluster DNS. Documented here for completeness.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe — always `{"status":"ok"}` |
| `GET /status` | Runner state: `idle\|running\|done\|failed`, `pid`, `exit_code`, `started_at` |
| `GET /output?offset=<N>` | Incremental output fetch. Returns bytes from `offset` onward; sets `X-Output-Offset` header with new offset. |
| `POST /run` | Dispatch task to goose. Body: `{task, profile?, inactivity_timeout?}`. Returns `202` immediately; goose runs async. |

The orchestrator polls `GET /output` and `GET /status` every **30 seconds** while a job runs.

---

## 3. Gaps & Observations

### 3.1 Missing: Real-time push mechanism

The API is entirely **pull-based**. There is no SSE, WebSocket, or webhook. A dashboard must either:
- Poll `GET /jobs` on a timer (simple, but 30s+ latency)
- Poll `GET /jobs/{id}/output` to see live output (functional, but chatty)
- Use a new SSE endpoint on the orchestrator (recommended — see §5)

### 3.2 No aggregate statistics endpoint

There is no `GET /stats` or `GET /jobs/summary`. The dashboard must compute counts by fetching all jobs and grouping client-side, or the API needs a new stats endpoint.

### 3.3 Output only from latest attempt

`GET /jobs/{id}/output` returns only the **most recent** attempt's output. If a job retries twice, the first attempt's output is embedded in the full `JobRecord` (via the `attempts` array) but is not surfaced by the output endpoint.

The full `attempts[]` array is available via `GET /jobs/{id}`, but the dashboard needs to render per-attempt output from the job record directly.

### 3.4 Output is KV-capped at 32KB, but full output in SigNoz

The `Truncated` flag on an attempt tells you when the output was cut. Full output lives in pod logs / SigNoz. The dashboard can show the 32KB tail and offer a deep-link to SigNoz for the rest — but there is no first-party API for full output retrieval.

### 3.5 No source-filtering on list

`GET /jobs` supports `status` and `tags` filters but not `source`. You can't filter "show me only jobs submitted from the dashboard" without fetching all and filtering client-side.

### 3.6 Cancel is soft — no timeout signal

Cancellation sets a KV flag; the running goose process doesn't receive a SIGTERM. It will eventually be killed by the inactivity watchdog (`JOB_INACTIVITY_TIMEOUT`, default 10m) or the orchestrator's context timeout (`JOB_MAX_DURATION`, default 168h = 7 days). The dashboard should show a "cancelling…" indicator and not immediately show CANCELLED until the next poll confirms.

### 3.7 `SubmitResponse` is minimal

`POST /jobs` returns only `{id, status, created_at}`. The dashboard must immediately follow up with `GET /jobs/{id}` to get the full record for display, or accept the sparse response for the "just submitted" state.

### 3.8 No cursor-based pagination

Pagination uses `limit`/`offset`, which can drift as new jobs are created. For a live dashboard, a job added between page 1 and page 2 fetches will cause a duplicate or missed entry.

### 3.9 Tags field not in MCP

The MCP `submit_job` tool doesn't expose `tags`. The dashboard (which calls REST directly, not MCP) can use tags freely, but Claude can't tag jobs via MCP today.

---

## 4. Proposed API Extensions

These are the new endpoints and enhancements the dashboard needs. They should be implemented on the existing Go `api.go` file.

### 4.1 `GET /jobs/stream` — SSE Job Events *(Priority: High)*

The central real-time mechanism. See §5 for full rationale.

**Protocol:** Server-Sent Events (`text/event-stream`)

```
GET /jobs/stream
Accept: text/event-stream
```

The server subscribes to NATS KV watch on the `job-records` bucket, translates each `KeyValueEntry` update into an SSE event, and streams it to the client.

**Event types:**

```
event: job_updated
data: {"id":"01JNP4...", "status":"RUNNING", "updated_at":"..."}

event: job_created
data: {"id":"01JNP4...", "status":"PENDING", "created_at":"...", "task":"..."}

event: heartbeat
data: {}
```

`job_updated` sends the **full `JobRecord`** so the client can update its local cache without a separate fetch.

`heartbeat` is sent every 15s to keep the connection alive through Cloudflare's 100s timeout.

**Query parameters:**
- `status=RUNNING,PENDING` — only emit events for jobs matching these statuses
- `since=<ULID>` — only emit events for jobs created after this ID (for reconnect)

---

### 4.2 `GET /stats` — Aggregate Statistics *(Priority: Medium)*

Summary counts for the dashboard header / status chips.

**Response `200 OK`:**

```json
{
  "pending":   3,
  "running":   2,
  "succeeded": 141,
  "failed":    8,
  "cancelled": 4,
  "total":     158,
  "oldest_active_started_at": "2026-03-10T01:00:00Z"
}
```

Implementation: iterate all KV keys once and count by status — same scan the List operation already does.

---

### 4.3 `GET /jobs/{id}/attempts/{n}/output` — Per-Attempt Output *(Priority: Low)*

Allow fetching output for a specific attempt, not just the latest.

```json
{
  "attempt": 1,
  "exit_code": 1,
  "output": "...",
  "truncated": true
}
```

**Workaround for now:** The `attempts[]` array on the full `JobRecord` already contains `output` for every attempt — the dashboard can render all attempts from `GET /jobs/{id}` directly. This endpoint is a convenience for direct linking.

---

### 4.4 `GET /jobs` — Add `source` Filter *(Priority: Low)*

Add `?source=dashboard` parameter to the existing list endpoint. Useful for scoping the dashboard to jobs it submitted.

---

### 4.5 `POST /jobs/{id}/resubmit` — Resubmit a Failed Job *(Priority: Medium)*

Duplicate a FAILED or CANCELLED job as a new PENDING job, preserving `task`, `profile`, `tags`, `source`. Useful for one-click retry from the dashboard without re-entering the task.

**Response `202 Accepted`:** New `SubmitResponse` with the new job's ID.

---

### 4.6 CORS Headers *(Priority: High if dashboard is on separate origin)*

If the dashboard is served from `ops.jomcgi.dev` and the orchestrator is accessed via a different hostname (or via Cloudflare Tunnel), CORS headers will be needed. Today the orchestrator has no CORS middleware.

**Required headers:**
```
Access-Control-Allow-Origin: https://ops.jomcgi.dev
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

**Alternative:** Route the dashboard's API calls through the same origin using a Cloudflare Worker or nginx reverse proxy. This avoids CORS entirely.

---

## 5. Real-Time Update Design

### 5.1 Option Comparison

| Option | Mechanism | Pro | Con |
|--------|-----------|-----|-----|
| **A) Client polling** | Dashboard polls `GET /jobs` every 5–10s | Zero backend changes | Latency up to 10s; noisy; no mid-job output streaming |
| **B) SSE from orchestrator (NATS KV watch)** | Orchestrator watches NATS KV, pushes to SSE clients | Low latency (~1s); uses existing NATS infra; simple for client | Needs new endpoint; orchestrator must track SSE clients |
| **C) WebSocket bridge** | WS connection, client subscribes to topics | Bidirectional; flexible | More complex server + client; no native browser NATS client |
| **D) NATS WebSocket direct** | Browser connects to NATS via WS | No orchestrator changes | Exposes NATS externally; security concern; NATS WS must be configured |

### 5.2 Recommendation: Option B — SSE from orchestrator

**Rationale:**

1. **NATS KV Watch already exists**: The orchestrator already writes every state change to the `job-records` KV bucket. `kv.Watch()` / `kv.WatchAll()` gives a change stream with zero additional infrastructure.

2. **SSE is the right fit for this use case**: The dashboard only needs server→client events (job state changes, output updates). SSE is simpler than WebSocket for unidirectional push, natively supported by all modern browsers, and works through HTTP/2.

3. **Cloudflare compatible**: Cloudflare Tunnel supports SSE with proper `Content-Type: text/event-stream`. The 100s response timeout is handled by periodic heartbeat events.

4. **No new infrastructure**: Unlike exposing NATS externally, the SSE stream stays inside the orchestrator's existing HTTP server. No new services, no NATS WebSocket config.

5. **Graceful degradation**: If the SSE connection drops (CF timeout, restart), the dashboard can fall back to polling `GET /jobs` and reconnect with `?since=<last_seen_id>`.

### 5.3 Implementation Sketch

In `api.go`, add:

```go
// handleStream serves a Server-Sent Events stream of job state changes.
// It subscribes to the NATS KV watch and pushes each change as an SSE event.
func (a *API) handleStream(w http.ResponseWriter, r *http.Request) {
    flusher, ok := w.(http.Flusher)
    if !ok {
        a.writeError(w, http.StatusInternalServerError, "streaming not supported")
        return
    }
    w.Header().Set("Content-Type", "text/event-stream")
    w.Header().Set("Cache-Control", "no-cache")
    w.Header().Set("Connection", "keep-alive")
    w.Header().Set("X-Accel-Buffering", "no") // Disable nginx buffering

    watcher, err := a.kv.WatchAll(r.Context())
    if err != nil { ... }
    defer watcher.Stop()

    heartbeat := time.NewTicker(15 * time.Second)
    defer heartbeat.Stop()

    for {
        select {
        case <-r.Context().Done():
            return
        case <-heartbeat.C:
            fmt.Fprint(w, "event: heartbeat\ndata: {}\n\n")
            flusher.Flush()
        case entry, ok := <-watcher.Updates():
            if !ok { return }
            if entry == nil { continue }
            // Determine event type from operation
            eventType := "job_updated"
            if entry.Operation() == jetstream.KeyValuePut && entry.Revision() == 1 {
                eventType = "job_created"
            }
            fmt.Fprintf(w, "event: %s\ndata: %s\n\n", eventType, entry.Value())
            flusher.Flush()
        }
    }
}
```

This approach passes the raw KV entry value (which is already a JSON-encoded `JobRecord`) directly to the SSE event data — no additional serialization needed.

### 5.4 Client Reconnection Strategy

The browser `EventSource` API automatically reconnects. The dashboard should:

1. On connect: fetch `GET /jobs` to populate initial state
2. On SSE event: merge the received `JobRecord` into the client-side job map by ID
3. On disconnect (onerror): fall back to 5s polling until reconnect succeeds
4. On reconnect: use `Last-Event-ID` header (set by browser automatically) to request `?since=<id>` — requires the server to accept this

---

## 6. TypeScript Data Model

These types reflect the exact JSON shapes returned by the current API, plus proposed extensions.

```typescript
// ─── Core Types ──────────────────────────────────────────────────────────────

export type JobStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";

export type JobProfile = "ci-debug" | "code-fix" | "";

export type JobSource = "api" | "github" | "cli" | string;

export interface Attempt {
  /** 1-based attempt number */
  number: number;
  /** K8s SandboxClaim name: "orch-<lowercase-id>-<attempt>" */
  sandbox_claim_name: string;
  /** null while running */
  exit_code: number | null;
  /** Last 32KB of stdout+stderr. Empty string until first 30s flush. */
  output: string;
  /** true if output was truncated to 32KB */
  truncated: boolean;
  started_at: string; // ISO 8601 UTC
  /** null while running */
  finished_at: string | null;
}

export interface JobRecord {
  /** 26-character ULID — lexicographically sortable by creation time */
  id: string;
  task: string;
  profile: JobProfile;
  status: JobStatus;
  created_at: string;  // ISO 8601 UTC
  updated_at: string;  // ISO 8601 UTC
  max_retries: number;
  source: JobSource;
  tags: string[];       // may be null in older records — treat null as []

  // Populated when submitted via GitHub webhook integration
  github_issue: number;  // 0 means not set
  debug_mode: boolean;
  /** Populated by future failure analysis feature */
  failure_summary: string;

  attempts: Attempt[];
}

// ─── API Request/Response Types ──────────────────────────────────────────────

export interface SubmitRequest {
  task: string;
  profile?: JobProfile;
  max_retries?: number;
  source?: JobSource;
  tags?: string[];
}

export interface SubmitResponse {
  id: string;
  status: "PENDING";
  created_at: string;
}

export interface ListResponse {
  jobs: JobRecord[];
  /** Total matching jobs (before pagination) */
  total: number;
}

export interface OutputResponse {
  attempt: number;
  exit_code: number | null;
  output: string;
  truncated: boolean;
}

export interface HealthResponse {
  status: "ok" | "unhealthy";
  error?: string;
}

export interface ErrorResponse {
  error: string;
}

// ─── Proposed: Stats Response ─────────────────────────────────────────────────

export interface StatsResponse {
  pending: number;
  running: number;
  succeeded: number;
  failed: number;
  cancelled: number;
  total: number;
  /** ISO 8601 — oldest currently-active job's started_at, null if none active */
  oldest_active_started_at: string | null;
}

// ─── SSE Event Types ─────────────────────────────────────────────────────────

export type SSEEventType = "job_created" | "job_updated" | "heartbeat";

export interface SSEEvent<T = JobRecord> {
  type: SSEEventType;
  data: T;
}

// ─── Client-Side State ────────────────────────────────────────────────────────

/** The dashboard maintains a normalized job map, keyed by ID */
export type JobMap = Record<string, JobRecord>;

export interface DashboardState {
  jobs: JobMap;
  total: number;
  isLoading: boolean;
  isConnected: boolean;  // SSE connection live
  error: string | null;
  filters: {
    status: JobStatus[];
    tags: string[];
    source: JobSource | null;
  };
  pagination: {
    limit: number;
    offset: number;
  };
}

// ─── Derived Helpers ──────────────────────────────────────────────────────────

/** Compute wall-clock duration for display */
export function jobDuration(job: JobRecord): number | null {
  const lastAttempt = job.attempts[job.attempts.length - 1];
  if (!lastAttempt) return null;
  const start = new Date(lastAttempt.started_at).getTime();
  const end = lastAttempt.finished_at
    ? new Date(lastAttempt.finished_at).getTime()
    : Date.now();
  return end - start; // milliseconds
}

/** true if job is in a terminal state */
export const isTerminal = (status: JobStatus): boolean =>
  status === "SUCCEEDED" || status === "FAILED" || status === "CANCELLED";

/** true if job is actively executing */
export const isActive = (status: JobStatus): boolean =>
  status === "PENDING" || status === "RUNNING";
```

---

## 7. UI State Matrix

What the frontend must render for each combination of job status and UI context.

### 7.1 Job List Row States

| Job Status | Status Chip | Progress | Action |
|------------|-------------|----------|--------|
| `PENDING` | 🟡 Pending | Spinner | Cancel |
| `RUNNING` | 🔵 Running | Animated pulse | Cancel |
| `SUCCEEDED` | 🟢 Succeeded | — | Resubmit |
| `FAILED` | 🔴 Failed | — | Resubmit |
| `CANCELLED` | ⚫ Cancelled | — | Resubmit |

### 7.2 Job Detail Panel States

| Condition | Output Area | Notes |
|-----------|-------------|-------|
| `PENDING`, no attempts | "Waiting for sandbox allocation…" | Poll `GET /jobs/{id}` until attempts > 0 |
| `RUNNING`, attempts[0].output == "" | "Starting goose… (first output in ~30s)" | Output is flushed every 30s |
| `RUNNING`, attempts[n].output != "" | Live output (auto-scroll, monospace) | Refresh via SSE or poll `/output` |
| `RUNNING`, attempts[n].truncated | Output + "⚠ Output truncated to 32KB — full logs in SigNoz" | Show SigNoz deep-link |
| `SUCCEEDED` / `FAILED` | Final output (static) | Show exit code |
| `CANCELLED` | Output up to cancellation point | May show "[orchestrator restarted - execution interrupted]" |
| Multi-attempt job | Accordion per attempt | Each attempt has its own output, exit code, duration |

### 7.3 Global States

| State | Render |
|-------|--------|
| Initial load | Skeleton list (3–5 rows), spinner in header |
| Empty (no jobs) | "No jobs yet — submit one to get started" |
| SSE connected | Green dot in header |
| SSE disconnected (fallback polling) | Yellow dot + "Reconnecting…" |
| API error | Toast notification with error message |
| Submitting new job | Submit button disabled + spinner |
| Cancelling job | Cancel button shows "Cancelling…" + disabled |

### 7.4 Output Streaming State Machine

```
         submit
            │
            ▼
      ┌──────────┐       sandbox          ┌──────────┐
      │ PENDING  │──── allocated ────────►│ RUNNING  │
      └──────────┘                        └────┬─────┘
            │                                  │
            │ cancel                    30s flush cycle
            │                                  │
            ▼                                  ▼
      ┌──────────┐                     output in KV store
      │CANCELLED │                             │
      └──────────┘                             │
                              ┌────────────────┤
                              │                │
                        exit_code=0       exit_code!=0
                              │                │
                              ▼                ▼
                         SUCCEEDED          FAILED
                                              │
                                    retries remaining?
                                       │          │
                                      yes         no
                                       │          │
                                       ▼          ▼
                                   PENDING     FAILED (terminal)
                                  (attempt+1)
```

### 7.5 Submit Form States

| State | Behavior |
|-------|----------|
| Empty task | Submit disabled |
| Valid task | Submit enabled |
| Submitting | Button spinner, form disabled |
| Success | Brief success toast + redirect to new job detail |
| Error | Error toast, form re-enabled |

---

## 8. Job Data Patterns & UX Insights

These observations are based on the code and config rather than live data, but they inform dashboard design decisions.

### 8.1 Job IDs Are ULIDs

26-character Crockford Base32 ULIDs: `01JNP4K7V8XQHZD3M6T5B2W0YC`

- **Time-sortable**: Lexicographic sort = chronological sort. The KV store uses reverse ULID sort for newest-first.
- **Copyable prefix**: First 10 chars encode the timestamp. Could show abbreviated ID in the list view (first 8 chars is sufficient for visual differentiation).
- **Deep links**: `/jobs/01JNP4K7V8XQHZD3M6T5B2W0YC` works as a stable permalink.

### 8.2 Job Lifecycle Timing

From the config defaults:

| Phase | Duration |
|-------|----------|
| Sandbox allocation (SandboxClaim → pod ready) | ~2 min timeout, typically 5–30s from warm pool |
| Output first appears | ~30s after `RUNNING` (first flush interval) |
| Inactivity kill | 10 minutes of no output |
| Max job duration | 168 hours (7 days) |
| KV record TTL | 7 days |
| Output flush interval | 30 seconds |

**Implication:** A job that just turned `RUNNING` will show empty output for up to 30 seconds — the dashboard should show a "waiting for first output…" state rather than an empty box.

### 8.3 Output Size

- **KV store cap**: 32KB (last 32KB of output)
- **In-memory runner cap**: 50MB
- **Pod logs**: full output via SigNoz

Typical goose output for a CI-debug job that involves running tests and reading files: likely 10–100KB raw, meaning truncation is common for longer jobs. The `truncated` flag should be prominently displayed.

### 8.4 Retry Pattern

The default `max_retries=2` means a job can make up to **3 total attempts** (initial + 2 retries). On retry, the task prompt is automatically augmented with the previous attempt's last 2000 chars of output and exit code. The `attempts[]` array shows the full history.

A job currently re-queued for retry will be in `PENDING` status with `len(attempts) > 0`. The dashboard should distinguish "waiting for first execution" from "waiting for retry N" — check `len(job.attempts)`.

### 8.5 Concurrency

`maxConcurrent=5` (default, configurable). There can be up to 5 simultaneously `RUNNING` jobs. The dashboard stats bar is most useful if it prominently shows `running` count vs. the concurrent limit.

### 8.6 Job Sources

Currently active sources:
- `"api"` — submitted via REST API directly (default)
- `"github"` — submitted via GitHub webhook/issue integration (future)
- `"cli"` — submitted via CLI tooling

The dashboard itself should set `source: "dashboard"` on jobs it submits, making them distinguishable in logs and the list view.

### 8.7 Profiles

Two profiles exist:
- `"ci-debug"` — uses `/home/goose-agent/recipes/ci-debug.yaml`. For debugging CI failures.
- `"code-fix"` — uses `/home/goose-agent/recipes/code-fix.yaml`. For applying code fixes.
- Empty — default goose config with all tools enabled.

The submit form should offer these as a dropdown with descriptions.

### 8.8 Failure Modes Visible in Output

The dashboard should recognize these special output strings and surface them prominently:

| String in output | Meaning |
|-----------------|---------|
| `--- killed: inactivity timeout (10m0s) ---` | Job killed by runner watchdog |
| `[orchestrator restarted - execution interrupted]` | Pod/orchestrator restart mid-job |
| `failed to start goose: ...` | Container issue (wrong image, missing binary) |

### 8.9 Tags Are UX-Friendly Filters

Tags are free-form strings with AND semantics on filter. Good candidates for the dashboard's filter bar. Existing usage (if any) can be discovered from the list endpoint.

---

## 9. Deployment Notes

### 9.1 Service URL

The orchestrator is deployed at:
```
agent-orchestrator.agent-orchestrator.svc.cluster.local:8080
```

For the dashboard (external, via Cloudflare Tunnel), the API should be exposed at a separate path or subdomain, e.g.:
- `https://ops.jomcgi.dev/api/*` (proxied to orchestrator) — simplest, avoids CORS
- `https://orchestrator.jomcgi.dev/*` — separate hostname, needs CORS headers

### 9.2 Website Deployment Pattern

Based on existing sites (ships.jomcgi.dev, hikes.jomcgi.dev), the repo pattern is:
- `websites/ops.jomcgi.dev/` — Vite + React source
- `websites/ops.jomcgi.dev/package.json` — uses `react`, `react-dom`, `vite`, `shadcn/ui`
- `websites/ops.jomcgi.dev/BUILD` — Bazel build target
- Static build deployed via `bazel run //websites:push_all_pages` in CI

Note: existing sites use plain JavaScript (not TypeScript) per repo convention. The TypeScript types in §6 would be used as JSDoc type annotations or `.d.ts` files rather than `.ts` source files, unless the repo convention is relaxed for this app.

### 9.3 NATS KV Watch for SSE

The `kv.WatchAll()` NATS API returns an `<-chan KeyValueEntry` channel. Each entry includes:
- `Key()` — job ID
- `Value()` — JSON-encoded `JobRecord`
- `Operation()` — `KeyValuePut` or `KeyValueDelete`
- `Revision()` — monotonic revision counter (revision 1 = first creation)

This channel naturally provides the event stream needed for SSE without any polling.

### 9.4 Recommended Implementation Order

1. **CORS middleware** (if needed) — 1 hour, unblocks all browser API calls
2. **`GET /jobs/stream` SSE endpoint** — 1 day, enables live dashboard
3. **`GET /stats` endpoint** — 2 hours, enables header stats bar
4. **`POST /jobs/{id}/resubmit`** — 2 hours, enables dashboard retry UX
5. **Frontend dashboard** — separate task

---

## Appendix: Example Full Job Record (RUNNING, 1 attempt in progress)

```json
{
  "id": "01JNP4K7V8XQHZD3M6T5B2W0YC",
  "task": "Debug the failing CI build. Run the tests, identify the root cause, and fix it.",
  "profile": "ci-debug",
  "status": "RUNNING",
  "created_at": "2026-03-10T03:46:00.123Z",
  "updated_at": "2026-03-10T03:47:32.456Z",
  "max_retries": 2,
  "source": "api",
  "tags": ["ci", "main-branch"],
  "github_issue": 0,
  "debug_mode": false,
  "failure_summary": "",
  "attempts": [
    {
      "number": 1,
      "sandbox_claim_name": "orch-01jnp4k7v8xqhzd3m6t5b2w0yc-1",
      "exit_code": null,
      "output": "Starting goose...\n[tool_use] bash\n$ go test ./...\nok  \tgithub.com/jomcgi/homelab/services/foo\t0.342s\nFAIL\tgithub.com/jomcgi/homelab/services/bar\n",
      "truncated": false,
      "started_at": "2026-03-10T03:47:00.000Z",
      "finished_at": null
    }
  ]
}
```

## Appendix: Example Full Job Record (FAILED after 2 attempts)

```json
{
  "id": "01JNP3AAAAAAAAAAAAAAAAAAAAA",
  "task": "Fix the flaky test in services/bar",
  "profile": "code-fix",
  "status": "FAILED",
  "created_at": "2026-03-10T02:00:00Z",
  "updated_at": "2026-03-10T02:45:12Z",
  "max_retries": 2,
  "source": "api",
  "tags": [],
  "github_issue": 0,
  "debug_mode": false,
  "failure_summary": "",
  "attempts": [
    {
      "number": 1,
      "sandbox_claim_name": "orch-01jnp3aaaaaaaaaaaaaaaaaaaaa-1",
      "exit_code": 1,
      "output": "...first attempt output (last 32KB)...",
      "truncated": true,
      "started_at": "2026-03-10T02:05:00Z",
      "finished_at": "2026-03-10T02:20:00Z"
    },
    {
      "number": 2,
      "sandbox_claim_name": "orch-01jnp3aaaaaaaaaaaaaaaaaaaaa-2",
      "exit_code": 1,
      "output": "This is retry attempt 2. The previous attempt (attempt 1) failed...\n...second attempt output...",
      "truncated": false,
      "started_at": "2026-03-10T02:25:00Z",
      "finished_at": "2026-03-10T02:45:00Z"
    }
  ]
}
```
