# Backend-Driven Job Summarization

## Problem

LLM-generated summaries for pipeline jobs are currently triggered by the UI. Every browser
tab polls `GET /jobs` every 5 seconds, and for each pipeline job without a cached summary,
fires `POST /jobs/{id}/summarize`. Summaries live only in React state — every page refresh
re-triggers all LLM calls. This wastes inference resources and adds latency to page loads.

## Solution

Move summarization into the backend consumer loop. Each job gets summarized a fixed number
of times based on lifecycle events, regardless of how many browsers are open. Summaries are
persisted in the `JobRecord` (NATS KV) and served to the UI via the existing `GET /jobs`
endpoint.

## Approach: Inline in consumer.go

Summarization calls are added directly into the existing consumer `processJob` flow.
The consumer already manages the full job lifecycle and runs a 30s ticker for progress
flushing — LLM calls (~1-3s) are negligible relative to the 30s poll cycle.

Alternatives considered:

- **Separate goroutine per job** — adds coordination complexity and KV write races for
  marginal benefit.
- **Background scan loop (like reconciler)** — loses event-driven precision; either polls
  too often or produces stale summaries.

## Data Model

Add `Title` and `Summary` fields to `JobRecord`:

```go
type JobRecord struct {
    // ... existing fields ...
    Title   string `json:"title,omitempty"`
    Summary string `json:"summary,omitempty"`
}
```

Remove `SummarizeResponse` from `model.go` — no longer needed.

## Summarizer Component

New `summarizer.go` file with a `Summarizer` struct:

```go
type Summarizer struct {
    inferenceURL string
    model        string
    logger       *slog.Logger
}

func (s *Summarizer) SummarizeTask(ctx context.Context, task string) (title string, err error)
func (s *Summarizer) SummarizePlan(ctx context.Context, task string, plan []PlanStep) (title, summary string, err error)
```

- **`SummarizeTask`** — generates a clean title from the raw task text (no plan required).
- **`SummarizePlan`** — generates title + summary from task + plan step statuses.
- Both are nil-safe: if `Summarizer` is nil or `inferenceURL` is empty, calls are no-ops.
- Errors are logged and swallowed — summarization failures never block job execution.

Extracts the existing LLM call logic from `handleSummarize` (OpenAI-compatible
`/v1/chat/completions` with JSON schema enforcement).

## Trigger Points

Four triggers in `processJob`:

### 1. Job submitted — title from task

After setting status to `RUNNING` and storing the job, call `SummarizeTask(job.Task)`.
Updates `job.Title` in KV. Gives users a clean title within seconds of submission.

### 2. Plan available — first plan summary

During the 30s ticker loop, when `planBuf.Get()` returns a non-empty plan for the first
time, call `SummarizePlan`. Updates both `job.Title` and `job.Summary`. Fires once
(tracked by a boolean flag).

### 3. Periodic update — every 5 minutes

Tracked via a `lastSummarizedAt time.Time` variable checked during the 30s ticker loop.
When 5 minutes have elapsed and a plan exists, call `SummarizePlan` with current step
statuses. Captures progress like "3 of 5 steps complete."

### 4. Terminal state — final summary

After the job reaches `SUCCEEDED`/`FAILED`, before the final `store.Put`, call
`SummarizePlan` one last time with the final plan state. Produces the definitive summary.

```
processJob flow:
  store job as RUNNING
  -> Trigger 1: SummarizeTask(job.Task) -> job.Title

  start sandbox goroutine
  loop:
    every 30s: flushProgress (existing)
    every 30s: check if plan appeared -> Trigger 2: SummarizePlan (once)
    every 5m:  -> Trigger 3: SummarizePlan (if plan exists)
    sandbox done: break

  set SUCCEEDED/FAILED
  -> Trigger 4: SummarizePlan (final)
  store job
```

## API & UI Cleanup

### Backend

- Delete `handleSummarize` from `api.go`
- Remove route `POST /jobs/{id}/summarize` from `RegisterRoutes`
- Remove `inferenceURL` from the `API` struct (moves to `Summarizer`)
- `main.go` constructs `Summarizer` from `config.inferenceUrl`, passes to `NewConsumer`

### UI

- Delete `summarizeJob` from `api.js`
- Remove `summaries` state Map, `pendingSummaries` ref, and the summary-fetching `useEffect`
- Read `job.title` and `job.summary` directly from the job record instead

### MCP Server

- No changes — `summarize_job` was never exposed as an MCP tool
- `get_job` and `list_jobs` automatically include the new fields

## Error Handling

- All summarizer calls are fire-and-forget: log on failure, never block the job
- If the inference service is down, jobs run normally with empty title/summary
- Each successful summary overwrites the previous one — no append semantics
- 30-second timeout on each LLM call (matches existing behavior)
