# Deep Plan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an Opus-powered "Deep Plan" agent that proposes structured pipelines from a user's goal, with iterative refinement support.

**Architecture:** Extends the existing batch job flow — no new protocols. A new `deep-plan` agent entry with `model` field flows through orchestrator → runner → `goose run --model`. The result parser gains a `pipeline` JSON field. The UI adds a "Deep Plan" button that submits a job, waits for completion, and populates the Pipeline Composer.

**Tech Stack:** Go (orchestrator, runner), React/Vite (UI), Goose CLI, YAML (recipe)

---

### Task 1: Add `Model` field to `AgentInfo` and parse it from config

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:19` (AgentInfo struct)
- Modify: `projects/agent_platform/orchestrator/main.go:227-252` (loadAgentsConfig — model is already part of AgentInfo, no extra work needed)
- Test: `projects/agent_platform/orchestrator/main_test.go`

**Step 1: Write the failing test**

In `main_test.go`, add a test that loads an agents config with a `model` field and asserts it appears on the AgentInfo:

```go
func TestLoadAgentsConfig_ModelField(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agents.json")
	data := `{"agents":[{"id":"deep-plan","label":"Deep Plan","model":"claude-opus-4-6","recipe":{"version":"1.0.0","title":"Deep Plan"}}]}`
	os.WriteFile(path, []byte(data), 0644)

	agents, recipes := loadAgentsConfig(path, slog.Default())
	if len(agents) != 1 {
		t.Fatalf("expected 1 agent, got %d", len(agents))
	}
	if agents[0].Model != "claude-opus-4-6" {
		t.Errorf("model = %q, want %q", agents[0].Model, "claude-opus-4-6")
	}
	if recipes["deep-plan"] == nil {
		t.Error("expected deep-plan recipe")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestLoadAgentsConfig_ModelField`
Expected: FAIL — `AgentInfo` has no `Model` field

**Step 3: Add `Model` field to `AgentInfo`**

In `model.go`, add to the `AgentInfo` struct:

```go
type AgentInfo struct {
	ID          string         `json:"id"`
	Label       string         `json:"label"`
	Icon        string         `json:"icon"`
	Background  string         `json:"bg"`
	Foreground  string         `json:"fg"`
	Description string         `json:"desc"`
	Category    string         `json:"category"`
	Model       string         `json:"model,omitempty"`
	Recipe      map[string]any `json:"recipe,omitempty"`
}
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestLoadAgentsConfig_ModelField`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/model.go projects/agent_platform/orchestrator/main_test.go
git commit -m "feat(agent-orchestrator): add model field to AgentInfo"
```

---

### Task 2: Add `Pipeline` field to `GooseResult` and extend parser

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:76` (GooseResult struct)
- Modify: `projects/agent_platform/orchestrator/result.go:9-40` (parseGooseResult)
- Test: `projects/agent_platform/orchestrator/result_test.go`

**Step 1: Write the failing test**

In `result_test.go`, add:

````go
func TestParseGooseResult_PipelineType(t *testing.T) {
	raw := "analysis complete\n```goose-result\ntype: pipeline\nurl: https://gist.github.com/jomcgi/abc123\nsummary: 3-step pipeline for trace debugging\npipeline: [{\"agent\":\"research\",\"task\":\"Investigate traces\",\"condition\":\"always\"},{\"agent\":\"code-fix\",\"task\":\"Fix sampling\",\"condition\":\"on success\"}]\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result")
	}
	if r.Type != "pipeline" {
		t.Errorf("type = %q, want %q", r.Type, "pipeline")
	}
	if r.URL != "https://gist.github.com/jomcgi/abc123" {
		t.Errorf("url = %q", r.URL)
	}
	if len(r.Pipeline) != 2 {
		t.Fatalf("expected 2 pipeline steps, got %d", len(r.Pipeline))
	}
	if r.Pipeline[0].Agent != "research" {
		t.Errorf("step 0 agent = %q, want %q", r.Pipeline[0].Agent, "research")
	}
	if r.Pipeline[1].Condition != "on success" {
		t.Errorf("step 1 condition = %q, want %q", r.Pipeline[1].Condition, "on success")
	}
}

func TestParseGooseResult_PipelineInvalidJSON(t *testing.T) {
	raw := "```goose-result\ntype: pipeline\npipeline: not valid json\nsummary: bad\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result (pipeline field just ignored)")
	}
	if r.Type != "pipeline" {
		t.Errorf("type = %q, want %q", r.Type, "pipeline")
	}
	if len(r.Pipeline) != 0 {
		t.Errorf("expected empty pipeline for invalid JSON, got %d steps", len(r.Pipeline))
	}
}
````

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestParseGooseResult_Pipeline`
Expected: FAIL — `GooseResult` has no `Pipeline` field

**Step 3: Add `Pipeline` field and parse it**

In `model.go`, update `GooseResult`:

```go
type GooseResult struct {
	Type     string         `json:"type"`
	URL      string         `json:"url"`
	Summary  string         `json:"summary"`
	Pipeline []PipelineStep `json:"pipeline,omitempty"`
}
```

In `result.go`, add the `pipeline` case and JSON parsing:

````go
import (
	"encoding/json"
	"strings"
)

func parseGooseResult(raw string) *GooseResult {
	const startMarker = "```goose-result\n"
	const endMarker = "\n```"

	lastStart := strings.LastIndex(raw, startMarker)
	if lastStart == -1 {
		return nil
	}
	content := raw[lastStart+len(startMarker):]
	endIdx := strings.Index(content, endMarker)
	if endIdx == -1 {
		return nil
	}
	content = content[:endIdx]

	result := &GooseResult{}
	for _, line := range strings.Split(content, "\n") {
		key, val, ok := strings.Cut(line, ": ")
		if !ok {
			continue
		}
		switch strings.TrimSpace(key) {
		case "type":
			result.Type = strings.TrimSpace(val)
		case "url":
			result.URL = strings.TrimSpace(val)
		case "summary":
			result.Summary = strings.TrimSpace(val)
		case "pipeline":
			var steps []PipelineStep
			if err := json.Unmarshal([]byte(strings.TrimSpace(val)), &steps); err == nil {
				result.Pipeline = steps
			}
		}
	}
	return result
}
````

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestParseGooseResult_Pipeline`
Expected: PASS

**Step 5: Run all result tests to check for regressions**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestParseGooseResult`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add projects/agent_platform/orchestrator/model.go projects/agent_platform/orchestrator/result.go projects/agent_platform/orchestrator/result_test.go
git commit -m "feat(agent-orchestrator): parse pipeline field from goose-result blocks"
```

---

### Task 3: Pass model through orchestrator to runner

**Files:**

- Modify: `projects/agent_platform/orchestrator/sandbox.go:79` (Run signature)
- Modify: `projects/agent_platform/orchestrator/sandbox.go:259-268` (dispatchTask — add model to payload)
- Modify: `projects/agent_platform/orchestrator/consumer.go:136-146` (look up model from agent config)
- Test: `projects/agent_platform/orchestrator/consumer_test.go`
- Test: `projects/agent_platform/orchestrator/sandbox_test.go`

**Step 1: Write failing test**

In `consumer_test.go`, add a test that verifies when a job has a profile with a model configured, the model is passed to the sandbox:

```go
func TestProcessJob_PassesModelToSandbox(t *testing.T) {
	store := newMemStore()
	job := pendingJob("MODEL01")
	job.Profile = "deep-plan"
	store.Put(context.Background(), job)

	var gotModel string
	sandbox := &fakeSandbox{
		runFn: func(ctx context.Context, claimName, task, recipe, model string, cancelFn func() bool, buf *syncBuffer) (*ExecResult, error) {
			gotModel = model
			return &ExecResult{ExitCode: 0, Output: "done"}, nil
		},
	}

	recipes := map[string]map[string]any{
		"deep-plan": {"version": "1.0.0", "title": "Deep Plan"},
	}
	models := map[string]string{
		"deep-plan": "claude-opus-4-6",
	}
	c := NewConsumer(nil, store, sandbox, nil, 5*time.Minute, recipes, models, slog.Default())
	c.processJob(context.Background(), newFakeMsg([]byte("MODEL01")))

	if gotModel != "claude-opus-4-6" {
		t.Errorf("model = %q, want %q", gotModel, "claude-opus-4-6")
	}
}
```

Note: This test will require updating the `Sandbox` interface, `fakeSandbox`, `NewConsumer`, and `Consumer` to carry models. The test captures the full change.

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestProcessJob_PassesModel`
Expected: FAIL — compilation errors

**Step 3: Implement the changes**

3a. Update the `Sandbox` interface in `consumer.go`:

```go
type Sandbox interface {
	Run(ctx context.Context, claimName, task, recipe, model string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error)
}
```

3b. Update `SandboxExecutor.Run` in `sandbox.go` to accept and forward `model`:

```go
func (s *SandboxExecutor) Run(ctx context.Context, claimName, task, recipe, model string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
```

3c. Update `dispatchTask` in `sandbox.go` to include model in the payload:

```go
func (s *SandboxExecutor) dispatchTask(ctx context.Context, baseURL, task, recipe, model string) error {
	payload := struct {
		Task              string `json:"task"`
		Recipe            string `json:"recipe,omitempty"`
		Model             string `json:"model,omitempty"`
		InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
	}{
		Task:              task,
		Recipe:            recipe,
		Model:             model,
		InactivityTimeout: int(s.inactivityTimeout.Seconds()),
	}
```

3d. Add `models` map to `Consumer`:

```go
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	publish     func(jobID string) error
	maxDuration time.Duration
	recipes     map[string]map[string]any
	models      map[string]string
	logger      *slog.Logger
}
```

3e. In `processJob`, look up model and pass to `sandbox.Run`:

```go
model := ""
if job.Profile != "" && c.models != nil {
	model = c.models[job.Profile]
}
// ...
r, err := c.sandbox.Run(jobCtx, claimName, task, recipeYAML, model, cancelFn, outputBuf)
```

3f. In `loadAgentsConfig` (`main.go`), build the models map alongside recipes:

```go
func loadAgentsConfig(path string, logger *slog.Logger) ([]AgentInfo, map[string]map[string]any, map[string]string) {
	// ... existing parsing ...
	recipes := make(map[string]map[string]any, len(cfg.Agents))
	models := make(map[string]string)
	for _, a := range cfg.Agents {
		if a.Recipe != nil {
			recipes[a.ID] = a.Recipe
		}
		if a.Model != "" {
			models[a.ID] = a.Model
		}
	}
	return cfg.Agents, recipes, models
}
```

3g. Update `main()` to pass models through:

```go
agents, recipes, models := loadAgentsConfig(envOr("AGENTS_CONFIG_PATH", "/etc/orchestrator/agents.json"), logger)
// ... pass models to NewConsumer ...
```

3h. Update `fakeSandbox` in `consumer_test.go` to match new interface.

3i. Update all existing callers of `sandbox.Run` and `dispatchTask` to pass the new `model` parameter.

**Step 4: Run all consumer and sandbox tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter="TestProcessJob|TestRunnerBaseURL"`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/sandbox.go projects/agent_platform/orchestrator/consumer.go projects/agent_platform/orchestrator/main.go projects/agent_platform/orchestrator/consumer_test.go projects/agent_platform/orchestrator/sandbox_test.go
git commit -m "feat(agent-orchestrator): pass model from agent config through to runner"
```

---

### Task 4: Runner accepts and uses `--model` flag

**Files:**

- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go:57-62` (RunRequest struct)
- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go:186-204` (buildGooseCmd)
- Test: `projects/agent_platform/orchestrator/cmd/runner/main_test.go`

**Step 1: Write failing tests**

In `cmd/runner/main_test.go`, add:

```go
func TestBuildGooseCmd_WithModel(t *testing.T) {
	args, cleanup := buildGooseCmd(RunRequest{Task: "plan a pipeline", Model: "claude-opus-4-6"})
	if cleanup != nil {
		defer cleanup()
	}

	expected := []string{"goose", "run", "--text", "plan a pipeline", "--model", "claude-opus-4-6"}
	if len(args) != len(expected) {
		t.Fatalf("expected %v, got %v", expected, args)
	}
	for i := range expected {
		if args[i] != expected[i] {
			t.Fatalf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
		}
	}
}

func TestBuildGooseCmd_WithRecipeAndModel(t *testing.T) {
	args, cleanup := buildGooseCmd(RunRequest{
		Task:   "plan it",
		Recipe: "version: '1.0.0'\ntitle: Test\n",
		Model:  "claude-opus-4-6",
	})
	if cleanup != nil {
		defer cleanup()
	}

	// Should have: goose run --recipe <file> --params ... --no-profile --model claude-opus-4-6
	if len(args) != 9 {
		t.Fatalf("expected 9 args, got %d: %v", len(args), args)
	}
	if args[7] != "--model" || args[8] != "claude-opus-4-6" {
		t.Fatalf("expected --model claude-opus-4-6 at end, got %s %s", args[7], args[8])
	}
}

func TestBuildGooseCmd_NoModel(t *testing.T) {
	// Existing no-recipe test but explicitly verify no --model flag
	args, _ := buildGooseCmd(RunRequest{Task: "fix it"})
	for _, arg := range args {
		if arg == "--model" {
			t.Fatal("--model should not appear when model is empty")
		}
	}
}
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/agent_platform/orchestrator/cmd/runner:runner_test --test_filter=TestBuildGooseCmd_WithModel`
Expected: FAIL — `RunRequest` has no `Model` field

**Step 3: Implement**

In `cmd/runner/main.go`, add `Model` to `RunRequest`:

```go
type RunRequest struct {
	Task              string `json:"task"`
	Recipe            string `json:"recipe,omitempty"`
	Model             string `json:"model,omitempty"`
	InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
}
```

Update `buildGooseCmd` to append `--model` when present:

```go
func buildGooseCmd(body RunRequest) ([]string, func()) {
	var args []string
	var cleanup func()

	if body.Recipe != "" {
		f, err := os.CreateTemp("", "goose-recipe-*.yaml")
		if err != nil {
			log.Printf("failed to create temp recipe file: %v", err)
			args = []string{"goose", "run", "--text", body.Task}
		} else {
			f.WriteString(body.Recipe)
			f.Close()
			cleanup = func() { os.Remove(f.Name()) }
			args = []string{
				"goose", "run",
				"--recipe", f.Name(),
				"--params", "task_description=" + body.Task,
				"--no-profile",
			}
		}
	} else {
		args = []string{"goose", "run", "--text", body.Task}
	}

	if body.Model != "" {
		args = append(args, "--model", body.Model)
	}

	return args, cleanup
}
```

**Step 4: Run all runner tests**

Run: `bazel test //projects/agent_platform/orchestrator/cmd/runner:runner_test`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/cmd/runner/main.go projects/agent_platform/orchestrator/cmd/runner/main_test.go
git commit -m "feat(agent-runner): accept model field and pass --model to goose CLI"
```

---

### Task 5: Add deep-plan agent config to Helm values

**Files:**

- Modify: `projects/agent_platform/chart/values.yaml:111+` (add deep-plan agent entry)

**Step 1: Add the deep-plan agent to `agentsConfig.agents`**

Add after the last agent entry in `values.yaml`:

````yaml
- id: deep-plan
  label: Deep Plan
  icon: "🧠"
  bg: "#fef3c7"
  fg: "#92400e"
  desc: Analyse goals and propose optimal agent pipelines using Opus
  category: analyse
  model: claude-opus-4-6
  recipe:
    version: "1.0.0"
    title: "Deep Plan"
    description: "Analyse a goal and propose an optimal agent pipeline"
    instructions: |
      You are a pipeline planning agent for the homelab agent orchestrator.
      Your job is to deeply understand the user's goal, explore the repository
      and cluster state, and propose an optimal pipeline of agent steps.

      ## Process
      1. Analyse the goal — what does the user want to achieve?
      2. Explore the repo structure and relevant code using the developer extension
      3. Check cluster state using Context Forge MCP tools if relevant
      4. Design a pipeline using the available agents
      5. Write your analysis and reasoning to a GitHub gist
      6. Return the pipeline as structured JSON

      ## Available Agents
      - ci-debug: Debug CI/build failures using BuildBuddy logs. Creates PRs with fixes.
      - research: Investigate infrastructure topics. Produces gists with findings.
      - code-fix: Fix code issues, create PRs. General-purpose code changes.
      - scaffold: Create new services, charts, or configs from scratch.
      - helm-chart-dev: Develop or modify Helm charts.
      - dep-upgrade: Upgrade dependencies (Go modules, npm packages, etc).
      - docs: Write or update documentation.
      - bazel: Fix or create Bazel BUILD files and build configs.

      ## Iteration Context
      If the prompt includes "Previous Pipeline" and "Feedback" sections, the user
      is iterating on a prior plan. Read the previous pipeline, understand what they
      changed in the UI, and incorporate their feedback into an improved pipeline.

      ## Output Format (REQUIRED)
      When COMPLETELY finished, create a GitHub gist with your full analysis, then
      emit your result as the LAST thing you write using EXACTLY this format:

      ```goose-result
      type: pipeline
      url: <gist URL with your analysis>
      summary: <1-2 sentences: what you planned and why>
      pipeline: <JSON array of pipeline steps>
      ```

      The pipeline field must be a valid JSON array of objects with keys:
      - agent: one of the available agent IDs
      - task: specific instructions for that agent step
      - condition: "always", "on success", or "on failure"

      Example:
      ```goose-result
      type: pipeline
      url: https://gist.github.com/jomcgi/abc123
      summary: 3-step pipeline to fix SigNoz trace dropping after 5 minutes
      pipeline: [{"agent":"research","task":"Investigate SigNoz trace retention config and identify why traces drop after 5 minutes","condition":"always"},{"agent":"code-fix","task":"Update trace sampling rate from 10% to 25% in SigNoz Helm values","condition":"on success"},{"agent":"research","task":"Validate traces are now retained beyond 5 minutes","condition":"on success"}]
      ```
    prompt: |
      {{ task_description | indent(2) }}

      REMINDER: Create a gist with your analysis and emit the goose-result block with type: pipeline as the LAST thing you write.
    parameters:
      - key: task_description
        description: "The goal and any iteration context"
        input_type: string
        requirement: required
    extensions:
      - type: builtin
        name: developer
      - type: streamable_http
        name: context-forge
        uri: http://context-forge.mcp-gateway.svc.cluster.local:8000/mcp
        timeout: 300
        headers:
          Authorization: "Bearer ${CI_DEBUG_MCP_TOKEN}"
      - type: stdio
        name: github
        cmd: pnpm
        args: ["dlx", "@modelcontextprotocol/server-github"]
        env_keys: ["GITHUB_TOKEN"]
    settings:
      max_turns: 80
      max_tool_repetitions: 5
````

**Step 2: Validate with helm template**

Run: `helm template agent-platform projects/agent_platform/chart/ -f projects/agent_platform/deploy/values.yaml -s templates/orchestrator/agents-configmap.yaml 2>&1 | head -20`
Expected: ConfigMap renders with deep-plan agent including model field

**Step 3: Commit**

```bash
git add projects/agent_platform/chart/values.yaml
git commit -m "feat(agent-platform): add deep-plan agent with Opus model config"
```

---

### Task 6: Add deep-plan recipe to image recipes directory

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml`

**Step 1: Create the recipe file**

Copy the recipe from the values.yaml agent config into a standalone file (this is the source-of-truth copy that recipe validation tests check):

```yaml
version: "1.0.0"
title: "Deep Plan"
description: "Analyse a goal and propose an optimal agent pipeline"
instructions: |
  [same as values.yaml recipe instructions above]
prompt: |
  {{ task_description | indent(2) }}

  REMINDER: Create a gist with your analysis and emit the goose-result block with type: pipeline as the LAST thing you write.
parameters:
  - key: task_description
    description: "The goal and any iteration context"
    input_type: string
    requirement: required
extensions:
  - type: builtin
    name: developer
  - type: streamable_http
    name: context-forge
    uri: http://context-forge.mcp-gateway.svc.cluster.local:8000/mcp
    timeout: 300
    headers:
      Authorization: "Bearer ${CI_DEBUG_MCP_TOKEN}"
  - type: stdio
    name: github
    cmd: pnpm
    args: ["dlx", "@modelcontextprotocol/server-github"]
    env_keys: ["GITHUB_TOKEN"]
settings:
  max_turns: 80
  max_tool_repetitions: 5
```

**Step 2: Run recipe validation tests**

Run: `bazel test //projects/agent_platform/goose_agent/image:recipe_validate_test`
Expected: PASS — new recipe has all required fields, template vars declared as parameters, includes goose-result block

**Step 3: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml
git commit -m "feat(goose-agent): add deep-plan recipe for pipeline planning"
```

---

### Task 7: UI — Add Deep Plan button and job-to-pipeline flow

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx:28-68` (add deepPlan handler)
- Modify: `projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx:654-679` (add Deep Plan button, rename Infer)
- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx` (deep plan job polling → pipeline population)
- Modify: `projects/agent_platform/orchestrator/ui/src/api.js` (add submitDeepPlan helper if needed)

**Step 1: Add Deep Plan submission to PipelineComposer**

In `PipelineComposer.jsx`, add a new `handleDeepPlan` callback alongside `handleInfer`. The composer needs to accept new props: `onDeepPlan` (callback), `deepPlanJobId` (active job ID for polling state), `deepPlanStatus` (PENDING/RUNNING/SUCCEEDED), and `analysisUrl` (gist link):

```jsx
// In PipelineComposer component, add props:
export default function PipelineComposer({ agents, onSubmit, onDeepPlan, deepPlanStatus, analysisUrl }) {
```

Add the Deep Plan button next to the existing Infer button in the footer area:

```jsx
<button
  onClick={() => {
    const text = extractPromptText(editorRef.current);
    if (text) onDeepPlan(text, pipeline);
  }}
  disabled={
    !hasText || deepPlanStatus === "RUNNING" || deepPlanStatus === "PENDING"
  }
  style={
    {
      /* same style as infer button but with different colors */
    }
  }
>
  {deepPlanStatus === "RUNNING" || deepPlanStatus === "PENDING"
    ? "Planning…"
    : "Deep plan"}
</button>
```

Rename existing "Infer pipeline" button to "Fast infer".

Add the analysis gist link when present:

```jsx
{
  analysisUrl && (
    <a
      href={analysisUrl}
      target="_blank"
      rel="noopener noreferrer"
      style={{ fontSize: 11, color: "#6b7280" }}
    >
      View analysis ↗
    </a>
  );
}
```

**Step 2: Wire up deep plan in App.jsx**

In `App.jsx`, add state and handlers:

```jsx
const [deepPlanJobId, setDeepPlanJobId] = useState(null);
const [deepPlanStatus, setDeepPlanStatus] = useState(null);
const [analysisUrl, setAnalysisUrl] = useState(null);

const handleDeepPlan = async (prompt, currentPipeline) => {
  // Build enriched task with iteration context
  let task = prompt;
  if (currentPipeline.length > 0) {
    task = `## Goal\n${prompt}\n\n## Previous Pipeline\n${JSON.stringify(currentPipeline)}\n\n## Feedback\n${prompt}`;
  }

  const res = await fetch("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task,
      profile: "deep-plan",
      tags: ["deep-plan"],
      source: "ui",
    }),
  });
  const data = await res.json();
  setDeepPlanJobId(data.id);
  setDeepPlanStatus("PENDING");
  setAnalysisUrl(null);
};
```

Add a polling effect that watches the deep plan job and populates the pipeline when done:

```jsx
useEffect(() => {
  if (!deepPlanJobId) return;
  const interval = setInterval(async () => {
    const res = await fetch(`/jobs/${deepPlanJobId}`);
    const job = await res.json();
    setDeepPlanStatus(job.status);
    if (job.status === "SUCCEEDED") {
      clearInterval(interval);
      const lastAttempt = job.attempts?.[job.attempts.length - 1];
      if (lastAttempt?.result?.pipeline) {
        setPipeline(lastAttempt.result.pipeline);
        setInferSource("inferred");
      }
      if (lastAttempt?.result?.url) {
        setAnalysisUrl(lastAttempt.result.url);
      }
      setDeepPlanJobId(null);
    } else if (job.status === "FAILED" || job.status === "CANCELLED") {
      clearInterval(interval);
      setDeepPlanJobId(null);
    }
  }, 5000);
  return () => clearInterval(interval);
}, [deepPlanJobId]);
```

Pass props to PipelineComposer:

```jsx
<PipelineComposer
  agents={agents}
  onSubmit={handleSubmitPipeline}
  onDeepPlan={handleDeepPlan}
  deepPlanStatus={deepPlanStatus}
  analysisUrl={analysisUrl}
/>
```

**Step 3: Test manually**

1. Run the dev server: `cd projects/agent_platform/orchestrator/ui && pnpm dev`
2. Verify "Deep plan" and "Fast infer" buttons appear
3. Verify "Deep plan" button submits a job via `POST /jobs`
4. Verify the analysis link appears when a gist URL is returned

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "feat(agent-orchestrator): add Deep Plan button and job-to-pipeline UI flow"
```

---

### Task 8: Handle API response for pipeline results

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go` (ensure `result.pipeline` is serialized in job responses)

**Step 1: Verify the pipeline field serializes correctly**

The `Pipeline` field on `GooseResult` has `json:"pipeline,omitempty"` — this should serialize automatically through the existing `GET /jobs/{id}` handler since it returns the full `JobRecord` including `Attempts[].Result`.

Write a quick API test to confirm:

In `api_test.go`, add:

```go
func TestGetJob_IncludesPipelineResult(t *testing.T) {
	store := newMemStore()
	job := &JobRecord{
		ID:     "PIPE01",
		Task:   "plan something",
		Status: JobSucceeded,
		Attempts: []Attempt{{
			Number: 1,
			Result: &GooseResult{
				Type:    "pipeline",
				URL:     "https://gist.github.com/test/123",
				Summary: "3-step pipeline",
				Pipeline: []PipelineStep{
					{Agent: "research", Task: "investigate", Condition: "always"},
					{Agent: "code-fix", Task: "fix it", Condition: "on success"},
				},
			},
		}},
	}
	store.Put(context.Background(), job)

	api := NewAPI(store, nil, func() error { return nil }, 0, nil, nil, "", slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/jobs/PIPE01", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != 200 {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var result JobRecord
	json.NewDecoder(rec.Body).Decode(&result)

	lastAttempt := result.Attempts[len(result.Attempts)-1]
	if lastAttempt.Result == nil {
		t.Fatal("expected result")
	}
	if len(lastAttempt.Result.Pipeline) != 2 {
		t.Fatalf("expected 2 pipeline steps, got %d", len(lastAttempt.Result.Pipeline))
	}
	if lastAttempt.Result.Pipeline[0].Agent != "research" {
		t.Errorf("step 0 agent = %q", lastAttempt.Result.Pipeline[0].Agent)
	}
}
```

**Step 2: Run test**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestGetJob_IncludesPipelineResult`
Expected: PASS (no code changes needed — just verifying the data flows through)

**Step 3: Commit**

```bash
git add projects/agent_platform/orchestrator/api_test.go
git commit -m "test(agent-orchestrator): verify pipeline result serialization in API responses"
```

---

### Task 9: Update loadAgentsConfig callers and run full test suite

**Files:**

- Modify: `projects/agent_platform/orchestrator/main.go` (update caller)
- Modify: `projects/agent_platform/orchestrator/api.go:34` (NewAPI may need models param, or not — API doesn't use models directly, consumer does)

**Step 1: Verify all compilation and tests pass**

Run: `bazel test //projects/agent_platform/orchestrator/... //projects/agent_platform/goose_agent/...`
Expected: ALL PASS

**Step 2: Run format**

Run: `format`
Expected: No changes (or auto-fix BUILD files if needed)

**Step 3: Commit any format fixes**

```bash
git add -A
git commit -m "chore(agent-orchestrator): fix formatting and BUILD files"
```

---

### Task 10: Bump chart version and create PR

**Files:**

- Modify: `projects/agent_platform/chart/Chart.yaml` (bump version)

**Step 1: Bump chart version**

Increment the patch (or minor) version in `Chart.yaml`.

**Step 2: Commit**

```bash
git add projects/agent_platform/chart/Chart.yaml
git commit -m "chore(agent-platform): bump chart version for deep-plan feature"
```

**Step 3: Push and create PR**

```bash
git push -u origin feat/deep-plan
gh pr create --title "feat(agent-orchestrator): add Deep Plan agent for Opus-powered pipeline planning" --body "$(cat <<'EOF'
## Summary
- Adds `model` field to agent config, passed through orchestrator → runner → `goose run --model`
- Extends `goose-result` parser to handle `pipeline` JSON field
- New `deep-plan` agent with Opus model and recipe for pipeline planning
- UI: "Deep Plan" button submits a planning job, populates Pipeline Composer on completion
- UI: "View analysis" gist link shown alongside proposed pipeline
- Renamed existing "Infer pipeline" to "Fast infer"

## Test plan
- [ ] Unit tests for model field parsing in agent config
- [ ] Unit tests for pipeline field parsing in goose-result
- [ ] Unit tests for model passthrough in consumer → sandbox → runner
- [ ] Unit tests for --model CLI flag construction in runner
- [ ] API test for pipeline result serialization
- [ ] Recipe validation test passes for new deep-plan recipe
- [ ] Manual: Deep Plan button visible, submits job, populates pipeline on completion
- [ ] Manual: Fast infer still works as before
- [ ] Manual: Iteration flow — edit pipeline, re-run Deep Plan with feedback

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 4: Enable auto-merge if CI passes**

```bash
gh pr merge --auto --rebase
```
