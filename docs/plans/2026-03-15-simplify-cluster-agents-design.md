# Design: Simplify Cluster Agents for Deep-Plan Orchestrator

**Date:** 2026-03-15
**Status:** Approved

## Context

The orchestrator now uses deep-plan for every job: the runner always runs
`deep-plan.yaml` first, which explores the repo/cluster, discovers available
recipe agents from disk, and builds a pipeline of steps. The `profile` field
in `SubmitRequest` is stored but never read by the consumer or runner — it's
dead weight.

The cluster agents still craft verbose task prompts with embedded instructions
("use conventional commits", "check for existing PRs", "skip generated code")
and attach a `profile` string. These instructions duplicate what the recipe
files already contain and fight against the deep planner's autonomy.

## Design

### Principle

Cluster agents provide **clear goals with factual context**, not instructions.
The deep planner decides the approach.

Goal pattern: **what happened** + **desired outcome** + **factual context**.

### New Task Prompts

**PatrolAgent** (alert investigation):

```
SigNoz alert "{title}" is firing (severity: {severity}, rule: {ruleID}).

Investigate the root cause. If a GitOps change can fix it, create and merge a PR.
If it requires manual intervention, create a GitHub issue with your findings.

Details: {detail}
```

**TestCoverageAgent**:

```
New commits landed on main ({commitRange}). Review changed Go and Python files
that lack test coverage and create PRs adding tests.

One PR per project, monitored and auto-merged.
```

**ReadmeFreshnessAgent**:

```
New commits landed on main. Audit all projects/*/README.md files for accuracy
against the actual project structure, configs, and code.

Fix any inaccuracies. One PR per project, monitored and auto-merged.
```

**RulesAgent**:

```
New commits landed on main ({commitRange}). Review merged PRs for patterns
that could be caught statically (semgrep rules) or prevented by Claude hooks.

One PR per rule or config change, monitored and auto-merged.
```

**PRFixAgent**:

```
PR #{prNumber} on branch {branch} has failing CI checks.

Diagnose and fix the CI failure. Push the fix (no force push).
```

### API Changes

- **`SubmitRequest`**: Remove `Profile` field. New jobs never set it.
- **`JobRecord`**: Keep `Profile` field with `omitempty` for backwards compat
  with existing KV entries. It will naturally age out.

### Cluster Agent Code Changes

- **`escalator.go`**: Remove `profile` from job request payload. Remove the
  patrol-style backwards-compat prompt builder (`if task == ""` fallback) —
  all agents now provide task via `Payload["task"]`.
- **`patrol.go`**: Move alert prompt into `PatrolAgent.Analyze()` via
  `Payload["task"]`, like other agents.
- **Each agent's `Analyze()`**: Replace verbose task prompts with goal-style.
- **`pr_fix_agent.go`**: Remove duplicate `hasActiveJob` — use escalator dedup.
  Move dedup from `Collect` to normal `Execute → Escalator` flow.

### What Doesn't Change

- Recipe files on disk (deep planner needs them for pipeline steps)
- Runner code (already works with just a task string)
- `GitActivityGate` (still needed for commit-level dedup)
- `Action.Payload` type (still useful for the `task` key)
- Orchestrator consumer logic
