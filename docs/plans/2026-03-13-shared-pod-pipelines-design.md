# Shared-Pod Autonomous Pipeline Execution

## Summary

Replace the current multi-pod pipeline model with single-pod autonomous execution. A user submits one prompt, a pod plans and executes all steps in a shared workspace, and a typed result is returned. The orchestrator simplifies from pipeline coordinator to job dispatcher.

## Problem

The current pipeline model creates a new SandboxClaim (and pod) per step. Each pod clones the repo fresh, runs one Goose session, and is destroyed. Steps pass context to each other via truncated text summaries (`buildStepContext` — last 2000 chars of previous output). This means:

- **No filesystem continuity** — code written in step 1 is invisible to step 2
- **Lossy context** — 2000 chars of output is a poor substitute for seeing the actual changes
- **Pod overhead** — each step pays claim creation + pod allocation + clone time
- **Manual pipeline composition** — users must pick agents and write per-step tasks in the UI

## Design

### Flow

```
POST /jobs {task: "fix the flaky auth test"}
  → Orchestrator creates one SandboxClaim
  → Pod boots, clones repo
  → Runner auto-executes deep-plan recipe as first session
     → deep-plan reads available recipes from /workspace/homelab/.../recipes/
     → outputs structured plan: [research, code-fix, critic]
  → Runner executes each step sequentially in the same workspace
     → each step sees previous steps' file changes, git state, artifacts
  → Final step produces typed result (pr/report/fix/issue)
  → Runner reports completion via GET /status
  → Orchestrator captures result, cleans up SandboxClaim
```

### Agent-Runner Changes

The runner (`cmd/runner/main.go`) currently manages a single Goose session and rejects new work after completion (409 Conflict). Three changes:

**1. State reset between sessions**

After a session completes (`Done`/`Failed`), the runner resets to `Idle` and accepts the next `POST /run`. The output buffer clears for the new session. The workspace persists.

**2. Deep-plan auto-execution**

On startup, the runner reads a `DEEP_PLAN_RECIPE` env var (path to the deep-plan recipe YAML). When the first `POST /run` arrives with a task, the runner:

1. Runs the deep-plan recipe with the task as `{{ task_description }}`
2. Parses the structured output (JSON plan with agent/task pairs)
3. Stores the plan internally
4. Executes each step sequentially, loading the appropriate recipe from disk

**3. Extended GET /status**

The status endpoint includes plan progress:

```json
{
  "state": "running",
  "plan": [
    {
      "agent": "research",
      "description": "investigate flaky test",
      "status": "completed"
    },
    {
      "agent": "code-fix",
      "description": "fix root cause",
      "status": "running"
    },
    { "agent": "critic", "description": "review the fix", "status": "pending" }
  ],
  "current_step": 1,
  "result": null
}
```

### Orchestrator Changes

**Simplified API — six endpoints:**

| Method                   | Path            | Purpose                                 |
| ------------------------ | --------------- | --------------------------------------- |
| `POST /jobs`             | Submit a prompt | Creates SandboxClaim, dispatches to pod |
| `GET /jobs`              | List jobs       | Status, plan progress, filters          |
| `GET /jobs/{id}`         | Get job detail  | Full job record with plan + result      |
| `GET /jobs/{id}/output`  | Stream output   | Current session's stdout                |
| `POST /jobs/{id}/cancel` | Cancel job      | Cooperative cancellation                |
| `GET /health`            | Health check    | NATS connectivity                       |

**Removed endpoints:**

- `POST /pipeline` — deep-plan handles composition
- `GET /agents` — runner discovers recipes from disk
- `POST /infer` — inference proxy (unused without pipeline composer)

**Removed code:**

- `advancePipeline`, `cascadeSkip`, `buildStepContext` in consumer.go
- `handlePipeline`, `handleAgents`, `handleInfer` in api.go
- `loadAgentsConfig`, `agents.json` ConfigMap
- `AgentInfo`, `AgentsResponse`, `PipelineRequest`, `PipelineStep`, `PipelineResponse` types
- `enrichPipeline` LLM enrichment

**Consumer simplification:**

`processJob` creates one SandboxClaim, dispatches the task, and polls until the runner reports all steps complete. No more per-step claim creation or pipeline advancement logic.

### Data Model Changes

**JobRecord — fields removed:**

- `PipelineID` — no external pipeline coordination
- `StepIndex` — runner tracks steps internally
- `StepCondition` — deep-plan decides sequencing
- `PipelineSummary` — replaced by plan on the job record
- `Title`, `Summary` — LLM enrichment was best-effort, plan provides this

**JobRecord — fields added:**

```go
type PlanStep struct {
    Agent       string `json:"agent"`
    Description string `json:"description"`
    Status      string `json:"status"` // pending, running, completed, failed, skipped
}

// Added to JobRecord:
Plan        []PlanStep `json:"plan,omitempty"`
CurrentStep int        `json:"current_step"`
```

**GooseResult output types:**

| Type     | Meaning                    | Key field |
| -------- | -------------------------- | --------- |
| `pr`     | Pull request created       | `url`     |
| `issue`  | GitHub issue opened        | `url`     |
| `fix`    | Code changed (no PR)       | `summary` |
| `report` | Document/analysis produced | `summary` |
| `none`   | Informational/research     | `summary` |

### Recipe Discovery

Recipes live in the cloned repo at a known path. The deep-plan recipe reads the directory to discover available agents:

```
/workspace/homelab/projects/agent_platform/goose_agent/image/recipes/
├── code-fix.yaml
├── ci-debug.yaml
├── critic.yaml
├── research.yaml
└── ...
```

Deep-plan reads each YAML file's `title` and `description` fields to understand what each agent does, then composes a plan using those agent IDs.

**Benefits:**

- Adding a new recipe = adding a YAML file and pushing. No Helm values, no ConfigMap, no orchestrator redeploy.
- Recipe availability is branch-specific — a pod cloned from a feature branch sees recipes added on that branch.
- No `agents.json` configuration to keep in sync.

### UI Changes

**Removed:** Pipeline composer panel (agent picker, step builder, condition selector).

**Added:** Plan progress view on the job detail page — a read-only list of steps with status indicators (pending/running/completed/failed). This replaces the pipeline visualization.

**Preserved:** Job list, job detail, output viewer, submit form (now just a single text input).

### What's Preserved

- Single job API (`POST /jobs`) — same endpoint, same request format
- NATS JetStream queue — still dispatches jobs to the consumer
- SandboxClaim lifecycle — one claim per job (unchanged for single jobs)
- Warm pool — still pre-allocates pods
- All existing recipes — no changes needed
- Reconciliation — adapted for simplified model (no pipeline state to reconcile)
- Cancel — cooperative cancellation via job status polling

### Migration

The `POST /pipeline` endpoint and pipeline composer can be removed in a single PR. Existing pipeline-related fields on JobRecord become unused (NATS KV entries with old fields are harmless — Go's JSON decoder ignores unknown fields).

No data migration needed. Old job records with pipeline fields are still readable. New job records use `Plan`/`CurrentStep` instead.

## Alternatives Considered

### Long-lived gRPC runner pods

Redesign the runner as a persistent gRPC service with multi-session support, registered via A2A with Context Forge. Rejected as over-engineered — the current ephemeral model works well for single jobs, and the shared-pod change addresses the real pipeline limitation without an architecture rewrite.

### Replace Goose with Claude Code CLI/SDK

Remove Goose and invoke `claude -p` or the Claude Agent SDK directly. While Goose is a thin layer over Claude Code (`GOOSE_PROVIDER=claude-code`), replacing it doesn't solve the pipeline filesystem-sharing problem and adds migration risk. Can be revisited independently.

### A2A agent mesh via Context Forge

Register each agent type as an A2A endpoint and let agents discover and call each other peer-to-peer. A2A is synchronous request/response and has no concept of shared filesystems or sandbox provisioning. The orchestrator's async job model with retries and status tracking is better suited to the homelab's use case.
