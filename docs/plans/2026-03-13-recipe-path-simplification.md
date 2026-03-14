# Recipe Path Simplification

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the fragile recipe-in-ConfigMap flow (YAML->JSON->map->YAML->tempfile) with direct file paths to recipe YAML files that already exist in the repo checkout.

**Architecture:** Recipes live as YAML files in `projects/agent_platform/goose_agent/image/recipes/`. The orchestrator config maps each agent ID to a file path. The runner passes the path directly to `goose run --recipe <path>` (relative to its workDir). Models are embedded in recipes via `settings.goose_model` (a native goose recipe field) instead of the separate `--model` CLI flag.

**Tech Stack:** Go, Helm, YAML, goose recipes

---

### Task 1: Add `settings.goose_model` to recipes that need Opus

Recipes that need a specific model currently rely on the orchestrator's `models` map + `--model` CLI flag. Move the model into the recipe itself using goose's native `settings.goose_model` field.

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml`
- Modify: `projects/agent_platform/goose_agent/image/recipe_validate_test.go`

**Step 1: Add `settings.goose_model` to the allowlist in the validation test**

In `recipe_validate_test.go`, the `recipeTopLevelFields` allowlist doesn't include `settings` sub-fields (settings is already allowed as a top-level key). But the test struct `recipeFile` doesn't validate settings contents, so no change needed there. However, we should add a settings field validation. For now, `settings` is already in `recipeTopLevelFields`, so the existing schema check passes. No test change needed for the allowlist.

**Step 2: Add `settings.goose_model` to deep-plan recipe**

In `projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml`, add `goose_model` to the existing `settings` block:

```yaml
settings:
  goose_model: claude-opus-4-6
  max_turns: 20
  max_tool_repetitions: 5
```

**Step 3: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml
git commit -m "fix(agent-platform): add goose_model to deep-plan recipe settings"
```

---

### Task 2: Replace `Recipe map[string]any` with `RecipePath string` in model + config

The orchestrator currently stores the full recipe map in memory and renders it to YAML at dispatch time. Replace this with a simple path string.

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go`
- Modify: `projects/agent_platform/orchestrator/main.go`

**Step 1: Update `AgentInfo` struct**

In `model.go`, replace the `Recipe` field:

```go
type AgentInfo struct {
	ID          string `json:"id"`
	Label       string `json:"label"`
	Icon        string `json:"icon"`
	Background  string `json:"bg"`
	Foreground  string `json:"fg"`
	Description string `json:"desc"`
	Category    string `json:"category"`
	RecipePath  string `json:"recipePath,omitempty"`
}
```

Remove the `Model` field (it now lives inside the recipe YAML via `settings.goose_model`).

**Step 2: Update `loadAgentsConfig` in `main.go`**

Replace the function to build a `recipePaths map[string]string` instead of `recipes map[string]map[string]any` and `models map[string]string`:

```go
func loadAgentsConfig(path string, logger *slog.Logger) ([]AgentInfo, map[string]string) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			logger.Info("no agents config file", "path", path)
			return nil, nil
		}
		logger.Error("failed to read agents config", "path", path, "error", err)
		return nil, nil
	}
	var cfg struct {
		Agents []AgentInfo `json:"agents"`
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		logger.Error("failed to parse agents config", "path", path, "error", err)
		return nil, nil
	}
	recipePaths := make(map[string]string, len(cfg.Agents))
	for _, a := range cfg.Agents {
		if a.RecipePath != "" {
			recipePaths[a.ID] = a.RecipePath
		}
	}
	logger.Info("loaded agents config", "path", path, "agents", len(cfg.Agents), "recipes", len(recipePaths))
	return cfg.Agents, recipePaths
}
```

**Step 3: Update `main()` call site**

Change the call and plumb the new types through:

```go
agents, recipePaths := loadAgentsConfig(envOr("AGENTS_CONFIG_PATH", "/etc/orchestrator/agents.json"), logger)
inferenceURL := envOr("INFERENCE_URL", "")

api := NewAPI(store, publish, healthCheck, maxRetries, agents, recipePaths, inferenceURL, logger)
// ...
consumer := NewConsumer(cons, store, sandbox, publish, maxDuration, recipePaths, logger)
```

**Step 4: Commit (will not compile yet — that's fine, subsequent tasks fix the callers)**

```bash
git add projects/agent_platform/orchestrator/model.go projects/agent_platform/orchestrator/main.go
git commit -m "refactor(agent-orchestrator): replace recipe map with recipe path in config"
```

---

### Task 3: Update `Consumer` to pass recipe path instead of rendered YAML

The consumer currently looks up a `map[string]any`, renders it to YAML, and passes the string. Now it just looks up a path.

**Files:**

- Modify: `projects/agent_platform/orchestrator/consumer.go`

**Step 1: Update `Consumer` struct and `NewConsumer`**

Replace `recipes map[string]map[string]any` and `models map[string]string` with `recipePaths map[string]string`:

```go
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	publish     func(jobID string) error
	maxDuration time.Duration
	recipePaths map[string]string
	logger      *slog.Logger
}

func NewConsumer(cons jetstream.Consumer, store Store, sandbox Sandbox, publish func(jobID string) error, maxDuration time.Duration, recipePaths map[string]string, logger *slog.Logger) *Consumer {
	return &Consumer{
		cons:        cons,
		store:       store,
		sandbox:     sandbox,
		publish:     publish,
		maxDuration: maxDuration,
		recipePaths: recipePaths,
		logger:      logger,
	}
}
```

**Step 2: Update `processJob` to pass recipe path instead of rendered YAML**

Replace the recipe rendering block (lines ~138-154 in consumer.go) with:

```go
	// Look up recipe path for this agent.
	recipePath := ""
	if job.Profile != "" && c.recipePaths != nil {
		recipePath = c.recipePaths[job.Profile]
	}
```

Remove the model lookup block entirely (lines ~150-154). The model is now inside the recipe YAML.

**Step 3: Update `Sandbox` interface and `Run` call**

Change the `Sandbox` interface signature — replace `recipe` (YAML string) and `model` with `recipePath`:

```go
type Sandbox interface {
	Run(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error)
}
```

Update the `Run` call in `processJob`:

```go
r, err := c.sandbox.Run(jobCtx, claimName, task, recipePath, cancelFn, outputBuf)
```

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/consumer.go
git commit -m "refactor(agent-orchestrator): pass recipe path to sandbox instead of rendered YAML"
```

---

### Task 4: Update `SandboxExecutor` to dispatch recipe path

The sandbox executor currently sends the recipe YAML string and model to the runner HTTP API. Now it sends a recipe path.

**Files:**

- Modify: `projects/agent_platform/orchestrator/sandbox.go`

**Step 1: Update `Run` method signature**

```go
func (s *SandboxExecutor) Run(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
```

**Step 2: Update `dispatchTask` call and signature**

Pass `recipePath` instead of `recipe` and `model`:

```go
if err := s.dispatchTask(ctx, baseURL, task, recipePath); err != nil {
```

```go
func (s *SandboxExecutor) dispatchTask(ctx context.Context, baseURL, task, recipePath string) error {
	payload := struct {
		Task              string `json:"task"`
		RecipePath        string `json:"recipe_path,omitempty"`
		InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
	}{
		Task:              task,
		RecipePath:        recipePath,
		InactivityTimeout: int(s.inactivityTimeout.Seconds()),
	}
	// ... rest unchanged
}
```

**Step 3: Commit**

```bash
git add projects/agent_platform/orchestrator/sandbox.go
git commit -m "refactor(agent-orchestrator): dispatch recipe path to runner"
```

---

### Task 5: Update runner to use recipe file path directly

The runner currently receives recipe YAML as a string, writes it to a temp file, then passes it to goose. Now it receives a path relative to workDir.

**Files:**

- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go`

**Step 1: Update `RunRequest` struct**

Replace `Recipe string` with `RecipePath string`:

```go
type RunRequest struct {
	Task              string `json:"task"`
	RecipePath        string `json:"recipe_path,omitempty"`
	InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
}
```

Remove the `Model` field entirely.

**Step 2: Rewrite `buildGooseCmd`**

Replace the entire function — no more temp file or model flag:

```go
func buildGooseCmd(body RunRequest) []string {
	if body.RecipePath != "" {
		return []string{
			"goose", "run",
			"--recipe", body.RecipePath,
			"--params", "task_description=" + body.Task,
			"--no-profile",
		}
	}
	return []string{"goose", "run", "--text", body.Task}
}
```

Note: `buildGooseCmd` no longer returns a cleanup function (no temp files). Update the caller in `runGoose`:

```go
args := buildGooseCmd(body)
// Remove: if cleanup != nil { defer cleanup() }
cmd := exec.CommandContext(ctx, args[0], args[1:]...)
```

**Step 3: Commit**

```bash
git add projects/agent_platform/orchestrator/cmd/runner/main.go
git commit -m "fix(agent-orchestrator): use recipe file path instead of temp file in runner"
```

---

### Task 6: Delete `recipe.go` and update `recipe_test.go`

The `renderRecipeYAML` function and all its tests are no longer needed.

**Files:**

- Delete: `projects/agent_platform/orchestrator/recipe.go`
- Delete: `projects/agent_platform/orchestrator/recipe_test.go`

**Step 1: Delete both files**

```bash
git rm projects/agent_platform/orchestrator/recipe.go projects/agent_platform/orchestrator/recipe_test.go
```

**Step 2: Commit**

```bash
git commit -m "refactor(agent-orchestrator): remove recipe YAML rendering code"
```

---

### Task 7: Update `API` to use recipe paths for validation

The API currently validates agent profiles against `recipes map[string]map[string]any`. Change to `recipePaths map[string]string`.

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go`

**Step 1: Update `API` struct and `NewAPI`**

```go
type API struct {
	store             Store
	publish           func(jobID string) error
	healthCheck       func() error
	defaultMaxRetries int
	agents            []AgentInfo
	recipePaths       map[string]string
	inferenceURL      string
	logger            *slog.Logger
}

func NewAPI(store Store, publish func(string) error, healthCheck func() error, defaultMaxRetries int, agents []AgentInfo, recipePaths map[string]string, inferenceURL string, logger *slog.Logger) *API {
	return &API{store: store, publish: publish, healthCheck: healthCheck, defaultMaxRetries: defaultMaxRetries, agents: agents, recipePaths: recipePaths, inferenceURL: inferenceURL, logger: logger}
}
```

**Step 2: Update `handleSubmit` validation**

Change the profile check (line ~62):

```go
if req.Profile != "" {
	if _, ok := a.recipePaths[req.Profile]; !ok {
		a.writeError(w, http.StatusBadRequest, "unknown agent: "+req.Profile)
		return
	}
}
```

**Step 3: Update `handlePipeline` validation**

Change the agent validation loop (line ~311):

```go
for _, step := range req.Steps {
	if _, ok := a.recipePaths[step.Agent]; !ok {
		a.writeError(w, http.StatusBadRequest, "unknown agent: "+step.Agent)
		return
	}
}
```

**Step 4: Update `handleAgents` — remove recipe stripping**

The `Recipe` field no longer exists on `AgentInfo`, so the stripping loop is unnecessary. Simplify:

```go
func (a *API) handleAgents(w http.ResponseWriter, _ *http.Request) {
	agents := a.agents
	if agents == nil {
		agents = []AgentInfo{}
	}
	a.writeJSON(w, http.StatusOK, AgentsResponse{Agents: agents})
}
```

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/api.go
git commit -m "refactor(agent-orchestrator): use recipe paths for agent validation in API"
```

---

### Task 8: Update all tests

Tests reference the old `recipes map[string]map[string]any`, `models map[string]string`, old `Sandbox` interface signature, and old `buildGooseCmd` return signature.

**Files:**

- Modify: `projects/agent_platform/orchestrator/api_test.go`
- Modify: `projects/agent_platform/orchestrator/consumer_test.go`
- Modify: `projects/agent_platform/orchestrator/cmd/runner/main_test.go`

**Step 1: Update `api_test.go`**

Change all `recipes` maps from `map[string]map[string]any{...}` to `map[string]string{...}`:

```go
// Before:
recipes := map[string]map[string]any{"ci-debug": {"version": "1.0.0"}}
// After:
recipePaths := map[string]string{"ci-debug": "projects/agent_platform/goose_agent/image/recipes/ci-debug.yaml"}
```

Update all `NewAPI(...)` calls to pass `recipePaths` instead of `recipes`.

Update `TestHandleAgents` — remove the assertion that `Recipe` is stripped (field no longer exists). Check that the `RecipePath` is not empty or just verify the agent metadata comes through.

**Step 2: Update `consumer_test.go`**

Update `fakeSandbox` to match new `Sandbox` interface (no `recipe` or `model` params):

```go
type fakeSandbox struct {
	runFn func(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, buf *syncBuffer) (*ExecResult, error)
}

func (f *fakeSandbox) Run(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, buf *syncBuffer) (*ExecResult, error) {
	if f.runFn != nil {
		return f.runFn(ctx, claimName, task, recipePath, cancelFn, buf)
	}
	return &ExecResult{ExitCode: 0, Output: "success"}, nil
}
```

Update `newTestConsumer` — no longer passes `models`:

```go
func newTestConsumer(store Store, sandbox Sandbox) *Consumer {
	return NewConsumer(nil, store, sandbox, nil, 5*time.Minute, nil, slog.Default())
}
```

Update `TestProcessJob_PassesModelToSandbox` — rename to `TestProcessJob_PassesRecipePathToSandbox` and verify the recipe path is passed:

```go
func TestProcessJob_PassesRecipePathToSandbox(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-RECIPE")
	job.Profile = "deep-plan"
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	var gotPath string
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, recipePath string, _ func() bool, _ *syncBuffer) (*ExecResult, error) {
			gotPath = recipePath
			return &ExecResult{ExitCode: 0, Output: "ok"}, nil
		},
	}

	recipePaths := map[string]string{"deep-plan": "projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml"}
	c := NewConsumer(nil, store, sandbox, nil, 5*time.Minute, recipePaths, slog.Default())
	c.processJob(context.Background(), msg)

	if gotPath != "projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml" {
		t.Errorf("recipePath = %q, want deep-plan recipe path", gotPath)
	}
}
```

**Step 3: Update `cmd/runner/main_test.go`**

Rewrite `buildGooseCmd` tests for the new signature (returns `[]string`, no cleanup):

- `TestBuildGooseCmd_NoRecipe` — unchanged except remove cleanup check
- `TestBuildGooseCmd_WithRecipe` — becomes `TestBuildGooseCmd_WithRecipePath`:
  ```go
  func TestBuildGooseCmd_WithRecipePath(t *testing.T) {
  	args := buildGooseCmd(RunRequest{Task: "do it", RecipePath: "recipes/research.yaml"})
  	expected := []string{"goose", "run", "--recipe", "recipes/research.yaml", "--params", "task_description=do it", "--no-profile"}
  	if len(args) != len(expected) {
  		t.Fatalf("expected %v, got %v", expected, args)
  	}
  	for i := range expected {
  		if args[i] != expected[i] {
  			t.Fatalf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
  		}
  	}
  }
  ```
- Delete `TestBuildGooseCmd_WithModel`, `TestBuildGooseCmd_WithRecipeAndModel`, `TestBuildGooseCmd_EmptyModelOmitted`, `TestBuildGooseCmd_RecipeTempFilePreservesTemplateVars` — no longer applicable
- Keep `TestBuildGooseCmd_YAMLHostileTask` but update for new signature (no cleanup)

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/api_test.go projects/agent_platform/orchestrator/consumer_test.go projects/agent_platform/orchestrator/cmd/runner/main_test.go
git commit -m "test(agent-orchestrator): update tests for recipe path simplification"
```

---

### Task 9: Update `values.yaml` — replace inline recipes with `recipePath`

Remove all inline `recipe:` blocks and `model:` fields from agent entries. Replace with `recipePath:`.

**Files:**

- Modify: `projects/agent_platform/chart/values.yaml`

**Step 1: Replace each agent entry**

For every agent, replace:

```yaml
- id: research
  label: Research
  # ... UI fields ...
  recipe:
    version: "1.0.0"
    # ... 50+ lines of recipe YAML ...
```

With:

```yaml
- id: research
  label: Research
  # ... UI fields ...
  recipePath: projects/agent_platform/goose_agent/image/recipes/research.yaml
```

Remove `model: claude-opus-4-6` from agents that had it (deep-plan, etc.) — the model now lives in the recipe file itself.

**Step 2: Remove the agents ConfigMap template**

The ConfigMap still exists but is now much smaller (just agent metadata + paths, no inline recipes). No structural change to the template needed — `{{ .Values.agentsConfig | toJson | quote }}` still works.

**Step 3: Commit**

```bash
git add projects/agent_platform/chart/values.yaml
git commit -m "fix(agent-platform): replace inline recipes with file paths in values.yaml"
```

---

### Task 10: Bump chart version and update `targetRevision`

Per repo convention, any chart change requires a version bump in both `Chart.yaml` and `application.yaml`.

**Files:**

- Modify: `projects/agent_platform/chart/Chart.yaml`
- Modify: `projects/agent_platform/deploy/application.yaml`

**Step 1: Bump chart version**

Increment the patch version in `Chart.yaml`.

**Step 2: Update `targetRevision` in `application.yaml`**

Match the new chart version.

**Step 3: Commit**

```bash
git add projects/agent_platform/chart/Chart.yaml projects/agent_platform/deploy/application.yaml
git commit -m "chore(agent-platform): bump chart version for recipe path simplification"
```

---

### Task 11: Verify build compiles and tests pass

**Step 1: Run format to update BUILD files**

```bash
cd /tmp/claude-worktrees/fix-recipe-model-field && format
```

**Step 2: Verify Go compilation**

```bash
cd /tmp/claude-worktrees/fix-recipe-model-field && go build ./projects/agent_platform/orchestrator/...
cd /tmp/claude-worktrees/fix-recipe-model-field && go build ./projects/agent_platform/orchestrator/cmd/runner/...
```

**Step 3: Run Go tests locally**

```bash
cd /tmp/claude-worktrees/fix-recipe-model-field && go test ./projects/agent_platform/orchestrator/... -v -count=1
cd /tmp/claude-worktrees/fix-recipe-model-field && go test ./projects/agent_platform/orchestrator/cmd/runner/... -v -count=1
```

**Step 4: Render Helm chart to verify**

```bash
helm template agent-platform /tmp/claude-worktrees/fix-recipe-model-field/projects/agent_platform/chart/ -f /tmp/claude-worktrees/fix-recipe-model-field/projects/agent_platform/deploy/values.yaml
```

**Step 5: Fix any issues and commit**

```bash
git add -A && git commit -m "fix(agent-platform): resolve build issues from recipe path refactor"
```
