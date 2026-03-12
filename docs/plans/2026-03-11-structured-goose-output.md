# Structured Goose Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured output parsing to Goose recipes and the orchestrator so job results are typed artifacts (PR, issue, gist) with concise summaries.

**Architecture:** Recipe instructions tell Goose to emit a `goose-result` fenced block. The orchestrator parses it from raw output into a `GooseResult` struct stored on the `Attempt` model and exposed via the API.

**Tech Stack:** Go (orchestrator), YAML (recipes)

---

### Task 1: Add GooseResult struct and model fields

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:46-54` (Attempt struct)
- Modify: `projects/agent_platform/orchestrator/model.go:78-84` (OutputResponse struct)

**Step 1: Add GooseResult struct and Result field to Attempt**

In `model.go`, add after the `Attempt` struct definition:

```go
// GooseResult is a structured result parsed from the agent's output.
type GooseResult struct {
	Type    string `json:"type"`
	URL     string `json:"url"`
	Summary string `json:"summary"`
}
```

Add `Result *GooseResult` field to the `Attempt` struct.

Add `Result *GooseResult` field to `OutputResponse`.

**Step 2: Commit**

```bash
git add projects/agent_platform/orchestrator/model.go
git commit -m "feat(orchestrator): add GooseResult struct to model"
```

### Task 2: Implement result parser with tests (TDD)

**Files:**

- Create: `projects/agent_platform/orchestrator/result.go`
- Create: `projects/agent_platform/orchestrator/result_test.go`

**Step 1: Write tests for parseGooseResult**

Test cases:

- Valid result block with all fields → returns GooseResult
- No result block → returns nil
- Multiple result blocks → uses the last one
- Malformed block (missing closing fence) → returns nil
- Partial fields (missing url) → returns GooseResult with empty URL
- Result block with extra whitespace → trims correctly
- Empty output string → returns nil

**Step 2: Implement parseGooseResult**

Parser finds the last ` ```goose-result ` block, splits header from body at `---` (not used in current design, but header lines are `key: value`), and returns a `GooseResult`.

**Step 3: Commit**

```bash
git add projects/agent_platform/orchestrator/result.go projects/agent_platform/orchestrator/result_test.go
git commit -m "feat(orchestrator): add goose-result block parser"
```

### Task 3: Wire parser into consumer

**Files:**

- Modify: `projects/agent_platform/orchestrator/consumer.go:176-186`

**Step 1: After output is captured, parse the result**

In `processJob()`, after `job.Attempts[idx].Output = output` (line 183), add:

```go
job.Attempts[idx].Result = parseGooseResult(output)
```

Also parse in the `execErr` path (line 185) — no-op since error output won't have a result block.

**Step 2: Update consumer_test to verify result parsing**

Add a test `TestProcessJob_ParsesStructuredResult` that returns output containing a goose-result block and verifies `Attempt.Result` is populated.

**Step 3: Commit**

```bash
git add projects/agent_platform/orchestrator/consumer.go projects/agent_platform/orchestrator/consumer_test.go
git commit -m "feat(orchestrator): parse structured result from agent output"
```

### Task 4: Update recipe instructions

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/recipes/code-fix.yaml`
- Modify: `projects/agent_platform/goose_agent/image/recipes/ci-debug.yaml`
- Modify: `projects/agent_platform/goose_agent/image/recipes/bazel.yaml`
- Modify: `projects/agent_platform/goose_agent/image/recipes/research.yaml`

**Step 1: Add output format instructions to each recipe**

Append structured output instructions to each recipe's `instructions` field. PR-producing recipes (code-fix, ci-debug, bazel) get PR-focused guidance. Research gets gist-focused guidance. All recipes include the good/bad example.

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/
git commit -m "feat(goose): add structured output instructions to recipes"
```

### Task 5: Run format and verify

**Step 1: Run format to regenerate BUILD files**

```bash
format
```

**Step 2: Verify build**

```bash
bazel test //projects/agent_platform/orchestrator/...
```

**Step 3: Commit any format changes**
