# Pipeline Execution Engine Design

## Goal

Transform the pipeline composer from a UI-only concept into a real execution engine where each pipeline step runs as an independent job, chained via a linked list with condition-based progression.

## Architecture

Pipeline steps are peer jobs sharing a `pipeline_id`. The first step dispatches immediately; subsequent steps are BLOCKED until their predecessor completes and their condition is evaluated. The orchestrator's job completion handler drives the chain forward. An LLM call enriches each job with a human-readable title and summary at creation time.

## Data Model

New fields on `JobRecord`:

```go
PipelineID    string `json:"pipeline_id,omitempty"`    // shared ULID grouping linked jobs
StepIndex     int    `json:"step_index,omitempty"`     // 0-based position in pipeline
StepCondition string `json:"step_condition,omitempty"` // "always" | "on success" | "on failure"
Title         string `json:"title,omitempty"`          // LLM-generated short title
Summary       string `json:"summary,omitempty"`        // LLM-generated 1-2 sentence description
```

New statuses:

- `BLOCKED` — waiting for predecessor to complete
- `SKIPPED` — predecessor completed but condition was not met

State machine additions:

```
BLOCKED → (predecessor completes, condition met) → PENDING → RUNNING → ...
BLOCKED → (predecessor completes, condition not met) → SKIPPED
BLOCKED → (cancel forward) → CANCELLED
```

## Pipeline Submission

New endpoint: `POST /pipeline`

Request:

```json
{
  "steps": [
    {
      "agent": "ci-debug",
      "task": "Debug the CI failure",
      "condition": "always"
    },
    { "agent": "code-fix", "task": "Fix the issue", "condition": "on success" }
  ]
}
```

Flow:

1. Generate `pipeline_id` (ULID)
2. Call llama-cpp synchronously to generate title + summary for each step (single batched prompt)
3. Create N `JobRecord`s sharing `pipeline_id`:
   - Step 0: status=PENDING, published to `agent.jobs` NATS subject
   - Steps 1-N: status=BLOCKED, stored in KV only (not published)
4. Return all job IDs + pipeline_id

The existing `POST /jobs` endpoint also gets LLM enrichment (title + summary) for single jobs.

## Step Chaining

In `consumer.go` `processJob()`, after a job reaches terminal state:

1. If `job.PipelineID == ""` → done (not a pipeline job)
2. Query store for next step: same `pipeline_id`, `step_index == job.StepIndex + 1`
3. If no next step → pipeline complete
4. Evaluate condition against predecessor status:
   - `"always"` → unblock
   - `"on success"` → unblock only if predecessor SUCCEEDED
   - `"on failure"` → unblock only if predecessor FAILED
5. If unblocking:
   - Prepend predecessor's output + result to next step's task (same pattern as retry context)
   - Set status PENDING
   - Publish job ID to `agent.jobs`
6. If condition not met:
   - Set status SKIPPED
   - Cascade: skip all remaining BLOCKED steps in the pipeline

## Forward Cancellation

When `POST /jobs/{id}/cancel` targets a pipeline job:

1. Cancel the target job (existing logic)
2. Find all jobs with same `pipeline_id` and `step_index > target.StepIndex` and status BLOCKED
3. Set all to CANCELLED

## LLM Enrichment

The orchestrator calls its configured `inferenceURL` (llama-cpp) to generate titles and summaries.

For pipelines: a single prompt that returns titles + summaries for all steps, using constrained JSON decoding.

For single jobs: a simpler prompt generating one title + summary.

This is synchronous — the API blocks until the LLM responds (~2-5s). If inference is unavailable or fails, jobs are created with empty title/summary (graceful degradation).

## Recipe Model Field

Add `model` to recipe `settings`:

```yaml
settings:
  max_turns: 50
  model: claude-sonnet-4-6
```

The runner reads `settings.model` from the recipe YAML and sets `GOOSE_MODEL` before launching goose. Falls back to the SandboxTemplate default if not specified.

## UI Changes

### Pipeline group rendering

Jobs with a `pipeline_id` are grouped in the job list. The compact flow shows agent pills with per-step status dots:

- PENDING: amber dot
- RUNNING: pulsing blue dot
- SUCCEEDED: green dot
- FAILED: red dot
- BLOCKED: grey/dimmed pill
- SKIPPED: dashed outline, muted, strikethrough label
- CANCELLED (cascade): same as skipped

When a step fails and downstream steps cascade to SKIPPED, a visual break in the chain (red break-line between failed step and skipped ones) makes the cascade origin immediately obvious.

### Expanded pipeline view

Each step card shows its own status, title, task, and output toggle. SKIPPED cards include the reason: "Skipped — condition 'on success' not met (step 1 failed)". Cancelled cascade cards show "Cancelled — predecessor cancelled".

### Title + summary in job list

Pipeline group header shows the LLM-generated pipeline title. Individual rows show step titles. Non-pipeline jobs also display their title.

## Decisions

| Decision              | Choice                                            | Rationale                                                     |
| --------------------- | ------------------------------------------------- | ------------------------------------------------------------- |
| Pipeline identity     | Peer jobs with shared pipeline_id (no parent job) | Simpler, avoids meta-job that doesn't run                     |
| Step context passing  | Full predecessor output prepended to next step    | Later steps build on earlier ones; matches retry pattern      |
| LLM enrichment timing | Synchronous at creation                           | Avoids UI flicker; acceptable latency for user action         |
| Cancellation          | Forward cascade                                   | Killing step 2 shouldn't undo step 1; step 3 should never run |
| Model selection       | Per-recipe via settings.model                     | Runner reads from recipe YAML, sets GOOSE_MODEL env var       |
