# Simplify Orchestrator UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Strip the pipeline composer UI and replace with simple submit + job history, add backend `/summarize` endpoint.

**Architecture:** The UI becomes a two-section page (submit textarea + job history list). The `PipelineFlow` horizontal visualization is kept but adapted to read from `job.plan[]` instead of grouped pipeline jobs. A new `POST /jobs/{id}/summarize` endpoint proxies to the in-cluster llama-cpp service for title/summary generation.

**Tech Stack:** React 19 + Vite (frontend), Go net/http (backend), llama-cpp OpenAI-compatible API (inference)

---

### Task 1: Backend — Add summarize endpoint model + handler

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go`
- Modify: `projects/agent_platform/orchestrator/api.go`

**Step 1: Add SummarizeResponse to model.go**

Add after the `OutputResponse` struct (line 95):

```go
// SummarizeResponse is returned by POST /jobs/{id}/summarize.
type SummarizeResponse struct {
	Title   string `json:"title"`
	Summary string `json:"summary"`
}
```

**Step 2: Add inferenceURL field and summarize handler to api.go**

Add `inferenceURL` field to the `API` struct and update `NewAPI`:

```go
type API struct {
	store             Store
	publish           func(jobID string) error
	healthCheck       func() error
	defaultMaxRetries int
	inferenceURL      string
	logger            *slog.Logger
}

func NewAPI(store Store, publish func(string) error, healthCheck func() error, defaultMaxRetries int, inferenceURL string, logger *slog.Logger) *API {
	return &API{store: store, publish: publish, healthCheck: healthCheck, defaultMaxRetries: defaultMaxRetries, inferenceURL: inferenceURL, logger: logger}
}
```

Register the route in `RegisterRoutes`:

```go
mux.HandleFunc("POST /jobs/{id}/summarize", a.handleSummarize)
```

Add the handler:

```go
func (a *API) handleSummarize(w http.ResponseWriter, r *http.Request) {
	if a.inferenceURL == "" {
		a.writeError(w, http.StatusServiceUnavailable, "inference not configured")
		return
	}

	id := r.PathValue("id")
	job, err := a.store.Get(r.Context(), id)
	if err != nil || job == nil {
		a.writeError(w, http.StatusNotFound, "job not found")
		return
	}

	if len(job.Plan) == 0 {
		a.writeError(w, http.StatusUnprocessableEntity, "job has no plan")
		return
	}

	// Build prompt from task + plan steps.
	var sb strings.Builder
	sb.WriteString("Task: ")
	sb.WriteString(job.Task)
	sb.WriteString("\n\nPlan steps:\n")
	for i, step := range job.Plan {
		fmt.Fprintf(&sb, "%d. [%s] %s (status: %s)\n", i+1, step.Agent, step.Description, step.Status)
	}

	chatReq := map[string]any{
		"model": "qwen3.5-35b-a3b",
		"messages": []map[string]string{
			{"role": "system", "content": "You summarize agent pipeline jobs. Given a task and its plan steps, produce a JSON object with: title (concise, under 10 words) and summary (1-2 sentence overview). Return ONLY valid JSON."},
			{"role": "user", "content": sb.String()},
		},
		"temperature": 0.3,
		"max_tokens":  256,
		"response_format": map[string]any{
			"type": "json_schema",
			"json_schema": map[string]any{
				"name":   "summary",
				"strict": true,
				"schema": map[string]any{
					"type":                 "object",
					"required":             []string{"title", "summary"},
					"additionalProperties": false,
					"properties": map[string]any{
						"title":   map[string]string{"type": "string"},
						"summary": map[string]string{"type": "string"},
					},
				},
			},
		},
	}

	body, err := json.Marshal(chatReq)
	if err != nil {
		a.writeError(w, http.StatusInternalServerError, "failed to build request")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, a.inferenceURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		a.writeError(w, http.StatusInternalServerError, "failed to create request")
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		a.logger.Error("inference request failed", "error", err)
		a.writeError(w, http.StatusBadGateway, "inference unavailable")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		a.logger.Error("inference returned non-200", "status", resp.StatusCode)
		a.writeError(w, http.StatusBadGateway, "inference error")
		return
	}

	var chatResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		a.writeError(w, http.StatusBadGateway, "failed to parse inference response")
		return
	}

	if len(chatResp.Choices) == 0 {
		a.writeError(w, http.StatusBadGateway, "no choices in inference response")
		return
	}

	var result SummarizeResponse
	if err := json.Unmarshal([]byte(chatResp.Choices[0].Message.Content), &result); err != nil {
		a.logger.Error("failed to parse summary JSON", "content", chatResp.Choices[0].Message.Content, "error", err)
		a.writeError(w, http.StatusBadGateway, "invalid summary format")
		return
	}

	a.writeJSON(w, http.StatusOK, result)
}
```

**Step 3: Update main.go to pass INFERENCE_URL**

In `main.go`, read the env var and pass to `NewAPI`:

```go
inferenceURL := envOr("INFERENCE_URL", "")
```

Update the `NewAPI` call to include `inferenceURL`.

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/model.go projects/agent_platform/orchestrator/api.go projects/agent_platform/orchestrator/main.go
git commit -m "feat(orchestrator): add POST /jobs/{id}/summarize endpoint"
```

---

### Task 2: Backend — Add summarize endpoint tests

**Files:**

- Modify: `projects/agent_platform/orchestrator/api_test.go`

**Step 1: Update newTestAPI to match new signature**

The `NewAPI` call in `newTestAPI` (line 83) needs the new `inferenceURL` parameter:

```go
func newTestAPI(store Store) (*API, *http.ServeMux) {
	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)
	return api, mux
}
```

Also update `TestHandleSubmit_WithProfile` which creates its own `NewAPI` (line 121).

**Step 2: Add test for summarize with no inference URL**

```go
func TestHandleSummarize_NoInference(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["SUM1"] = &JobRecord{
		ID: "SUM1", Task: "deploy service", Status: JobSucceeded,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
		Plan: []PlanStep{{Agent: "planner", Description: "analyze repo", Status: "completed"}},
	}

	_, mux := newTestAPI(store) // inferenceURL is ""

	req := httptest.NewRequest(http.MethodPost, "/jobs/SUM1/summarize", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d: %s", rec.Code, rec.Body.String())
	}
}
```

**Step 3: Add test for summarize with no plan**

```go
func TestHandleSummarize_NoPlan(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["SUM2"] = &JobRecord{
		ID: "SUM2", Task: "simple job", Status: JobSucceeded,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, "http://fake-llm:8080", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodPost, "/jobs/SUM2/summarize", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422, got %d: %s", rec.Code, rec.Body.String())
	}
}
```

**Step 4: Add test for summarize with mock LLM server**

```go
func TestHandleSummarize_Success(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["SUM3"] = &JobRecord{
		ID: "SUM3", Task: "deploy auth service", Status: JobSucceeded,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
		Plan: []PlanStep{
			{Agent: "planner", Description: "analyze requirements", Status: "completed"},
			{Agent: "coder", Description: "implement changes", Status: "completed"},
		},
	}

	// Mock LLM server
	llm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"choices": []map[string]any{
				{"message": map[string]string{"content": `{"title":"Deploy auth service","summary":"Analyzed requirements and implemented auth service deployment."}`}},
			},
		})
	}))
	defer llm.Close()

	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, llm.URL, logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodPost, "/jobs/SUM3/summarize", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp SummarizeResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Title != "Deploy auth service" {
		t.Fatalf("expected title 'Deploy auth service', got %q", resp.Title)
	}
}
```

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/api_test.go
git commit -m "test(orchestrator): add summarize endpoint tests"
```

---

### Task 3: Backend — Add INFERENCE_URL to Helm chart

**Files:**

- Modify: `projects/agent_platform/chart/orchestrator/values.yaml`
- Modify: `projects/agent_platform/chart/orchestrator/templates/deployment.yaml`
- Modify: `projects/agent_platform/chart/orchestrator/Chart.yaml`
- Modify: `projects/agent_platform/orchestrator/deploy/application.yaml` (targetRevision sync)

**Step 1: Add inferenceUrl to values.yaml config section**

Add to the `config:` block after `reconcileInterval`:

```yaml
inferenceUrl: ""
```

**Step 2: Add env var to deployment.yaml**

Add after the `RECONCILE_INTERVAL` env var (line 60):

```yaml
- name: INFERENCE_URL
  value: { { .Values.config.inferenceUrl | quote } }
```

**Step 3: Set the inference URL in deploy/values.yaml**

Add to `projects/agent_platform/deploy/values.yaml` under the orchestrator section:

```yaml
orchestrator:
  config:
    inferenceUrl: "http://llama-cpp.llama-cpp.svc.cluster.local:8080"
```

Check the actual deploy values file structure first to determine the exact path.

**Step 4: Bump Chart.yaml version + update application.yaml targetRevision**

Bump the patch version in `projects/agent_platform/chart/orchestrator/Chart.yaml` and update `targetRevision` in `projects/agent_platform/orchestrator/deploy/application.yaml` to match.

**Step 5: Commit**

```bash
git add projects/agent_platform/chart/orchestrator/ projects/agent_platform/orchestrator/deploy/ projects/agent_platform/deploy/
git commit -m "feat(orchestrator): add INFERENCE_URL config to Helm chart"
```

---

### Task 4: Frontend — Simplify api.js

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/api.js`

**Step 1: Remove listAgents and submitPipeline, add summarizeJob**

Rewrite `api.js` to:

```js
const API = "";

export async function listJobs({ status, tags, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (tags) params.set("tags", tags);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const res = await fetch(`${API}/jobs?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJob(id) {
  const res = await fetch(`${API}/jobs/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitJob(task) {
  const res = await fetch(`${API}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, source: "dashboard" }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelJob(id) {
  const res = await fetch(`${API}/jobs/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJobOutput(id) {
  const res = await fetch(`${API}/jobs/${id}/output`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function summarizeJob(id) {
  const res = await fetch(`${API}/jobs/${id}/summarize`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/api.js
git commit -m "refactor(orchestrator-ui): simplify api.js, add summarizeJob"
```

---

### Task 5: Frontend — Delete unused files

**Files:**

- Delete: `projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx`
- Delete: `projects/agent_platform/orchestrator/ui/src/pipeline-config.js`

**Step 1: Delete files**

```bash
rm projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx
rm projects/agent_platform/orchestrator/ui/src/pipeline-config.js
```

**Step 2: Commit**

```bash
git add -A projects/agent_platform/orchestrator/ui/src/PipelineComposer.jsx projects/agent_platform/orchestrator/ui/src/pipeline-config.js
git commit -m "refactor(orchestrator-ui): remove PipelineComposer and pipeline-config"
```

---

### Task 6: Frontend — Rewrite App.jsx

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx`

This is the largest task. The new `App.jsx` should contain:

**Keep as-is:**

- `POLL_INTERVAL`, `STATUS_META` constants
- `timeAgo()`, `elapsed()`, `getResult()` utils
- `GitHubIcon`, `ChevronDown`, `Dot`, `ResultPill` components

**Adapt PipelineFlow:**

- Instead of accepting `jobs` (grouped pipeline jobs) and `agents`, accept `plan` (array of `PlanStep`) and `currentStep` (int).
- Each pill shows the agent name + status dot based on `step.status` (mapped: `completed→SUCCEEDED`, `running→RUNNING`, `failed→FAILED`, `skipped→SKIPPED`, `pending→PENDING`).

**New SubmitBar component:**

- Textarea + submit button
- Calls `submitJob(task)` on submit
- Disables button while submitting

**Adapt JobRow:**

- Remove `onApplyPipeline` prop and "Apply pipeline" button
- Remove `agents` prop (no longer needed)
- When `job.plan?.length > 0`, show PipelineFlow below the task title
- Add LLM summary display: if summary is available from cache, show title in the row and summary in expanded view

**Adapt JobList:**

- Remove `groupJobs()`, `PipelineRow`, `PipelineDetail`, `derivePipelineSummary` — jobs are no longer grouped by pipeline_id
- Remove `agents` and `onApplyPipeline` props
- Remove BLOCKED/SKIPPED from status filter (these are step-level, not job-level)

**Adapt App:**

- Remove all `agents` state and `listAgents` fetch
- Remove all deep plan state (`deepPlanJobId`, `deepPlanStatus`, `deepPlanResult`, `analysisUrl`)
- Remove `handlePipelineSubmit`, `handleDeepPlan`, `handleApplyPipeline`
- Remove `PipelineComposer` import
- Remove `CONDITION_STYLES` import
- Add simple `handleSubmit` that calls `submitJob(task)`
- Add `summaryCache` state (Map of jobId → {title, summary})
- Add effect that calls `summarizeJob` for jobs with plan but no cached summary
- Render: `<SubmitBar>` then `<JobList>`

**Step 1: Write the new App.jsx**

The full rewrite. See design doc for the data flow. Key structure:

```jsx
import { useState, useEffect, useCallback, useRef } from "react";
import { listJobs, submitJob, cancelJob, summarizeJob } from "./api.js";

// Constants, utils, icon components (keep existing)
// ...

// Adapted PipelineFlow — reads job.plan[]
function PipelineFlow({ plan, currentStep }) {
  /* ... */
}

// New simple submit bar
function SubmitBar({ onSubmit }) {
  /* ... */
}

// Adapted JobRow — shows plan flow inline, uses summary cache
function JobRow({ job, summary, onCancel, isMobile }) {
  /* ... */
}

// Simplified JobList — flat list, no pipeline grouping
function JobList({ jobs, summaries, onCancel, isMobile }) {
  /* ... */
}

// App — simple submit + polled job list + summary cache
export default function App() {
  /* ... */
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "feat(orchestrator-ui): simplify to submit + job history with plan flow"
```

---

### Task 7: Verify — Render Helm templates + format

**Step 1: Run format to update BUILD files**

```bash
format
```

**Step 2: Render helm templates to check for errors**

```bash
helm template agent-platform projects/agent_platform/chart/orchestrator/ -f projects/agent_platform/chart/orchestrator/values.yaml
```

**Step 3: Commit any formatting changes**

```bash
git add -A && git commit -m "style: format and update BUILD files"
```

---

### Task 8: Push and create PR

**Step 1: Push branch**

```bash
git push -u origin feat/simplify-orchestrator-ui
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(orchestrator): simplify UI to submit + job history" --body "$(cat <<'EOF'
## Summary
- Strip pipeline composer (@ mentions, agent picker, fast infer/deep plan buttons, drag-and-drop)
- Simplify to textarea submit + job history list
- Keep horizontal pipeline flow visualization, adapted to read from `job.plan[]`
- Add `POST /jobs/{id}/summarize` backend endpoint (proxies to llama-cpp for title + summary)
- Client-side summary caching for efficient LLM usage

## Test plan
- [ ] Backend: summarize endpoint tests pass in CI
- [ ] UI: submit a job and verify it appears in history
- [ ] UI: job with plan shows horizontal flow with agent pills
- [ ] UI: summaries load for jobs with plans
- [ ] UI: cancel button works for pending/running jobs
- [ ] Helm: template renders without errors

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
