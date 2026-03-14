# Shared-Pod Autonomous Pipeline Execution — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** All pipeline steps execute sequentially in a single pod with a shared workspace, planned autonomously by the deep-plan agent.

**Architecture:** The agent-runner gains state-reset between sessions and plan tracking. The orchestrator consumer reuses one SandboxClaim per pipeline. Deep-plan reads recipes from disk. Pipeline-specific API, types, and enrichment code are removed.

**Tech Stack:** Go, Goose recipes (YAML), NATS JetStream, Kubernetes SandboxClaim CRD

**Design doc:** `docs/plans/2026-03-13-shared-pod-pipelines-design.md`

---

### Task 1: Runner — allow state reset between sessions

The runner currently rejects `POST /run` when state is `Done` or `Failed`. Allow it to accept new work after completion.

**Files:**

- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go:137-181`
- Test: `projects/agent_platform/orchestrator/cmd/runner/main_test.go` (create — no test file exists yet)

**Step 1: Write the failing test**

Create `projects/agent_platform/orchestrator/cmd/runner/main_test.go`:

```go
package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHandleRun_AcceptsAfterCompletion(t *testing.T) {
	r := newRunner()

	// Simulate a completed session.
	r.mu.Lock()
	r.state = StateDone
	code := 0
	r.exitCode = &code
	now := time.Now()
	r.startedAt = &now
	r.output = []byte("previous output")
	r.mu.Unlock()

	// POST /run should be accepted (not 409 Conflict).
	body := `{"task":"second task"}`
	req := httptest.NewRequest("POST", "/run", strings.NewReader(body))
	w := httptest.NewRecorder()
	r.handleRun(w, req)

	if w.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", w.Code, w.Body.String())
	}

	// Previous output should be cleared.
	r.mu.RLock()
	if len(r.output) != 0 {
		t.Errorf("expected output to be cleared, got %d bytes", len(r.output))
	}
	r.mu.RUnlock()
}

func TestHandleRun_StillRejectsWhileRunning(t *testing.T) {
	r := newRunner()

	r.mu.Lock()
	r.state = StateRunning
	r.mu.Unlock()

	body := `{"task":"another task"}`
	req := httptest.NewRequest("POST", "/run", strings.NewReader(body))
	w := httptest.NewRecorder()
	r.handleRun(w, req)

	if w.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d", w.Code)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/orchestrator/cmd/runner:runner_test --test_filter=AcceptsAfterCompletion`
Expected: FAIL — `expected 202, got 409`

**Step 3: Implement the state reset**

In `main.go`, modify `handleRun` to only reject `StateRunning`:

```go
r.mu.Lock()
if r.state == StateRunning {
	r.mu.Unlock()
	http.Error(w, "task already running", http.StatusConflict)
	return
}
```

This already works — the current code only blocks on `StateRunning`. The key change is that the state reset block below it already clears `r.output`, `r.exitCode`, etc. Verify the test passes to confirm the current code handles Done/Failed correctly.

If the test fails, it means there's an additional guard. Remove any check that blocks on `StateDone`/`StateFailed`.

**Step 4: Run tests to verify they pass**

Run: `bazel test //projects/agent_platform/orchestrator/cmd/runner:runner_test`
Expected: PASS (both tests)

**Step 5: Commit**

```
feat(agent-runner): allow state reset between sessions

The runner now accepts POST /run after a session completes (Done/Failed),
clearing the output buffer for the new session while preserving workspace
state. This enables sequential multi-session execution in the same pod.
```

---

### Task 2: Runner — add plan tracking to GET /status

Extend the runner to track a plan (list of steps with status) and expose it via `GET /status`.

**Files:**

- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go`
- Test: `projects/agent_platform/orchestrator/cmd/runner/main_test.go`

**Step 1: Write the failing test**

Add to `main_test.go`:

```go
func TestHandleStatus_IncludesPlan(t *testing.T) {
	r := newRunner()

	r.mu.Lock()
	r.state = StateRunning
	r.plan = []PlanStep{
		{Agent: "research", Description: "investigate", Status: "completed"},
		{Agent: "code-fix", Description: "fix it", Status: "running"},
		{Agent: "critic", Description: "review", Status: "pending"},
	}
	r.currentStep = 1
	r.mu.Unlock()

	req := httptest.NewRequest("GET", "/status", nil)
	w := httptest.NewRecorder()
	r.handleStatus(w, req)

	var resp StatusResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if len(resp.Plan) != 3 {
		t.Fatalf("expected 3 plan steps, got %d", len(resp.Plan))
	}
	if resp.CurrentStep != 1 {
		t.Errorf("expected current_step=1, got %d", resp.CurrentStep)
	}
	if resp.Plan[0].Status != "completed" {
		t.Errorf("expected step 0 completed, got %s", resp.Plan[0].Status)
	}
}
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `PlanStep` type and `plan`/`currentStep` fields don't exist.

**Step 3: Implement plan tracking**

Add types and fields to `main.go`:

```go
// PlanStep represents one step in the autonomous pipeline plan.
type PlanStep struct {
	Agent       string `json:"agent"`
	Description string `json:"description"`
	Status      string `json:"status"` // pending, running, completed, failed, skipped
}

// Add to StatusResponse:
Plan        []PlanStep `json:"plan,omitempty"`
CurrentStep int        `json:"current_step"`

// Add to runner struct:
plan        []PlanStep
currentStep int
```

Update `handleStatus` to include the new fields:

```go
func (r *runner) handleStatus(w http.ResponseWriter, _ *http.Request) {
	r.mu.RLock()
	resp := StatusResponse{
		State:       r.state,
		PID:         r.pid,
		ExitCode:    r.exitCode,
		StartedAt:   r.startedAt,
		Plan:        r.plan,
		CurrentStep: r.currentStep,
	}
	r.mu.RUnlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}
```

**Step 4: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator/cmd/runner:runner_test`
Expected: PASS

**Step 5: Commit**

```
feat(agent-runner): add plan tracking to GET /status

The runner now tracks a list of PlanStep structs and exposes them via
GET /status alongside the current step index. This allows the
orchestrator to poll plan progress for the UI.
```

---

### Task 3: Runner — auto-execute deep-plan and sequential steps

The core feature: when `POST /run` is called, the runner automatically runs deep-plan first, parses the structured output for a pipeline, then executes each step sequentially using the appropriate recipe from disk.

**Files:**

- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go`
- Test: `projects/agent_platform/orchestrator/cmd/runner/main_test.go`

**Step 1: Write the failing test**

This is an integration-style test. The runner spawns goose as a subprocess, which we can't easily fake. Instead, test the plan parsing logic:

````go
func TestParsePlanFromOutput(t *testing.T) {
	output := `Some analysis text here...

` + "```goose-result\n" +
		`type: pipeline
url: https://gist.github.com/jomcgi/abc123
summary: 3-step pipeline to fix auth
pipeline: [{"agent":"research","task":"investigate","condition":"always"},{"agent":"code-fix","task":"fix it","condition":"on success"}]
` + "```\n"

	steps, err := parsePlanFromOutput(output)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if len(steps) != 2 {
		t.Fatalf("expected 2 steps, got %d", len(steps))
	}
	if steps[0].Agent != "research" {
		t.Errorf("step 0 agent: got %q, want %q", steps[0].Agent, "research")
	}
	if steps[1].Agent != "code-fix" {
		t.Errorf("step 1 agent: got %q, want %q", steps[1].Agent, "code-fix")
	}
}

func TestParsePlanFromOutput_NoPipeline(t *testing.T) {
	output := "```goose-result\ntype: report\nsummary: just a report\n```\n"
	steps, err := parsePlanFromOutput(output)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(steps) != 0 {
		t.Errorf("expected 0 steps for non-pipeline result, got %d", len(steps))
	}
}
````

**Step 2: Run test to verify it fails**

Expected: FAIL — `parsePlanFromOutput` doesn't exist.

**Step 3: Implement plan parsing and autonomous execution**

Add to `main.go`:

````go
// parsedStep is the raw step from the goose-result pipeline JSON.
type parsedStep struct {
	Agent     string `json:"agent"`
	Task      string `json:"task"`
	Condition string `json:"condition"`
}

// parsePlanFromOutput extracts pipeline steps from a goose-result block.
// Returns empty slice (not error) if the result type is not "pipeline".
func parsePlanFromOutput(output string) ([]parsedStep, error) {
	const startMarker = "` + "```goose-result\\n" + `"
	const endMarker = "\\n` + "```" + `"

	lastStart := strings.LastIndex(output, startMarker)
	if lastStart == -1 {
		return nil, nil
	}
	content := output[lastStart+len(startMarker):]
	endIdx := strings.Index(content, endMarker)
	if endIdx == -1 {
		return nil, nil
	}
	content = content[:endIdx]

	// Check if this is a pipeline result.
	var resultType string
	var pipelineJSON string
	for _, line := range strings.Split(content, "\n") {
		key, val, ok := strings.Cut(line, ": ")
		if !ok {
			continue
		}
		switch strings.TrimSpace(key) {
		case "type":
			resultType = strings.TrimSpace(val)
		case "pipeline":
			pipelineJSON = strings.TrimSpace(val)
		}
	}

	if resultType != "pipeline" || pipelineJSON == "" {
		return nil, nil
	}

	var steps []parsedStep
	if err := json.Unmarshal([]byte(pipelineJSON), &steps); err != nil {
		return nil, fmt.Errorf("parsing pipeline JSON: %w", err)
	}
	return steps, nil
}
````

Modify `runGoose` to support autonomous pipeline mode. When `RECIPES_DIR` env var is set, after the first session (deep-plan) completes:

1. Parse the output for a pipeline
2. Set `r.plan` with the steps
3. For each step, load the recipe from `$RECIPES_DIR/<agent>.yaml`
4. Call goose with the step's recipe and task
5. Update `r.plan[i].Status` as each step progresses

The existing `handleRun` stays as the entry point — it starts the deep-plan session. The autonomous loop runs in the same goroutine after deep-plan completes.

**Step 4: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator/cmd/runner:runner_test`
Expected: PASS

**Step 5: Commit**

```
feat(agent-runner): auto-execute deep-plan and sequential pipeline steps

When RECIPES_DIR is set, the runner automatically runs deep-plan as the
first session, parses the structured output for a pipeline, then
executes each step sequentially using recipes loaded from disk. Plan
progress is exposed via GET /status.
```

---

### Task 4: Deep-plan recipe — read agents from disk instead of hardcoded list

Update the deep-plan recipe instructions to tell the agent to discover available recipes by reading the recipes directory rather than relying on a hardcoded list.

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml`

**Step 1: Update the recipe**

Replace the hardcoded `## Available Agents` section with instructions to read from disk:

```yaml
## Available Agents
Discover available agents by reading the recipe YAML files in the recipes
directory (same directory as this recipe). Each file's name (without .yaml)
is the agent ID. Read each file's `title` and `description` fields to
understand what the agent does.

Do NOT use agents that don't have a recipe file on disk.
```

Remove the hardcoded agent list (lines 18-34 in the current recipe).

Keep the `## Composition Patterns` section as guidance — those patterns are still valid regardless of which agents exist on disk.

**Step 2: Verify recipe is valid YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml'))"`
Expected: No error

**Step 3: Commit**

```
refactor(deep-plan): discover available agents from recipe files on disk

Instead of hardcoding the agent list in the recipe instructions,
deep-plan now reads the recipes directory to discover available agents.
This means adding a new agent only requires adding a recipe YAML file.
```

---

### Task 5: Orchestrator — add PlanStep to model and extend status polling

Add the `PlanStep` type to the orchestrator's data model and extend the status polling to capture plan progress from the runner.

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go`
- Modify: `projects/agent_platform/orchestrator/sandbox.go`
- Test: `projects/agent_platform/orchestrator/sandbox_test.go`

**Step 1: Write the failing test**

Add to `sandbox_test.go`:

```go
func TestPollStatus_IncludesPlan(t *testing.T) {
	// Test that pollStatus parses plan steps from the runner response.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"state":        "running",
			"current_step": 1,
			"plan": []map[string]string{
				{"agent": "research", "description": "investigate", "status": "completed"},
				{"agent": "code-fix", "description": "fix", "status": "running"},
			},
		})
	}))
	defer srv.Close()

	state, exitCode, plan, err := pollStatusWithPlan(context.Background(), srv.URL, &http.Client{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "running" {
		t.Errorf("state: got %q, want %q", state, "running")
	}
	if len(plan) != 2 {
		t.Fatalf("expected 2 plan steps, got %d", len(plan))
	}
}
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `PlanStep` not in model.go, `pollStatusWithPlan` doesn't exist.

**Step 3: Add PlanStep to model.go**

```go
// PlanStep represents one step in an autonomous pipeline plan.
type PlanStep struct {
	Agent       string `json:"agent"`
	Description string `json:"description"`
	Status      string `json:"status"` // pending, running, completed, failed, skipped
}
```

Add fields to `JobRecord`:

```go
Plan        []PlanStep `json:"plan,omitempty"`
CurrentStep int        `json:"current_step"`
```

**Step 4: Extend pollStatus in sandbox.go**

Add a `pollStatusWithPlan` function (or extend the existing `pollStatus` to return plan data) that parses the new fields from the runner's `GET /status` response.

**Step 5: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: PASS

**Step 6: Commit**

```
feat(orchestrator): add PlanStep to model and extend status polling

The orchestrator can now capture plan progress from the runner's
GET /status response and store it on the JobRecord for UI display.
```

---

### Task 6: Consumer — reuse SandboxClaim for autonomous pipeline

Modify the consumer to let the runner handle the full pipeline in one pod. The consumer dispatches the task, polls until all steps are done, and captures the final result.

**Files:**

- Modify: `projects/agent_platform/orchestrator/consumer.go`
- Test: `projects/agent_platform/orchestrator/consumer_test.go`

**Step 1: Write the failing test**

Add a test that verifies the consumer captures plan progress during polling:

```go
func TestProcessJob_CapturesPlanProgress(t *testing.T) {
	store := newMemStore()
	job := &JobRecord{
		ID:         "PLAN01",
		Task:       "fix the flaky test",
		Status:     JobPending,
		MaxRetries: 1,
		Attempts:   []Attempt{},
	}
	store.Put(context.Background(), job)

	planSteps := []PlanStep{
		{Agent: "research", Description: "investigate", Status: "completed"},
		{Agent: "code-fix", Description: "fix it", Status: "completed"},
	}

	sandbox := &fakeSandbox{
		runFn: func(ctx context.Context, claimName, task, recipe, model string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
			outputBuf.Write([]byte("done"))
			return &ExecResult{ClaimName: claimName, ExitCode: 0, Output: "done"}, nil
		},
		planSteps: planSteps, // new field on fakeSandbox
	}

	// ... test that after processJob, the job record has Plan populated
}
```

Note: the exact test structure depends on how plan polling is integrated into the consumer's poll loop. Adapt based on the sandbox interface changes from Task 5.

**Step 2: Implement consumer changes**

The key change: during `pollUntilDone` (or the consumer's processing loop), periodically poll `GET /status` for plan data and write it to the job record. This is an extension of the existing output-flush ticker.

**Step 3: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: PASS (all existing + new tests)

**Step 4: Commit**

```
feat(orchestrator): capture plan progress from runner during execution

The consumer now polls the runner's GET /status for plan steps and
writes them to the JobRecord. The UI can display step-by-step progress.
```

---

### Task 7: Remove pipeline API and related code

Clean up the pipeline-specific code that's no longer needed.

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go` — remove `handlePipeline`, `handleAgents`, `handleInfer`
- Modify: `projects/agent_platform/orchestrator/model.go` — remove `PipelineID`, `StepIndex`, `StepCondition`, `PipelineSummary`, `Title`, `Summary`, `AgentInfo`, `AgentsResponse`, `PipelineRequest`, `PipelineStep`, `PipelineResponse`
- Delete: `projects/agent_platform/orchestrator/enrich.go`
- Delete: `projects/agent_platform/orchestrator/enrich_test.go`
- Modify: `projects/agent_platform/orchestrator/consumer.go` — remove `advancePipeline`, `cascadeSkip`, `buildStepContext`
- Modify: `projects/agent_platform/orchestrator/result.go` — remove `Pipeline` field from `GooseResult` and its parsing
- Modify: `projects/agent_platform/orchestrator/main.go` — remove `loadAgentsConfig`, `agents`/`recipes`/`models` params
- Modify: `projects/agent_platform/orchestrator/api_test.go` — remove pipeline/agents tests
- Modify: `projects/agent_platform/orchestrator/consumer_test.go` — remove pipeline advancement tests
- Modify: `projects/agent_platform/orchestrator/result_test.go` — remove pipeline parsing tests

**Step 1: Remove API endpoints**

Remove `handlePipeline`, `handleAgents`, `handleInfer` from `api.go`. Remove their route registrations from `RegisterRoutes`. Remove associated tests from `api_test.go`.

**Step 2: Remove pipeline model fields**

Remove `PipelineID`, `StepIndex`, `StepCondition`, `PipelineSummary`, `Title`, `Summary` from `JobRecord`. Remove `AgentInfo`, `AgentsResponse`, `PipelineRequest`, `PipelineStep`, `PipelineResponse` types. Remove `Pipeline` field from `GooseResult`.

**Step 3: Remove pipeline consumer logic**

Remove `advancePipeline`, `cascadeSkip`, `buildStepContext` from `consumer.go`. Remove the `advancePipeline` calls from `processJob`. Remove associated tests.

**Step 4: Remove enrichment code**

Delete `enrich.go` and `enrich_test.go` entirely.

**Step 5: Simplify main.go**

Remove `loadAgentsConfig`. Remove `agents`, `recipes`, `models` variables and their injection into `NewAPI` and `NewConsumer`. Remove `AGENTS_CONFIG_PATH` env var. Update `NewAPI` and `NewConsumer` signatures.

**Step 6: Run all tests**

Run: `bazel test //projects/agent_platform/orchestrator/...`
Expected: PASS — all remaining tests pass, removed tests are gone

**Step 7: Commit**

```
refactor(orchestrator): remove pipeline API, enrichment, and agent registry

The orchestrator no longer manages pipelines directly — the runner handles
autonomous planning and execution. Removes POST /pipeline, GET /agents,
POST /infer endpoints and all pipeline-related model fields, consumer
logic, and enrichment code.
```

---

### Task 8: Chart version bump and deploy config

Bump the chart version and update the orchestrator deployment to remove the agents ConfigMap.

**Files:**

- Modify: `projects/agent_platform/chart/Chart.yaml` — bump version
- Modify: `projects/agent_platform/deploy/application.yaml` — update `targetRevision`
- Modify: `projects/agent_platform/chart/orchestrator/values.yaml` — remove agents config
- Modify: `projects/agent_platform/chart/orchestrator/templates/deployment.yaml` — remove agents ConfigMap mount if present

**Step 1: Bump chart version**

Increment the patch (or minor) version in `Chart.yaml`.

**Step 2: Update targetRevision**

Update `deploy/application.yaml` to match the new chart version.

**Step 3: Remove agents config from values**

Remove the `agents:` block from `chart/orchestrator/values.yaml` (the large block of agent IDs, labels, icons, categories, and recipes).

**Step 4: Verify Helm template renders**

Run: `helm template agent-platform projects/agent_platform/chart/ -f projects/agent_platform/deploy/values.yaml`
Expected: Renders without errors, no agents ConfigMap in output

**Step 5: Commit**

```
chore(agent-platform): bump chart version and remove agents ConfigMap

Removes the agents.json ConfigMap and associated Helm values now that
the runner discovers recipes from the cloned repo at runtime.
```

---

### Task 9: Add RECIPES_DIR to SandboxTemplate environment

The runner needs to know where recipes live in the workspace so it can load them for each pipeline step.

**Files:**

- Modify: `projects/agent_platform/chart/sandboxes/values.yaml` or `templates/sandboxtemplate.yaml`

**Step 1: Add env var**

Add `RECIPES_DIR` to the goose container environment in the SandboxTemplate:

```yaml
- name: RECIPES_DIR
  value: /workspace/homelab/projects/agent_platform/goose_agent/image/recipes
```

**Step 2: Add DEEP_PLAN_RECIPE env var**

Point the runner at the deep-plan recipe specifically:

```yaml
- name: DEEP_PLAN_RECIPE
  value: /workspace/homelab/projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml
```

**Step 3: Verify template renders**

Run: `helm template agent-platform projects/agent_platform/chart/ -f projects/agent_platform/deploy/values.yaml`
Expected: SandboxTemplate includes both env vars

**Step 4: Commit**

```
feat(sandboxes): add RECIPES_DIR and DEEP_PLAN_RECIPE env vars

Configures the runner to discover recipes from the cloned repo and
auto-execute deep-plan as the first session for autonomous pipelines.
```

---

### Task 10: Format and final verification

**Step 1: Run format**

Run: `format`

**Step 2: Run all tests**

Run: `bazel test //projects/agent_platform/orchestrator/...`
Expected: PASS

**Step 3: Verify Helm template**

Run: `helm template agent-platform projects/agent_platform/chart/ -f projects/agent_platform/deploy/values.yaml`
Expected: Clean render

**Step 4: Commit any formatting fixes**

```
style: format after shared-pod pipeline changes
```
