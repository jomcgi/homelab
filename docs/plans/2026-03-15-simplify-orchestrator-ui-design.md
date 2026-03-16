# Simplify Orchestrator UI

**Date:** 2026-03-15
**Status:** Approved

## Context

The orchestrator backend was recently refactored to remove the pipeline composition API (`/pipeline`, `/agents`, `/infer`). The backend now autonomously creates and executes plans — a single `POST /jobs` creates a job, and the backend populates `plan[]` with agent steps and manages execution via `current_step`.

The UI still contains the old pipeline composer (@ mentions, agent picker, fast infer/deep plan buttons, drag-and-drop step editor) which calls removed endpoints. It needs to be simplified to match the new backend model.

## Design

### Frontend

**Remove entirely:**

- `PipelineComposer.jsx` — @ mention system, step cards, drag-and-drop, infer/deep plan buttons
- `pipeline-config.js` — LLM schema builders, system prompts, condition styles
- `api.js` functions: `listAgents`, `submitPipeline`, `inferPipeline`
- All agent-related state, pipeline composition logic, and deep plan polling in `App.jsx`

**Keep (adapted):**

- **Job submission** — single textarea + submit button. Calls `POST /jobs { task, source: "dashboard" }`.
- **Job history list** — polls `GET /jobs?limit=50` every 5s. Each row shows: status dot, title (from `/summarize` or truncated task), time ago, result pill (PR/issue/gist link).
- **Horizontal pipeline flow** — when a job has `plan[]`, renders compact horizontal pills with agent names, status dots, and connectors. Driven by `job.plan` + `job.current_step` instead of grouped pipeline jobs.
- **Expanded job detail** — clicking a job shows: LLM summary (1-2 sentences), horizontal plan flow below it, expandable output from latest attempt, cancel button for active jobs.

**New behavior:**

- On job list load, for jobs with `plan[]` but no cached title/summary, fire `POST /jobs/{id}/summarize`. Cache results client-side (in-memory map keyed by job ID).

### Backend — New Endpoint

```
POST /jobs/{id}/summarize
→ { "title": "...", "summary": "..." }
```

- Fetches job record from store
- Sends task + plan step descriptions to llama-cpp `/v1/chat/completions`
- Uses JSON schema constrained decoding for structured output
- Prompt: given the task and plan steps, produce a concise title (< 10 words) and 1-2 sentence summary
- Llama-cpp URL from `INFERENCE_URL` env var (in-cluster service address)

### Data Flow

```
User types task → POST /jobs → job created (PENDING)
                                    ↓
Backend autonomously plans + executes → plan[] populated, steps run
                                    ↓
UI polls GET /jobs → sees plan[] → renders horizontal flow
                   → calls POST /jobs/{id}/summarize → gets title + summary
                   → caches and displays
```

### What We're NOT Doing

- No agent selection UI (backend decides agents autonomously)
- No pipeline composition (backend creates the plan)
- No client-side LLM calls (all through backend proxy)
- No advanced submit fields (profile, tags, retries)

## Files Affected

### Delete

- `projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx`
- `projects/agent_platform/orchestrator/ui/src/pipeline-config.js`

### Rewrite

- `projects/agent_platform/orchestrator/ui/src/App.jsx` — strip pipeline composer, keep job list + horizontal flow + expanded detail
- `projects/agent_platform/orchestrator/ui/src/api.js` — remove `listAgents`, `submitPipeline`, `inferPipeline`; add `summarizeJob`

### Modify

- `projects/agent_platform/orchestrator/api.go` — add `POST /jobs/{id}/summarize` handler
- `projects/agent_platform/orchestrator/api_test.go` — test for summarize endpoint
