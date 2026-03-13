# Deep Plan: Opus-Powered Pipeline Planning Agent

## Summary

Add a "Deep Plan" agent that uses Claude Opus to analyze the user's goal, explore the repo and cluster via MCP tools, and produce a structured pipeline definition. The user can iterate — editing the proposed pipeline and re-running Deep Plan with feedback — before submitting for execution.

This complements the existing "Infer pipeline" feature (local LLM, instant, pattern-matching) with a heavyweight alternative that reasons deeply about what agents and steps are actually needed.

## Motivation

The current pipeline inference uses a local LLM (qwen3.5-35b) via `/infer`. It's fast but shallow — it can only map agent names to tasks based on descriptions. It can't explore the repo, check cluster state, or reason about what actually makes sense for a given goal.

Deep Plan fills this gap: a real Goose job that uses Opus + MCP tools to research the problem space and propose an informed pipeline.

## Design

### Concept

Deep Plan is a regular batch job using the existing orchestrator infrastructure. No new communication protocols, no WebSockets, no interactive sessions. The "interactivity" comes from a feedback loop:

```
User writes goal in Composer
        |
   +----+-----+
   |           |
Fast Infer  Deep Plan
(local LLM)  (Opus job)
   |           |
   +-----+----+
         |
  Pipeline Composer populated
  User edits steps, tasks, conditions
         |
   +-----+----+
   |           |
Submit      Re-run Deep Plan
(execute)   (with edits + feedback as context)
```

### Output format

Deep Plan extends the `goose-result` block with a `pipeline` field:

````
```goose-result
type: pipeline
url: https://gist.github.com/...
summary: Recommends 3-step pipeline: research trace config, fix sampling, validate
pipeline: [{"agent":"research","task":"Investigate SigNoz trace sampling","condition":"always"},{"agent":"code-fix","task":"Update sampling rate to 25%","condition":"on success"},{"agent":"research","task":"Validate traces flowing at new rate","condition":"on success"}]
````

```

- `url` — gist containing the deep analysis (reasoning, trade-offs, alternatives considered)
- `pipeline` — same `PipelineStep[]` schema the UI already uses
- `summary` — what was planned and why

### Model override

Add a `model` field to `AgentInfo` (the agent config). The orchestrator passes it to the runner in the `/run` request body, and the runner appends `--model {model}` to the `goose run` CLI args.

This keeps model selection as an operational concern per-agent rather than baked into recipe instructions.

### First-run flow

1. User types goal in the Composer
2. Clicks **Deep Plan** button
3. UI sends `POST /jobs` with `profile: "deep-plan"` and `tags: ["deep-plan"]`
4. Orchestrator dispatches to Goose pod with `--model claude-opus-4-6`
5. Goose explores repo + cluster, writes analysis gist, returns structured pipeline
6. UI parses `result.pipeline` → populates Pipeline Composer
7. Gist URL displayed as "View analysis" link alongside the pipeline

### Iteration flow

1. User edits pipeline and/or types feedback in the Composer
2. Clicks **Deep Plan** again
3. UI sends `POST /jobs` with enriched task containing:
   - Original goal
   - Current pipeline state (as edited by user)
   - Previous analysis gist URL
   - User's new feedback/direction
4. Goose gets full context, returns updated pipeline + new gist
5. UI replaces pipeline in the Composer

### Graduation to execution

User clicks the existing **Submit to orchestrator** button — pipeline executes as batch jobs, identical to today.

## Changes by layer

### Agent config (`values.yaml`)

New `deep-plan` agent entry:
- `model: claude-opus-4-6`
- Recipe with instructions to explore the repo/cluster, write analysis gist, and output structured pipeline JSON in the `goose-result` block
- Higher `max_turns` (e.g. 80) to allow thorough exploration

### Data model (`model.go`)

- `GooseResult`: add `Pipeline []PipelineStep` field
- `AgentInfo`: add `Model string` field

### Result parser (`result.go`)

- Extend `parseGooseResult` to extract `pipeline:` line and parse JSON array

### Consumer / Sandbox (`consumer.go`, `sandbox.go`)

- Look up `model` from agent config when dispatching
- Pass `model` in `/run` request body

### Runner (`cmd/runner/main.go`)

- Accept `model` field in `/run` request
- Append `--model {model}` to `goose run` command args when present

### UI

- **PipelineComposer**: add "Deep Plan" button alongside renamed "Fast infer" button
- **App.jsx**: after deep-plan job completes, parse `result.pipeline` → populate Composer
- Show "View analysis" gist link when `result.url` is present
- On re-run, serialize current pipeline + feedback into the task field

### What doesn't change

- Pipeline submission (`POST /pipeline`)
- Job execution, retry, NATS plumbing
- Other recipes/agents
- SandboxClaim lifecycle (still one-shot per job)

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Interactive chat vs batch iteration | Batch iteration | Goose startup latency (~60s) makes per-turn chat impractical. Sequential jobs with context carryover achieve the same refinement loop with zero infra changes. |
| Model configuration | Per-agent `model` field in `AgentInfo` | Operational concern, not recipe-intrinsic. Keeps runner simple — just a new field on `/run` request. |
| Chat history persistence | Best-effort (stored in NATS KV as job records) | Full session continuity across pod eviction adds complexity for low value. Can add later. |
| Concurrent interactive sessions | No limit | Let cluster resources be the natural constraint. |
| Entry point | Dedicated "Deep Plan" button | Clean separation from fast inference. |
| Analysis artifact | GitHub gist | Consistent with existing research recipe pattern. Displayed alongside pipeline in UI. |
```
