# Recipe-Driven Agent Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move goose recipes from baked-in image artifacts to orchestrator-managed data, served via ConfigMap and sent to runners over HTTP at dispatch time.

**Architecture:** Recipes are defined in Helm `values.yaml`, rendered into a ConfigMap mounted at `/etc/orchestrator/agents.json`. The orchestrator reads this file at startup, serves UI metadata via `GET /agents`, and sends rendered recipe YAML to runners in the `POST /run` request body. The runner writes the recipe to a temp file and passes it to `goose run --recipe`.

**Tech Stack:** Go (orchestrator + runner), Helm templates, JavaScript (frontend)

**Design doc:** `docs/plans/2026-03-12-recipe-driven-agents-design.md`

---

### Task 1: Add recipe content to AgentInfo model and config loader

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:25-46`
- Modify: `projects/agent_platform/orchestrator/main.go:224-237`
- Modify: `projects/agent_platform/orchestrator/main_test.go:109-150`

**Step 1: Update model types**

In `model.go`, add a `Recipe` field to `AgentInfo` and remove `ProfileInfo` / `AgentsResponse.Profiles`:

```go
// AgentInfo describes an available agent for the pipeline composer UI.
type AgentInfo struct {
	ID          string         `json:"id"`
	Label       string         `json:"label"`
	Icon        string         `json:"icon"`
	Background  string         `json:"bg"`
	Foreground  string         `json:"fg"`
	Description string         `json:"desc"`
	Category    string         `json:"category"`
	Recipe      map[string]any `json:"recipe,omitempty"`
}

// AgentsResponse is returned by GET /agents.
type AgentsResponse struct {
	Agents []AgentInfo `json:"agents"`
}
```

Remove the `ProfileInfo` struct entirely. Remove `ValidProfiles`.

**Step 2: Update loadAgentsConfig to return recipe map**

In `main.go`, change `loadAgentsConfig` to return `([]AgentInfo, map[string]map[string]any)` — the second return is a recipes map keyed by agent ID. The function reads the JSON, extracts the agents list, and builds the recipes map from each agent's `Recipe` field.

```go
func loadAgentsConfig(path string, logger *slog.Logger) ([]AgentInfo, map[string]map[string]any) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			logger.Info("no agents config file, pipeline composer will show empty agent list", "path", path)
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
	recipes := make(map[string]map[string]any, len(cfg.Agents))
	for _, a := range cfg.Agents {
		if a.Recipe != nil {
			recipes[a.ID] = a.Recipe
		}
	}
	logger.Info("loaded agents config", "path", path, "agents", len(cfg.Agents), "recipes", len(recipes))
	return cfg.Agents, recipes
}
```

**Step 3: Update main.go call site**

```go
agents, recipes := loadAgentsConfig(envOr("AGENTS_CONFIG_PATH", "/etc/orchestrator/agents.json"), logger)
```

Pass `recipes` to `NewAPI` (updated in Task 3).

**Step 4: Update tests in main_test.go**

Update `TestLoadAgentsConfig` to include a recipe field in the test JSON and verify the recipes map is populated. Update `TestLoadAgentsConfigMissing` and `TestLoadAgentsConfigInvalid` to check `nil` for the recipes map.

**Step 5: Run tests to verify**

Run: `cd projects/agent_platform/orchestrator && go vet ./...`
Expected: PASS (or only errors from downstream changes not yet made)

**Step 6: Commit**

```
feat(agent-orchestrator): add recipe field to AgentInfo, remove ValidProfiles
```

---

### Task 2: Update API to serve agents without profiles, store recipes

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go:22-46,229-251`
- Modify: `projects/agent_platform/orchestrator/api_test.go:387-504`

**Step 1: Update API struct**

Replace `profiles []ProfileInfo` with `recipes map[string]map[string]any` in the `API` struct. Update `NewAPI` signature:

```go
type API struct {
	store             Store
	publish           func(jobID string) error
	healthCheck       func() error
	defaultMaxRetries int
	agents            []AgentInfo
	recipes           map[string]map[string]any
	logger            *slog.Logger
}

func NewAPI(store Store, publish func(string) error, healthCheck func() error, defaultMaxRetries int, agents []AgentInfo, recipes map[string]map[string]any, logger *slog.Logger) *API {
	return &API{store: store, publish: publish, healthCheck: healthCheck, defaultMaxRetries: defaultMaxRetries, agents: agents, recipes: recipes, logger: logger}
}
```

**Step 2: Remove handleProfiles, update handleAgents**

Remove the `GET /profiles` route and `handleProfiles` handler. Update `handleAgents` to return `AgentsResponse` without profiles. Strip the `Recipe` field from the response (it's large and the frontend doesn't need it):

```go
func (a *API) handleAgents(w http.ResponseWriter, _ *http.Request) {
	agents := a.agents
	if agents == nil {
		agents = []AgentInfo{}
	}
	// Strip recipe content from response — frontend only needs UI metadata.
	stripped := make([]AgentInfo, len(agents))
	for i, ag := range agents {
		stripped[i] = ag
		stripped[i].Recipe = nil
	}
	a.writeJSON(w, http.StatusOK, AgentsResponse{Agents: stripped})
}
```

**Step 3: Update handleSubmit to validate agent ID instead of profile**

Replace the `ValidProfiles` check in `handleSubmit` with a check against `a.recipes`:

```go
if req.Profile != "" {
	if _, ok := a.recipes[req.Profile]; !ok {
		a.writeError(w, http.StatusBadRequest, "unknown agent: "+req.Profile)
		return
	}
}
```

Note: We keep using the `Profile` field in `SubmitRequest` and `JobRecord` for now — renaming it is a separate concern. The field now semantically means "agent ID".

**Step 4: Update newTestAPI helper**

In `api_test.go`, find `newTestAPI` and update it to pass `nil` for recipes instead of `nil, nil` for agents/profiles:

```go
func newTestAPI(store Store) (*API, *http.ServeMux) {
	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, nil, nil, logger)
	// ...
}
```

**Step 5: Update TestHandleAgents**

Remove profile assertions, add recipe stripping assertion:

```go
func TestHandleAgents(t *testing.T) {
	logger := slog.Default()
	agents := []AgentInfo{
		{ID: "ci-debug", Label: "CI Debug", Icon: "gear", Background: "#dbeafe", Foreground: "#1e40af", Description: "Debug CI", Category: "analyse", Recipe: map[string]any{"version": "1.0.0"}},
	}
	api := NewAPI(newMemStore(), nil, nil, 2, agents, map[string]map[string]any{"ci-debug": {"version": "1.0.0"}}, logger)
	// ... assert response has agents without recipe field, no profiles field
}
```

**Step 6: Remove TestHandleProfiles and TestValidProfilesMatchRecipeFiles**

Delete these tests — the endpoints/concepts they tested no longer exist.

**Step 7: Run tests**

Run: `cd projects/agent_platform/orchestrator && go vet ./...`

**Step 8: Commit**

```
refactor(agent-orchestrator): remove profiles endpoint, validate agent IDs from config
```

---

### Task 3: Add recipe rendering and update dispatch to send recipe YAML

**Files:**

- Modify: `projects/agent_platform/orchestrator/sandbox.go:259-288`
- Create: `projects/agent_platform/orchestrator/recipe.go`
- Create: `projects/agent_platform/orchestrator/recipe_test.go`

**Step 1: Write failing test for renderRecipe**

Create `recipe_test.go`:

```go
package main

import "testing"

func TestRenderRecipe_SimpleSubstitution(t *testing.T) {
	recipe := map[string]any{
		"prompt": "{{ task_description }}",
	}
	rendered, err := renderRecipeYAML(recipe, "fix the build")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(rendered, "fix the build") {
		t.Fatalf("expected rendered recipe to contain task, got:\n%s", rendered)
	}
	if strings.Contains(rendered, "{{ task_description }}") {
		t.Fatal("template variable was not replaced")
	}
}

func TestRenderRecipe_IndentFilter(t *testing.T) {
	recipe := map[string]any{
		"prompt": "{{ task_description | indent(2) }}",
	}
	rendered, err := renderRecipeYAML(recipe, "line1\nline2")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(rendered, "  line1\n  line2") {
		t.Fatalf("expected indented lines, got:\n%s", rendered)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd projects/agent_platform/orchestrator && go test -run TestRenderRecipe -v`
Expected: FAIL — `renderRecipeYAML` not defined

**Step 3: Implement renderRecipeYAML in recipe.go**

```go
package main

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

// indentRe matches {{ task_description | indent(N) }}.
var indentRe = regexp.MustCompile(`\{\{\s*task_description\s*\|\s*indent\((\d+)\)\s*\}\}`)

// renderRecipeYAML takes a recipe map, substitutes {{ task_description }}
// template variables with the given task, and returns the rendered YAML string.
func renderRecipeYAML(recipe map[string]any, task string) (string, error) {
	raw, err := yaml.Marshal(recipe)
	if err != nil {
		return "", fmt.Errorf("marshaling recipe: %w", err)
	}
	s := string(raw)

	// Replace {{ task_description | indent(N) }} first (more specific).
	s = indentRe.ReplaceAllStringFunc(s, func(match string) string {
		sub := indentRe.FindStringSubmatch(match)
		n, _ := strconv.Atoi(sub[1])
		prefix := strings.Repeat(" ", n)
		lines := strings.Split(task, "\n")
		for i := range lines {
			lines[i] = prefix + lines[i]
		}
		return strings.Join(lines, "\n")
	})

	// Replace plain {{ task_description }}.
	s = strings.ReplaceAll(s, "{{ task_description }}", task)

	return s, nil
}
```

**Step 4: Run tests**

Run: `cd projects/agent_platform/orchestrator && go test -run TestRenderRecipe -v`
Expected: PASS

**Step 5: Add recipe lookup method to API**

Add a method to look up and render a recipe:

```go
// RecipeYAML looks up the recipe for the given agent ID and renders the
// task_description template variable. Returns empty string if no recipe found.
func (a *API) RecipeYAML(agentID, task string) (string, error) {
	recipe, ok := a.recipes[agentID]
	if !ok {
		return "", nil
	}
	return renderRecipeYAML(recipe, task)
}
```

**Step 6: Update dispatchTask to send recipe instead of profile**

In `sandbox.go`, change the `dispatchTask` signature and payload:

```go
func (s *SandboxExecutor) dispatchTask(ctx context.Context, baseURL, task, recipe string) error {
	payload := struct {
		Task              string `json:"task"`
		Recipe            string `json:"recipe,omitempty"`
		InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
	}{
		Task:              task,
		Recipe:            recipe,
		InactivityTimeout: int(s.inactivityTimeout.Seconds()),
	}
	// ... rest unchanged
}
```

**Step 7: Update SandboxExecutor.Run signature**

Change `Run(ctx, claimName, task, profile, ...)` to `Run(ctx, claimName, task, recipe, ...)`:

```go
func (s *SandboxExecutor) Run(ctx context.Context, claimName, task, recipe string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
```

Update the `dispatchTask` call inside `Run`:

```go
if err := s.dispatchTask(ctx, baseURL, task, recipe); err != nil {
```

**Step 8: Update consumer to render recipe before dispatch**

In `consumer.go`, the call to `c.sandbox.Run` needs to pass a rendered recipe instead of `job.Profile`:

```go
// Look up and render recipe for this agent.
recipeYAML := ""
if job.Profile != "" {
	var err error
	recipeYAML, err = c.api.RecipeYAML(job.Profile, task)
	if err != nil {
		c.logger.Error("failed to render recipe", "agent", job.Profile, "error", err)
	}
}
r, err := c.sandbox.Run(jobCtx, claimName, task, recipeYAML, cancelFn, outputBuf)
```

The consumer needs access to the API's recipe lookup. Pass the API (or just the recipes map) to `NewConsumer`.

**Step 9: Update consumer_test.go fakeSandbox**

Update the `fakeSandbox.Run` signature to use `recipe string` instead of `profile string`.

**Step 10: Add yaml.v3 dependency if not already present**

Check if `gopkg.in/yaml.v3` is already a dependency:

Run: `grep 'yaml.v3' projects/agent_platform/orchestrator/go.mod`

If not present, add it.

**Step 11: Run all orchestrator tests**

Run: `cd projects/agent_platform/orchestrator && go vet ./...`

**Step 12: Commit**

```
feat(agent-orchestrator): render recipes and send to runners at dispatch
```

---

### Task 4: Update runner to accept recipe YAML

**Files:**

- Modify: `projects/agent_platform/orchestrator/cmd/runner/main.go:58-100,220-233,347-353`
- Modify: `projects/agent_platform/orchestrator/cmd/runner/main_test.go:221-303`

**Step 1: Update RunRequest**

Replace `Profile` with `Recipe`:

```go
type RunRequest struct {
	Task              string `json:"task"`
	Recipe            string `json:"recipe,omitempty"`
	InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
}
```

**Step 2: Update buildGooseCmd**

Write recipe to temp file when present:

```go
func buildGooseCmd(body RunRequest) ([]string, func()) {
	if body.Recipe != "" {
		f, err := os.CreateTemp("", "goose-recipe-*.yaml")
		if err != nil {
			log.Printf("failed to create temp recipe file: %v", err)
			return []string{"goose", "run", "--text", body.Task}, nil
		}
		f.WriteString(body.Recipe)
		f.Close()
		cleanup := func() { os.Remove(f.Name()) }
		return []string{
			"goose", "run",
			"--recipe", f.Name(),
			"--no-profile",
		}, cleanup
	}
	return []string{"goose", "run", "--text", body.Task}, nil
}
```

Note: the recipe is already rendered (template substituted) by the orchestrator, so no `--params` needed.

**Step 3: Update runGoose to call cleanup**

```go
args, cleanup := buildGooseCmd(body)
if cleanup != nil {
	defer cleanup()
}
```

**Step 4: Remove discoverProfiles, validProfiles, recipesDir, profileNames**

Delete these functions/variables and the `recipesDir` constant. Remove the `discoverProfiles` call from `main()`.

**Step 5: Update tests**

- `TestBuildGooseCmd_NoProfile` → `TestBuildGooseCmd_NoRecipe`: test with empty recipe, expect `--text` mode
- `TestBuildGooseCmd_WithProfile` → `TestBuildGooseCmd_WithRecipe`: test with recipe content, verify temp file is created and `--recipe` flag used
- Remove `TestBuildGooseCmd_UnknownProfile` (no longer applicable)
- Remove `TestDiscoverProfiles` and `TestDiscoverProfiles_MissingDir`

```go
func TestBuildGooseCmd_NoRecipe(t *testing.T) {
	args, cleanup := buildGooseCmd(RunRequest{Task: "fix the bug"})
	if cleanup != nil {
		defer cleanup()
	}
	expected := []string{"goose", "run", "--text", "fix the bug"}
	// ... assert args match expected
}

func TestBuildGooseCmd_WithRecipe(t *testing.T) {
	recipeYAML := "version: '1.0.0'\ntitle: Test\n"
	args, cleanup := buildGooseCmd(RunRequest{Task: "do it", Recipe: recipeYAML})
	if cleanup == nil {
		t.Fatal("expected cleanup function for temp file")
	}
	defer cleanup()

	if args[0] != "goose" || args[1] != "run" || args[2] != "--recipe" {
		t.Fatalf("unexpected args: %v", args)
	}
	// Verify temp file exists and contains recipe content.
	content, err := os.ReadFile(args[3])
	if err != nil {
		t.Fatalf("failed to read temp recipe: %v", err)
	}
	if string(content) != recipeYAML {
		t.Fatalf("expected recipe content %q, got %q", recipeYAML, string(content))
	}
}
```

**Step 6: Run runner tests**

Run: `cd projects/agent_platform/orchestrator/cmd/runner && go vet ./...`

**Step 7: Commit**

```
feat(agent-runner): accept recipe YAML over HTTP, remove filesystem profile discovery
```

---

### Task 5: Update Helm values with full recipe content

**Files:**

- Modify: `projects/agent_platform/chart/orchestrator/values.yaml:64-95`
- Modify: `projects/agent_platform/chart/values.yaml:110-133`

**Step 1: Add recipe content to subchart values**

Update `agentsConfig` in `projects/agent_platform/chart/orchestrator/values.yaml` to include full recipe YAML under each agent's `recipe` key. Copy the content from `projects/agent_platform/goose_agent/image/recipes/*.yaml` for each agent (ci-debug, code-fix, research, bazel).

Example for ci-debug:

```yaml
- id: ci-debug
  label: CI Debug
  icon: "..."
  bg: "#dbeafe"
  fg: "#1e40af"
  desc: Analyse CI/build failures using BuildBuddy logs
  category: analyse
  recipe:
    version: "1.0.0"
    title: "CI Debug"
    description: "Debug CI build failures using BuildBuddy tools"
    instructions: |
      You are debugging a CI build failure...
      (full content from ci-debug.yaml)
    prompt: |
      {{ task_description | indent(2) }}
    parameters:
      - key: task_description
        description: "The task to perform"
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
      max_turns: 50
      max_tool_repetitions: 5
```

**Step 2: Mirror to umbrella chart values**

Copy the same `agentsConfig` content to `projects/agent_platform/chart/values.yaml` under `agent-orchestrator.agentsConfig`.

**Step 3: Verify Helm renders correctly**

Run: `helm template test projects/agent_platform/chart/orchestrator/`
Verify the ConfigMap contains the full recipe content as JSON.

**Step 4: Commit**

```
feat(agent-platform): add full recipe content to Helm agent config
```

---

### Task 6: Remove recipes from goose-agent image build

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/BUILD:7-11,32-39,110-115,117-127`

**Step 1: Remove recipes_tar from image build**

In the `BUILD` file:

- Remove the `recipes_tar` `pkg_tar` rule (lines 32-39)
- Remove `:recipes_tar` from the `apko_image` `tars` list (line 113)
- Keep the `recipe_files` filegroup — it's still used by orchestrator tests
- Keep `recipe_validate_test` and `image_test` — they validate recipe YAML syntax

**Step 2: Verify build**

Run: `cd projects/agent_platform/goose_agent/image && bazel build :image` (or verify via `format`)

**Step 3: Commit**

```
refactor(goose-agent): remove baked-in recipes from container image
```

---

### Task 7: Clean up frontend

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/api.js:52-62`
- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx`

**Step 1: Remove listProfiles from api.js**

Delete the `listProfiles` function. Update `listAgents` return type comment:

```js
export async function listAgents() {
  const res = await fetch(`${API}/agents`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { agents: AgentInfo[] }
}
```

**Step 2: Remove profiles state from App.jsx**

Remove `profiles` state variable. Remove `profiles` prop from `PipelineComposer`. Update `listAgents` response destructuring (no more `.profiles`).

**Step 3: Update submitJob to use agent ID instead of profile**

In `api.js`, the `submitJob` function still sends `profile`. Keep this field name for backwards compatibility with the API — the orchestrator now treats it as "agent ID". No change needed.

**Step 4: Run format**

Run: `format` to ensure JS files are formatted.

**Step 5: Commit**

```
refactor(agent-orchestrator): clean up frontend, remove profiles references
```

---

### Task 8: Run format, verify Helm template, push

**Step 1: Run format**

Run: `format`

**Step 2: Verify full Helm render**

Run: `helm dependency update projects/agent_platform/chart/ && helm template agent-platform projects/agent_platform/chart/ -f projects/agent_platform/deploy/values.yaml > /dev/null`

**Step 3: Push and update PR**

```bash
git push
```

Verify CI passes via BuildBuddy.
