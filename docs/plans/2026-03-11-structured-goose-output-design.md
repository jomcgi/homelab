# Structured Goose Output

**Date**: 2026-03-11
**Status**: Approved

## Problem

Goose job output is raw text with session boilerplate. Consumers of the
orchestrator API have no structured way to know what artifact was produced
(PR, issue, gist) or get a concise summary of the outcome.

## Solution

Two-layer approach: recipe-level prompt instructions + orchestrator-level parsing.

### Output Format

Each recipe instructs Goose to emit a fenced `goose-result` block as its
final output:

````
```goose-result
type: pr | issue | gist
url: https://github.com/jomcgi/homelab/pull/123
summary: Fixed missing healthcheck port in signoz values.yaml. PR passes CI.
```
````

- **type**: `pr` (code changes), `issue` (discovered problems), `gist` (research findings)
- **url**: Link to the created GitHub artifact (required)
- **summary**: 1-2 sentences describing what was done and the outcome (not reasoning)

### Recipe Mapping

| Recipe   | Default output type | Notes                      |
| -------- | ------------------- | -------------------------- |
| code-fix | pr                  | Creates PR with fix        |
| ci-debug | pr                  | Creates PR with CI fix     |
| bazel    | pr                  | Creates PR with build fix  |
| research | gist                | Creates gist with findings |

Any recipe may emit `type: issue` if it discovers a problem it cannot fix.

### Orchestrator Changes

- `GooseResult` struct with `Type`, `URL`, `Summary` fields
- Parser finds the last `goose-result` fenced block in raw output
- `Attempt.Result` stores the parsed result (nullable)
- `OutputResponse.Result` exposes it via API
- Raw `Output` field unchanged (debug/audit trail)

### Files Changed

- `projects/agent_platform/goose_agent/image/recipes/*.yaml` — output instructions
- `projects/agent_platform/orchestrator/model.go` — GooseResult struct + model fields
- `projects/agent_platform/orchestrator/result.go` — parser (new file)
- `projects/agent_platform/orchestrator/result_test.go` — parser tests (new file)
- `projects/agent_platform/orchestrator/consumer.go` — call parser after execution
