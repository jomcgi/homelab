# Backend-Driven Job Summarization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move LLM-generated job summaries from UI-triggered (per-refresh) to backend lifecycle events in the consumer loop, persisted in JobRecord.

**Architecture:** New `Summarizer` struct in `summarizer.go` wraps the OpenAI-compatible LLM call. Consumer calls it at four lifecycle points (submit, plan available, every 5m, terminal). Title/Summary stored in `JobRecord` NATS KV. UI reads from job record directly; the `/summarize` endpoint and client-side summary state are removed.

**Tech Stack:** Go (backend), React/JSX (UI), NATS KV (storage), OpenAI-compatible inference API

---

### Task 1: Add Title and Summary fields to JobRecord

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:17-38`
- Modify: `projects/agent_platform/orchestrator/model.go:96-100` (delete `SummarizeResponse`)

**Step 1: Add fields to JobRecord**

In `model.go`, add `Title` and `Summary` fields to `JobRecord` after the `FailureSummary` field (line 31):

```go
	// LLM-generated summary fields, populated by the backend summarizer.
	Title   string `json:"title,omitempty"`
	Summary string `json:"summary,omitempty"`
```

**Step 2: Delete SummarizeResponse**

Remove the `SummarizeResponse` type (lines 96-100):

```go
// SummarizeResponse is returned by POST /jobs/{id}/summarize.
type SummarizeResponse struct {
	Title   string `json:"title"`
	Summary string `json:"summary"`
}
```

**Step 3: Run format**

Run: `format`

This regenerates BUILD files and formats code.

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/model.go
git commit -m "feat(orchestrator): add Title and Summary fields to JobRecord"
```

---

### Task 2: Create Summarizer component

**Files:**

- Create: `projects/agent_platform/orchestrator/summarizer.go`
- Test: `projects/agent_platform/orchestrator/summarizer_test.go`

**Step 1: Write the failing tests**

Create `summarizer_test.go`:

```go
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSummarizer_SummarizeTask(t *testing.T) {
	llm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req map[string]any
		json.NewDecoder(r.Body).Decode(&req)

		msgs := req["messages"].([]any)
		userMsg := msgs[1].(map[string]any)["content"].(string)
		if userMsg == "" {
			t.Error("expected non-empty user message")
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"choices": []map[string]any{
				{"message": map[string]string{"content": `{"title":"Deploy Auth Service"}`}},
			},
		})
	}))
	defer llm.Close()

	s := NewSummarizer(llm.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "Please deploy the auth service to production with the new OAuth2 configuration")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title != "Deploy Auth Service" {
		t.Errorf("title = %q, want %q", title, "Deploy Auth Service")
	}
}

func TestSummarizer_SummarizePlan(t *testing.T) {
	llm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"choices": []map[string]any{
				{"message": map[string]string{"content": `{"title":"Deploy Auth","summary":"Deploying auth service: 2 of 3 steps complete."}`}},
			},
		})
	}))
	defer llm.Close()

	s := NewSummarizer(llm.URL, "test-model", slog.Default())
	plan := []PlanStep{
		{Agent: "planner", Description: "Analyze repo", Status: "completed"},
		{Agent: "coder", Description: "Write code", Status: "completed"},
		{Agent: "reviewer", Description: "Review changes", Status: "running"},
	}
	title, summary, err := s.SummarizePlan(context.Background(), "deploy auth service", plan)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title != "Deploy Auth" {
		t.Errorf("title = %q, want %q", title, "Deploy Auth")
	}
	if summary == "" {
		t.Error("expected non-empty summary")
	}
}

func TestSummarizer_NilSafe(t *testing.T) {
	var s *Summarizer
	title, err := s.SummarizeTask(context.Background(), "test")
	if err != nil {
		t.Fatalf("nil summarizer should not error: %v", err)
	}
	if title != "" {
		t.Errorf("nil summarizer should return empty title, got %q", title)
	}

	title2, summary, err := s.SummarizePlan(context.Background(), "test", nil)
	if err != nil {
		t.Fatalf("nil summarizer should not error: %v", err)
	}
	if title2 != "" || summary != "" {
		t.Errorf("nil summarizer should return empty strings")
	}
}

func TestSummarizer_EmptyInferenceURL(t *testing.T) {
	s := NewSummarizer("", "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "test")
	if err != nil {
		t.Fatalf("empty URL should not error: %v", err)
	}
	if title != "" {
		t.Errorf("empty URL should return empty title, got %q", title)
	}
}

func TestSummarizer_LLMError(t *testing.T) {
	llm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer llm.Close()

	s := NewSummarizer(llm.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "test task")
	if err == nil {
		t.Fatal("expected error from failed LLM call")
	}
	if title != "" {
		t.Errorf("expected empty title on error, got %q", title)
	}
}
```

**Step 2: Run tests to verify they fail**

Run: `format` (to generate BUILD file updates)

Tests will fail with "undefined: NewSummarizer" since the implementation doesn't exist yet.

**Step 3: Write the Summarizer implementation**

Create `summarizer.go`:

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// Summarizer generates titles and summaries for jobs via an LLM inference endpoint.
// All methods are nil-safe: if the receiver is nil or inferenceURL is empty, they return
// zero values without error.
type Summarizer struct {
	inferenceURL string
	model        string
	logger       *slog.Logger
}

// NewSummarizer creates a Summarizer targeting the given OpenAI-compatible inference endpoint.
func NewSummarizer(inferenceURL, model string, logger *slog.Logger) *Summarizer {
	return &Summarizer{inferenceURL: inferenceURL, model: model, logger: logger}
}

// SummarizeTask generates a clean title from a raw task string.
func (s *Summarizer) SummarizeTask(ctx context.Context, task string) (string, error) {
	if s == nil || s.inferenceURL == "" {
		return "", nil
	}

	systemPrompt := "You generate short titles for agent tasks. Respond with JSON containing \"title\" (max 10 words, no quotes around it)."
	userPrompt := "Task: " + task

	result, err := s.callLLM(ctx, systemPrompt, userPrompt, []string{"title"})
	if err != nil {
		return "", err
	}
	return result["title"], nil
}

// SummarizePlan generates a title and summary from a task and its plan steps.
func (s *Summarizer) SummarizePlan(ctx context.Context, task string, plan []PlanStep) (string, string, error) {
	if s == nil || s.inferenceURL == "" {
		return "", "", nil
	}

	var sb strings.Builder
	sb.WriteString("Job task: ")
	sb.WriteString(task)
	sb.WriteString("\n\nPlan steps:\n")
	for i, step := range plan {
		fmt.Fprintf(&sb, "%d. [%s] %s (agent: %s)\n", i+1, step.Status, step.Description, step.Agent)
	}

	systemPrompt := "You summarize agent job plans. Respond with JSON containing \"title\" (short, max 10 words) and \"summary\" (1-2 sentences)."
	result, err := s.callLLM(ctx, systemPrompt, sb.String(), []string{"title", "summary"})
	if err != nil {
		return "", "", err
	}
	return result["title"], result["summary"], nil
}

func (s *Summarizer) callLLM(ctx context.Context, systemPrompt, userPrompt string, fields []string) (map[string]string, error) {
	properties := make(map[string]any, len(fields))
	for _, f := range fields {
		properties[f] = map[string]string{"type": "string"}
	}

	reqBody := map[string]any{
		"model": s.model,
		"messages": []map[string]string{
			{"role": "system", "content": systemPrompt},
			{"role": "user", "content": userPrompt},
		},
		"temperature": 0.3,
		"max_tokens":  256,
		"response_format": map[string]any{
			"type": "json_schema",
			"json_schema": map[string]any{
				"name":   "summary_response",
				"strict": true,
				"schema": map[string]any{
					"type":                 "object",
					"properties":           properties,
					"required":             fields,
					"additionalProperties": false,
				},
			},
		},
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	callCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(callCtx, http.MethodPost, s.inferenceURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("inference request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("inference returned %d", resp.StatusCode)
	}

	var chatResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	if len(chatResp.Choices) == 0 {
		return nil, fmt.Errorf("no choices in response")
	}

	var result map[string]string
	if err := json.Unmarshal([]byte(chatResp.Choices[0].Message.Content), &result); err != nil {
		s.logger.Error("failed to parse summary JSON", "content", chatResp.Choices[0].Message.Content, "error", err)
		return nil, fmt.Errorf("parse summary JSON: %w", err)
	}

	return result, nil
}
```

**Step 4: Run format and verify tests pass**

Run: `format`

All 5 tests should pass.

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/summarizer.go projects/agent_platform/orchestrator/summarizer_test.go
git commit -m "feat(orchestrator): add Summarizer component for LLM-driven title/summary generation"
```

---

### Task 3: Wire Summarizer into Consumer

**Files:**

- Modify: `projects/agent_platform/orchestrator/consumer.go:44-64` (Consumer struct + constructor)
- Modify: `projects/agent_platform/orchestrator/consumer.go:101-269` (processJob method)
- Modify: `projects/agent_platform/orchestrator/consumer_test.go:63-65` (newTestConsumer helper)

**Step 1: Add Summarizer to Consumer struct**

In `consumer.go`, add a `summarizer` field to the `Consumer` struct (after line 51):

```go
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	publish     func(jobID string) error
	summarizer  *Summarizer
	maxDuration time.Duration
	logger      *slog.Logger
}
```

Update `NewConsumer` to accept a `*Summarizer` parameter:

```go
func NewConsumer(cons jetstream.Consumer, store Store, sandbox Sandbox, publish func(jobID string) error, summarizer *Summarizer, maxDuration time.Duration, logger *slog.Logger) *Consumer {
	return &Consumer{
		cons:        cons,
		store:       store,
		sandbox:     sandbox,
		publish:     publish,
		summarizer:  summarizer,
		maxDuration: maxDuration,
		logger:      logger,
	}
}
```

**Step 2: Add summary triggers to processJob**

In `processJob`, add the four triggers. The changes are relative to the existing method:

**Trigger 1 — After setting RUNNING (after line 141):**

```go
	// Trigger 1: Generate clean title from raw task.
	if title, err := c.summarizer.SummarizeTask(jobCtx, job.Task); err != nil {
		logger.Warn("summarize task failed", "error", err)
	} else if title != "" {
		job.Title = title
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Warn("failed to store title", "error", err)
		}
	}
```

**Trigger 2 + 3 — In the ticker loop, replace the existing `case <-ticker.C` (lines 183-185):**

```go
	planSummarized := false
	var lastSummarizedAt time.Time

	// ...existing resultCh goroutine...

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	var res sandboxResult
loop:
	for {
		select {
		case res = <-resultCh:
			break loop
		case <-ticker.C:
			_ = msg.InProgress()
			c.flushProgress(jobCtx, jobID, outputBuf, planBuf)

			// Trigger 2: First plan summary (once).
			if plan, _ := planBuf.Get(); len(plan) > 0 && !planSummarized {
				planSummarized = true
				c.summarizeAndStore(jobCtx, jobID, job.Task, plan, logger)
				lastSummarizedAt = time.Now()
			}

			// Trigger 3: Periodic summary update (every 5m).
			if plan, _ := planBuf.Get(); len(plan) > 0 && planSummarized && time.Since(lastSummarizedAt) >= 5*time.Minute {
				c.summarizeAndStore(jobCtx, jobID, job.Task, plan, logger)
				lastSummarizedAt = time.Now()
			}
		}
	}
```

**Trigger 4 — Before the final store.Put for SUCCEEDED/FAILED.** Add after setting `job.Status = JobFailed` or `JobSucceeded`, before the `store.Put` call:

In the failed path (after line 255 `job.Status = JobFailed`):

```go
	if len(job.Plan) > 0 {
		c.summarizeAndStoreOnJob(jobCtx, job, logger)
	}
```

In the succeeded path (after line 264 `job.Status = JobSucceeded`):

```go
	if len(job.Plan) > 0 {
		c.summarizeAndStoreOnJob(jobCtx, job, logger)
	}
```

**Step 3: Add helper methods to Consumer**

Add these at the end of `consumer.go`:

```go
// summarizeAndStore reads the current job from the store, generates a summary, and writes it back.
// Used during the ticker loop when we don't have a fresh job reference.
func (c *Consumer) summarizeAndStore(ctx context.Context, jobID, task string, plan []PlanStep, logger *slog.Logger) {
	title, summary, err := c.summarizer.SummarizePlan(ctx, task, plan)
	if err != nil {
		logger.Warn("summarize plan failed", "error", err)
		return
	}
	if title == "" && summary == "" {
		return
	}

	current, err := c.store.Get(ctx, jobID)
	if err != nil {
		logger.Warn("failed to read job for summary update", "error", err)
		return
	}
	if title != "" {
		current.Title = title
	}
	if summary != "" {
		current.Summary = summary
	}
	if err := c.store.Put(ctx, current); err != nil {
		logger.Warn("failed to store summary", "error", err)
	}
}

// summarizeAndStoreOnJob generates a summary and writes it directly to the provided job record.
// Used at terminal state when we already have the job in hand.
func (c *Consumer) summarizeAndStoreOnJob(ctx context.Context, job *JobRecord, logger *slog.Logger) {
	title, summary, err := c.summarizer.SummarizePlan(ctx, job.Task, job.Plan)
	if err != nil {
		logger.Warn("summarize plan (terminal) failed", "error", err)
		return
	}
	if title != "" {
		job.Title = title
	}
	if summary != "" {
		job.Summary = summary
	}
}
```

**Step 4: Update test helper**

In `consumer_test.go`, update `newTestConsumer` to pass `nil` for the summarizer:

```go
func newTestConsumer(store Store, sandbox Sandbox) *Consumer {
	return NewConsumer(nil, store, sandbox, nil, nil, 5*time.Minute, slog.Default())
}
```

**Step 5: Write a test for summarization during processJob**

Add to `consumer_test.go`:

```go
func TestProcessJob_SummarizesOnCompletion(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUMMARIZE")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	llm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"choices": []map[string]any{
				{"message": map[string]string{"content": `{"title":"Run Tests"}`}},
			},
		})
	}))
	defer llm.Close()

	summarizer := NewSummarizer(llm.URL, "test-model", slog.Default())

	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 0, Output: "done"}, nil
		},
	}

	c := NewConsumer(nil, store, sandbox, nil, summarizer, 5*time.Minute, slog.Default())
	c.processJob(context.Background(), msg)

	got, _ := store.Get(context.Background(), job.ID)
	if got.Title != "Run Tests" {
		t.Errorf("expected title 'Run Tests', got %q", got.Title)
	}
}

func TestProcessJob_SummarizesWithNilSummarizer(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-NIL-SUMMARIZER")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{}

	c := NewConsumer(nil, store, sandbox, nil, nil, 5*time.Minute, slog.Default())
	c.processJob(context.Background(), msg)

	got, _ := store.Get(context.Background(), job.ID)
	if got.Status != JobSucceeded {
		t.Errorf("expected SUCCEEDED, got %s", got.Status)
	}
	// Title should remain empty when summarizer is nil.
	if got.Title != "" {
		t.Errorf("expected empty title with nil summarizer, got %q", got.Title)
	}
}
```

Add these imports to the test file's import block: `"encoding/json"`, `"log/slog"`, `"net/http"`, `"net/http/httptest"`.

**Step 6: Run format and verify tests pass**

Run: `format`

All existing and new tests should pass.

**Step 7: Commit**

```bash
git add projects/agent_platform/orchestrator/consumer.go projects/agent_platform/orchestrator/consumer_test.go
git commit -m "feat(orchestrator): wire Summarizer into consumer lifecycle triggers"
```

---

### Task 4: Wire Summarizer in main.go and remove inferenceURL from API

**Files:**

- Modify: `projects/agent_platform/orchestrator/main.go:111-137`
- Modify: `projects/agent_platform/orchestrator/api.go:24-47` (API struct, NewAPI, RegisterRoutes)
- Modify: `projects/agent_platform/orchestrator/api_test.go:81-87` (newTestAPI helper)

**Step 1: Create Summarizer in main.go and pass to consumer**

In `main.go`, replace lines 111-137:

```go
	inferenceURL := envOr("INFERENCE_URL", "")
	inferenceModel := envOr("INFERENCE_MODEL", "qwen3.5-35b-a3b")

	var summarizer *Summarizer
	if inferenceURL != "" {
		summarizer = NewSummarizer(inferenceURL, inferenceModel, logger)
		logger.Info("summarizer enabled", "url", inferenceURL, "model", inferenceModel)
	}

	api := NewAPI(store, publish, healthCheck, maxRetries, logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)
	registerUI(mux)

	// ... existing server setup ...

	// Start consumer if sandbox is available.
	if sandbox != nil {
		consumer := NewConsumer(cons, store, sandbox, publish, summarizer, maxDuration, logger)
		go consumer.Run(ctx)
	} else {
		logger.Info("running in API-only mode (no sandbox executor)")
	}
```

**Step 2: Remove inferenceURL from API struct**

In `api.go`, remove `inferenceURL` from the `API` struct and `NewAPI`:

```go
type API struct {
	store             Store
	publish           func(jobID string) error
	healthCheck       func() error
	defaultMaxRetries int
	logger            *slog.Logger
}

func NewAPI(store Store, publish func(string) error, healthCheck func() error, defaultMaxRetries int, logger *slog.Logger) *API {
	return &API{store: store, publish: publish, healthCheck: healthCheck, defaultMaxRetries: defaultMaxRetries, logger: logger}
}
```

**Step 3: Update newTestAPI in api_test.go**

```go
func newTestAPI(store Store) (*API, *http.ServeMux) {
	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)
	return api, mux
}
```

**Step 4: Run format and verify tests pass**

Run: `format`

Note: The summarize-related tests (`TestHandleSummarize_*`) will fail because the endpoint still exists but `inferenceURL` is removed. We'll fix that in the next task.

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/main.go projects/agent_platform/orchestrator/api.go projects/agent_platform/orchestrator/api_test.go
git commit -m "refactor(orchestrator): move inferenceURL from API to Summarizer, wire into consumer"
```

---

### Task 5: Remove the /summarize endpoint and tests

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go:39-47` (RegisterRoutes)
- Modify: `projects/agent_platform/orchestrator/api.go:232-340` (delete handleSummarize)
- Modify: `projects/agent_platform/orchestrator/api_test.go:316-401` (delete summarize tests)

**Step 1: Remove the route from RegisterRoutes**

In `api.go`, remove this line from `RegisterRoutes`:

```go
	mux.HandleFunc("POST /jobs/{id}/summarize", a.handleSummarize)
```

**Step 2: Delete handleSummarize method**

Delete the entire `handleSummarize` method from `api.go` (lines 232-340).

**Step 3: Delete summarize tests**

Delete `TestHandleSummarize_NoInference`, `TestHandleSummarize_NoPlan`, and `TestHandleSummarize_Success` from `api_test.go`.

Also update the test for `TestHandleSummarize_NoPlan` reference — it creates an API with `inferenceURL` parameter which no longer exists. Remove the entire test.

**Step 4: Clean up unused imports**

After removing `handleSummarize`, these imports in `api.go` may become unused: `"bytes"`, `"context"`, `"fmt"`. Remove any that the compiler flags.

**Step 5: Run format and verify tests pass**

Run: `format`

All remaining tests should pass.

**Step 6: Commit**

```bash
git add projects/agent_platform/orchestrator/api.go projects/agent_platform/orchestrator/api_test.go
git commit -m "fix(orchestrator): remove /summarize endpoint, replaced by backend lifecycle summarization"
```

---

### Task 6: Update UI to read from job record

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/api.js:42-46` (delete summarizeJob)
- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx` (multiple locations)

**Step 1: Delete summarizeJob from api.js**

Remove the `summarizeJob` function (lines 42-46):

```js
export async function summarizeJob(id) {
  const res = await fetch(`${API}/jobs/${id}/summarize`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

**Step 2: Remove summary state and useEffect from App.jsx**

In `App.jsx`, remove:

1. The import of `summarizeJob` from line 2:

   ```js
   import { listJobs, submitJob, cancelJob } from "./api.js";
   ```

2. The `summaries` state (line 709):

   ```js
   const [summaries, setSummaries] = useState(new Map());
   ```

3. The `pendingSummaries` ref (line 714):

   ```js
   const pendingSummaries = useRef(new Set());
   ```

4. The entire summary-fetching `useEffect` (lines 744-765).

**Step 3: Update JobRow to read from job record**

In `JobRow` component (line 323), remove the `summary` prop:

```jsx
function JobRow({ job, onCancel, isMobile }) {
```

Update the title display (line 367):

```jsx
{
  job.title || job.task;
}
```

Update the expanded summary display (lines 465-477). Replace `summary?.summary` with `job.summary`:

```jsx
{
  job.summary && (
    <p
      style={{
        padding: "10px 20px",
        fontSize: 12,
        color: "#6b7280",
        lineHeight: 1.5,
        margin: 0,
      }}
    >
      {job.summary}
    </p>
  );
}
```

Update `isExpandable` (line 332):

```jsx
const isExpandable = jobSummary || hasOutput || job.summary;
```

Update the output toggle border condition (line 509):

```jsx
jobSummary || job.summary;
```

**Step 4: Update JobList to remove summaries prop**

In `JobList` component (line 614), remove `summaries` prop:

```jsx
function JobList({ jobs, onCancel, isMobile }) {
```

In the `JobRow` usage (lines 690-696), remove `summary` prop:

```jsx
<JobRow key={job.id} job={job} onCancel={onCancel} isMobile={isMobile} />
```

**Step 5: Update App component render**

Remove `summaries` prop from `JobList` usage (line 827):

```jsx
<JobList jobs={jobs} onCancel={handleCancel} isMobile={isMobile} />
```

**Step 6: Clean up unused imports**

Remove `useRef` from the React import if no other refs remain. Check if `useState` import of `Map` is the only usage that was removed.

**Step 7: Run format**

Run: `format`

**Step 8: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/api.js projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "fix(orchestrator): remove client-side summarization, read title/summary from job record"
```

---

### Task 7: Make INFERENCE_MODEL configurable in Helm values

**Files:**

- Modify: `projects/agent_platform/chart/orchestrator/values.yaml`
- Modify: `projects/agent_platform/chart/orchestrator/templates/deployment.yaml` (if env vars are templated there)

**Step 1: Check current values and deployment template**

Read `projects/agent_platform/chart/orchestrator/values.yaml` and the deployment template to see how `INFERENCE_URL` is currently injected.

**Step 2: Add inferenceModel to values.yaml**

Add alongside the existing `inferenceUrl`:

```yaml
inferenceModel: "qwen3.5-35b-a3b"
```

**Step 3: Add INFERENCE_MODEL env var to deployment template**

Add to the env section, next to the existing `INFERENCE_URL`:

```yaml
- name: INFERENCE_MODEL
  value: { { .Values.inferenceModel | quote } }
```

**Step 4: Verify with helm template**

Run: `helm template agent-platform projects/agent_platform/chart/orchestrator/ -f projects/agent_platform/orchestrator/deploy/values.yaml`

Verify `INFERENCE_MODEL` appears in the rendered deployment.

**Step 5: Bump Chart.yaml version**

Bump the patch version in `projects/agent_platform/chart/orchestrator/Chart.yaml` and update `targetRevision` in `projects/agent_platform/orchestrator/deploy/application.yaml` to match.

**Step 6: Run format**

Run: `format`

**Step 7: Commit**

```bash
git add projects/agent_platform/chart/orchestrator/
git commit -m "feat(orchestrator): make inference model configurable via INFERENCE_MODEL env var"
```

---

### Task 8: Update BUILD file and final verification

**Files:**

- Modify: `projects/agent_platform/orchestrator/BUILD`

**Step 1: Run format to update BUILD**

Run: `format`

This should add `summarizer.go` to `go_library.srcs` and `summarizer_test.go` to `go_test.srcs`.

**Step 2: Verify BUILD file**

Read `projects/agent_platform/orchestrator/BUILD` and confirm:

- `summarizer.go` is in the `orchestrator_lib` library's `srcs`
- `summarizer_test.go` is in both `go_test` targets' `srcs`

**Step 3: Push and verify CI**

```bash
git push -u origin feat/backend-summarization
```

Check BuildBuddy CI for test results. All tests should pass.

**Step 4: Create PR**

```bash
gh pr create --title "feat(orchestrator): backend-driven job summarization" --body "$(cat <<'EOF'
## Summary
- Move LLM-generated summaries from UI-triggered (per-refresh) to backend lifecycle events
- Add Title/Summary fields to JobRecord, persisted in NATS KV
- New Summarizer component called at 4 lifecycle points: job submit, plan available, every 5m, terminal state
- Remove /summarize endpoint and client-side summary state
- Make inference model configurable via INFERENCE_MODEL env var

## Test plan
- [ ] Verify summarizer_test.go passes (unit tests with mock LLM)
- [ ] Verify consumer_test.go passes (including new summarization tests)
- [ ] Verify api_test.go passes (summarize endpoint tests removed)
- [ ] Deploy to cluster, submit a pipeline job, verify title appears shortly after submission
- [ ] Verify summary updates as plan steps complete
- [ ] Verify final summary appears after job succeeds/fails
- [ ] Verify UI works without /summarize endpoint (no console errors)
- [ ] Verify jobs without INFERENCE_URL configured still run normally

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
