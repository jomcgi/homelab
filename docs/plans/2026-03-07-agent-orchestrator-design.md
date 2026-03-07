# Agent Orchestrator Service — Design

**Date:** 2026-03-07
**Status:** Approved
**ADR:** architecture/decisions/agents/ (agent-run orchestration)

## Summary

Convert the `agent-run` CLI into a long-running service that orchestrates Goose agent tasks via a REST API, backed by NATS JetStream for queuing and NATS KV for state persistence.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| State store | NATS JetStream + KV | Leverages existing infra, durable across restarts |
| API style | REST with query params | Simple, curl-friendly, easy to wrap in MCP tools |
| Retry scope | Basic retries with context inheritance | Reserve DLQ/GH issue fields for later |
| Code location | `services/agent-orchestrator/` | Proper service, not a tool |
| Auth | None (ClusterIP only) | MVP; add Cloudflare Access when exposed externally |
| MCP exposure | Design API for MCP consumption | REST-first; MCP wrapping is a separate concern |
| Architecture | Monolithic (single binary) | HTTP + consumer + NATS in one process |

## Data Model

```go
type JobStatus string

const (
    JobPending   JobStatus = "PENDING"
    JobRunning   JobStatus = "RUNNING"
    JobSucceeded JobStatus = "SUCCEEDED"
    JobFailed    JobStatus = "FAILED"
    JobCancelled JobStatus = "CANCELLED"
)

type JobRecord struct {
    ID             string    `json:"id"`               // ULID
    Task           string    `json:"task"`
    Status         JobStatus `json:"status"`
    CreatedAt      time.Time `json:"created_at"`
    UpdatedAt      time.Time `json:"updated_at"`
    MaxRetries     int       `json:"max_retries"`
    Source         string    `json:"source"`            // "api", "github", "cli"

    // Reserved for webhook/DLQ integration
    GithubIssue    int       `json:"github_issue,omitempty"`
    DebugMode      bool      `json:"debug_mode,omitempty"`
    FailureSummary string    `json:"failure_summary,omitempty"`

    Attempts       []Attempt `json:"attempts"`
}

type Attempt struct {
    Number           int        `json:"number"`
    SandboxClaimName string     `json:"sandbox_claim_name"`
    ExitCode         *int       `json:"exit_code,omitempty"`
    Output           string     `json:"output"`
    StartedAt        time.Time  `json:"started_at"`
    FinishedAt       *time.Time `json:"finished_at,omitempty"`
}
```

ULIDs provide lexicographic sort by creation time — free chronological ordering in NATS KV key listings.

## REST API

| Method | Path | Purpose | MCP use case |
|--------|------|---------|--------------|
| POST | `/jobs` | Submit a job | "run this task" |
| GET | `/jobs` | List/filter jobs | "what's running?", "show pending" |
| GET | `/jobs/:id` | Job detail + attempts | "show me job X" |
| POST | `/jobs/:id/cancel` | Cancel job | "stop that job" |
| GET | `/jobs/:id/output` | Latest attempt output | "what did it produce?" |
| GET | `/health` | Liveness/readiness | k8s probes |

### Query parameters for GET /jobs

- `status` — comma-separated filter (e.g. `running,pending`)
- `limit` — pagination (default 20)
- `offset` — pagination offset

### Submit request/response

```json
// POST /jobs → 202 Accepted
// Request
{ "task": "Fix the flaky test in services/grimoire/api", "max_retries": 2 }

// Response
{ "id": "01JQXK...", "status": "PENDING", "created_at": "2026-03-07T..." }
```

## Architecture

```
┌─────────────────────────────────────────────┐
│          agent-orchestrator                  │
│                                             │
│  ┌──────────┐    ┌─────────────────────┐    │
│  │ HTTP API │    │   NATS JetStream     │    │
│  │          │───▶│   Stream: agent.jobs │    │
│  │          │    └──────────┬──────────┘    │
│  │          │               │               │
│  │          │ read    pull (max-in-flight=1) │
│  │          │               ▼               │
│  │          │    ┌─────────────────────┐    │
│  └────┬─────┘    │    Consumer          │    │
│       │          │ 1. Update KV→RUNNING │    │
│       ▼          │ 2. Create SandboxClaim│   │
│  ┌──────────┐    │ 3. Wait for pod      │    │
│  │ NATS KV  │◀───│ 4. Exec goose run    │    │
│  │ Bucket:  │    │ 5. Capture output    │    │
│  │ job-     │    │ 6. Update KV→result  │    │
│  │ records  │    │ 7. Ack/retry message │    │
│  └──────────┘    │ 8. Cleanup sandbox   │    │
│                  └─────────────────────┘    │
└─────────────────────────────────────────────┘
```

### Submit flow

1. HTTP handler validates request, generates ULID
2. Writes initial JobRecord (PENDING) to NATS KV
3. Publishes job ID to JetStream stream `agent.jobs`
4. Returns 202 Accepted

### Consumer flow

1. Pulls job ID from stream (max-in-flight=1 serializes execution)
2. Reads JobRecord from KV, sets status→RUNNING
3. Creates SandboxClaim in `goose-sandboxes` namespace
4. Polls for pod readiness
5. Execs `goose run --text <task>`, captures output
6. Updates KV with exit code, output, final status
7. On failure with retries remaining: NAKs message for re-delivery
8. Cleans up SandboxClaim

### Cancel flow

1. HTTP handler sets status→CANCELLED in KV
2. Consumer checks status before each lifecycle phase
3. If CANCELLED, cleans up sandbox and acks message

### Retry with context inheritance

Subsequent attempts receive an enriched prompt:

```
Previous attempt failed (exit code {code}).
Output summary: {truncated previous output}

Original task: {task}

Try a different approach.
```

## Deployment

**Chart:** `charts/agent-orchestrator/`
- Deployment (1 replica)
- Service (ClusterIP:8080)
- ServiceAccount + ClusterRole (SandboxClaim CRUD, pod exec)
- ConfigMap

**RBAC:**
- `extensions.agents.x-k8s.io/sandboxclaims` — create, get, list, watch, delete
- `agents.x-k8s.io/sandboxes` — get, list, watch
- `core/pods` — get, list, watch
- `core/pods/exec` — create

**Environment:**
- `NATS_URL` — nats://nats.nats.svc.cluster.local:4222
- `SANDBOX_NAMESPACE` — goose-sandboxes
- `SANDBOX_TEMPLATE` — goose-agent
- `MAX_RETRIES` — 2 (default)
- `HTTP_PORT` — 8080

**NATS resources** (self-provisioned on startup):
- Stream: `agent.jobs` (WorkQueue retention, max 1000 msgs)
- KV Bucket: `job-records` (TTL 7 days)

**Overlay:** `overlays/prod/agent-orchestrator/`

**Image:** apko + rules_apko, static Go binary, uid 65532

## Out of Scope (Future)

- GitHub webhook handler (POST /webhooks/github)
- DLQ → GitHub issue creation → debug re-queue
- failure_summary synthesis via Claude API
- Cloudflare Access authentication
- MCP server wrapping
- SSE/streaming output
- Refactor agent-run CLI to thin API client
