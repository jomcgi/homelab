# Pipeline Output Per-Step Filtering

**Date:** 2026-03-18
**Status:** Approved

## Problem

Pipeline job output is displayed as a single monolithic blob in the orchestrator UI. Users cannot see which output belongs to which pipeline step. The goose startup banner appears once per step (only the first is stripped), and `goose-result` blocks are shown as raw text despite being parsed separately. The agent also doesn't know its output will be rendered visually, so it doesn't format for readability.

## Design

### 1. Backend: Enhanced Output Cleaning (`clean.go`)

Enhance `cleanOutput()` to:

- Strip **all** goose banners, not just the first (each pipeline step spawns a new goose process)
- Remove `goose-result` fenced blocks from the output text (the parsed result is already stored in `Attempt.Result`)

The `--- pipeline step N: agent_name ---` separators are preserved in the stored output — they serve as structural markers for frontend parsing.

### 2. Frontend: Per-Step Accordion Output (`App.jsx`)

Replace the single `<pre>` output block with per-step collapsible accordion sections.

**Output parsing:** Split the output string on the regex `/\n--- pipeline step (\d+): (.+?) ---\n/` to produce an array of `{ index, agent, content }` objects. The separator text itself is excluded from rendered content. Content before the first separator (deep-plan output) is hidden.

**Accordion sections:** Each step gets a collapsible section with:

- Agent name + status dot (matching the pipeline node colors)
- Chevron toggle
- Step output rendered via `react-markdown`

**Default state:** All sections collapsed when the job row is expanded.

### 3. Frontend: Clickable Pipeline Nodes (`App.jsx`)

Make `PipelineFlow` nodes interactive:

- Clicking a node sets `activeStep` state on the `JobRow`
- The active node gets a visual ring/border highlight
- The matching accordion section opens and smooth-scrolls into view
- Clicking the same node again deselects and collapses it

### 4. Frontend: Markdown Rendering

Add `react-markdown` dependency. Each step's output chunk renders through `react-markdown` instead of raw `<pre>`. Styled to match the existing UI (monospace code blocks, consistent font sizes, DM Sans body text).

Non-pipeline jobs (edge case where deep-plan produces zero steps) fall back to the current single-output toggle with markdown rendering.

### 5. Goose Hints: Markdown Output Guidance (`.goosehints`)

Add to `projects/agent_platform/goose_agent/.goosehints`:

```
## Output Formatting
Your output is rendered as markdown in a dashboard UI. Use markdown formatting
(headers, lists, code blocks) for clarity. Do not include raw terminal output
like progress bars or spinner characters.
```

## Data Flow

```
Runner output (per step, with separators + banners + goose-result blocks)
  → cleanOutput() strips ALL banners + goose-result blocks + ANSI
  → stored in Attempt.Output (single blob, step separators preserved)
  → API serves to frontend
  → Frontend splits on separator regex → per-step chunks
  → Each chunk rendered via react-markdown in accordion section
  → PipelineFlow nodes scroll/highlight to matching section
```

## Dependencies

- `react-markdown` added to `projects/agent_platform/orchestrator/ui/package.json`

## What We're Not Doing

- No per-step API endpoint — frontend parsing of separators is sufficient
- No changes to the runner separator format
- No syntax highlighting library (code blocks get monospace styling only)
- No per-step timing (would require backend changes to track step start/end times)
