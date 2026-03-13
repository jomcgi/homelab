# Pipeline Execution Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the pipeline composer from a UI concept into a real execution engine where each step is an independent job chained via linked list with condition-based progression, enriched with LLM-generated titles.

**Architecture:** Pipeline steps are peer `JobRecord`s sharing a `pipeline_id`. Step 0 is PENDING; steps 1-N are BLOCKED. On job completion, the consumer evaluates the next step's condition and unblocks or skips it. A new `POST /pipeline` endpoint creates all jobs and calls llama-cpp for title/summary enrichment.

**Tech Stack:** Go, NATS JetStream KV, React/Vite, llama-cpp (OpenAI-compatible API)

---

### Task 1: Add new fields and statuses to the data model

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:8-14` (statuses)
- Modify: `projects/agent_platform/orchestrator/model.go:34-51` (JobRecord)
- Modify: `projects/agent_platform/orchestrator/model.go:72-79` (SubmitRequest/PipelineRequest)

**Step 1: Add BLOCKED and SKIPPED statuses**

Add after line 13 in model.go:

```go
const (
	JobPending   JobStatus = "PENDING"
	JobRunning   JobStatus = "RUNNING"
	JobSucceeded JobStatus = "SUCCEEDED"
	JobFailed    JobStatus = "FAILED"
	JobCancelled JobStatus = "CANCELLED"
	JobBlocked   JobStatus = "BLOCKED"
	JobSkipped   JobStatus = "SKIPPED"
)
```

**Step 2: Add pipeline fields to JobRecord**

Add after the `Tags` field (line 43):

```go
// Pipeline execution fields.
PipelineID    string `json:"pipeline_id,omitempty"`    // shared ULID grouping linked jobs
StepIndex     int    `json:"step_index,omitempty"`     // 0-based position in pipeline
StepCondition string `json:"step_condition,omitempty"` // "always" | "on success" | "on failure"
Title         string `json:"title,omitempty"`          // LLM-generated short title
Summary       string `json:"summary,omitempty"`        // LLM-generated 1-2 sentence summary
```

**Step 3: Add PipelineRequest and PipelineResponse types**

Add after `SubmitResponse` (after line 86):

```go
// PipelineStep describes one step in a pipeline submission.
type PipelineStep struct {
	Agent     string `json:"agent"`
	Task      string `json:"task"`
	Condition string `json:"condition"` // "always" | "on success" | "on failure"
}

// PipelineRequest is the JSON body for POST /pipeline.
type PipelineRequest struct {
	Steps []PipelineStep `json:"steps"`
}

// PipelineResponse is returned after a pipeline is created.
type PipelineResponse struct {
	PipelineID string           `json:"pipeline_id"`
	Jobs       []SubmitResponse `json:"jobs"`
}
```

**Step 4: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: All existing tests pass (new fields are omitempty, no breakage).

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/model.go
git commit -m "feat(agent-orchestrator): add pipeline fields and BLOCKED/SKIPPED statuses to model"
```

---

### Task 2: Add Store method to list jobs by pipeline_id

**Files:**

- Modify: `projects/agent_platform/orchestrator/store.go:18-23` (Store interface)
- Modify: `projects/agent_platform/orchestrator/store.go:67-118` (JobStore.List or new method)
- Modify: `projects/agent_platform/orchestrator/api_test.go:17-79` (memStore)

**Step 1: Write the failing test**

Add to `api_test.go`:

```go
func TestMemStore_ListByPipeline(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["STEP0"] = &JobRecord{ID: "STEP0", Task: "a", Status: JobPending, PipelineID: "PIPE1", StepIndex: 0, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}
	store.jobs["STEP1"] = &JobRecord{ID: "STEP1", Task: "b", Status: JobBlocked, PipelineID: "PIPE1", StepIndex: 1, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}
	store.jobs["OTHER"] = &JobRecord{ID: "OTHER", Task: "c", Status: JobPending, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}

	jobs, err := store.ListByPipeline(context.Background(), "PIPE1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(jobs) != 2 {
		t.Fatalf("expected 2 jobs, got %d", len(jobs))
	}
	// Should be sorted by step_index ascending.
	if jobs[0].StepIndex != 0 || jobs[1].StepIndex != 1 {
		t.Fatalf("expected step indices 0,1 got %d,%d", jobs[0].StepIndex, jobs[1].StepIndex)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestMemStore_ListByPipeline`
Expected: FAIL — `ListByPipeline` not defined.

**Step 3: Add ListByPipeline to Store interface**

In `store.go`, add to the `Store` interface:

```go
type Store interface {
	Put(ctx context.Context, job *JobRecord) error
	Get(ctx context.Context, id string) (*JobRecord, error)
	Delete(ctx context.Context, id string) error
	List(ctx context.Context, statusFilter, tagFilter []string, limit, offset int) ([]JobRecord, int, error)
	ListByPipeline(ctx context.Context, pipelineID string) ([]JobRecord, error)
}
```

**Step 4: Implement on JobStore**

```go
// ListByPipeline returns all jobs in a pipeline, sorted by step_index ascending.
func (s *JobStore) ListByPipeline(ctx context.Context, pipelineID string) ([]JobRecord, error) {
	lister, err := s.kv.ListKeys(ctx)
	if err != nil {
		if err == jetstream.ErrNoKeysFound {
			return nil, nil
		}
		return nil, err
	}

	var jobs []JobRecord
	for key := range lister.Keys() {
		entry, err := s.kv.Get(ctx, key)
		if err != nil {
			continue
		}
		var job JobRecord
		if err := json.Unmarshal(entry.Value(), &job); err != nil {
			continue
		}
		if job.PipelineID == pipelineID {
			jobs = append(jobs, job)
		}
	}

	sort.Slice(jobs, func(i, j int) bool {
		return jobs[i].StepIndex < jobs[j].StepIndex
	})
	return jobs, nil
}
```

**Step 5: Implement on memStore in test file**

```go
func (m *memStore) ListByPipeline(_ context.Context, pipelineID string) ([]JobRecord, error) {
	var jobs []JobRecord
	for _, job := range m.jobs {
		if job.PipelineID == pipelineID {
			jobs = append(jobs, *job)
		}
	}
	sort.Slice(jobs, func(i, j int) bool {
		return jobs[i].StepIndex < jobs[j].StepIndex
	})
	return jobs, nil
}
```

**Step 6: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: All tests pass.

**Step 7: Commit**

```bash
git add projects/agent_platform/orchestrator/store.go projects/agent_platform/orchestrator/api_test.go
git commit -m "feat(agent-orchestrator): add ListByPipeline to Store interface"
```

---

### Task 3: Add LLM enrichment helper

**Files:**

- Create: `projects/agent_platform/orchestrator/enrich.go`
- Create: `projects/agent_platform/orchestrator/enrich_test.go`

**Step 1: Write the failing test**

Create `enrich_test.go`:

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnrichPipeline(t *testing.T) {
	// Mock LLM server returning structured JSON.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := map[string]any{
			"choices": []map[string]any{
				{"message": map[string]any{
					"content": `[{"title":"Debug CI","summary":"Investigate BuildBuddy failures"},{"title":"Fix Code","summary":"Apply fixes from CI analysis"}]`,
				}},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	steps := []PipelineStep{
		{Agent: "ci-debug", Task: "Debug the CI failure", Condition: "always"},
		{Agent: "code-fix", Task: "Fix the issue", Condition: "on success"},
	}

	enrichments, err := enrichPipeline(context.Background(), server.URL, steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(enrichments) != 2 {
		t.Fatalf("expected 2 enrichments, got %d", len(enrichments))
	}
	if enrichments[0].Title != "Debug CI" {
		t.Fatalf("expected 'Debug CI', got %q", enrichments[0].Title)
	}
}

func TestEnrichPipeline_InferenceUnavailable(t *testing.T) {
	// When inference URL is empty, return nil (graceful degradation).
	enrichments, err := enrichPipeline(context.Background(), "", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if enrichments != nil {
		t.Fatalf("expected nil enrichments, got %v", enrichments)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestEnrich`
Expected: FAIL — `enrichPipeline` not defined.

**Step 3: Implement enrich.go**

Create `enrich.go`:

````go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// enrichment holds LLM-generated metadata for a pipeline step.
type enrichment struct {
	Title   string `json:"title"`
	Summary string `json:"summary"`
}

// enrichPipeline calls the inference endpoint to generate titles and summaries
// for each pipeline step. Returns nil on empty URL (graceful degradation).
func enrichPipeline(ctx context.Context, inferenceURL string, steps []PipelineStep) ([]enrichment, error) {
	if inferenceURL == "" || len(steps) == 0 {
		return nil, nil
	}

	var sb strings.Builder
	for i, s := range steps {
		fmt.Fprintf(&sb, "Step %d: agent=%s, task=%s\n", i+1, s.Agent, s.Task)
	}

	prompt := fmt.Sprintf(`Generate a short title (max 6 words) and summary (max 2 sentences) for each pipeline step.

Steps:
%s
Return a JSON array: [{"title": "...", "summary": "..."}] with one entry per step. Only JSON, no other text.`, sb.String())

	body, _ := json.Marshal(map[string]any{
		"model": "qwen3.5-35b-a3b",
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
		"temperature": 0.3,
		"max_tokens":  500,
	})

	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, inferenceURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("creating enrichment request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, nil // Graceful degradation — don't block pipeline creation.
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, nil
	}

	var llmResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&llmResp); err != nil {
		return nil, nil
	}

	if len(llmResp.Choices) == 0 {
		return nil, nil
	}

	content := strings.TrimSpace(llmResp.Choices[0].Message.Content)
	content = strings.TrimPrefix(content, "```json")
	content = strings.TrimSuffix(content, "```")
	content = strings.TrimSpace(content)

	var enrichments []enrichment
	if err := json.Unmarshal([]byte(content), &enrichments); err != nil {
		return nil, nil
	}

	return enrichments, nil
}
````

**Step 4: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestEnrich`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/enrich.go projects/agent_platform/orchestrator/enrich_test.go
git commit -m "feat(agent-orchestrator): add LLM enrichment helper for pipeline titles"
```

---

### Task 4: Add POST /pipeline endpoint

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go:39-48` (RegisterRoutes)
- Modify: `projects/agent_platform/orchestrator/api.go` (new handler)
- Modify: `projects/agent_platform/orchestrator/api_test.go` (new tests)

**Step 1: Write the failing test**

Add to `api_test.go`:

```go
func TestHandlePipeline(t *testing.T) {
	store := newMemStore()
	logger := slog.Default()
	recipes := map[string]map[string]any{
		"ci-debug": {"version": "1.0.0"},
		"code-fix": {"version": "1.0.0"},
	}
	var published []string
	publish := func(id string) error {
		published = append(published, id)
		return nil
	}
	api := NewAPI(store, publish, nil, 2, nil, recipes, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	body := `{"steps":[{"agent":"ci-debug","task":"debug CI","condition":"always"},{"agent":"code-fix","task":"fix it","condition":"on success"}]}`
	req := httptest.NewRequest(http.MethodPost, "/pipeline", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp PipelineResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.PipelineID == "" {
		t.Fatal("expected non-empty pipeline_id")
	}
	if len(resp.Jobs) != 2 {
		t.Fatalf("expected 2 jobs, got %d", len(resp.Jobs))
	}

	// First job should be PENDING (dispatched).
	if resp.Jobs[0].Status != JobPending {
		t.Fatalf("step 0: expected PENDING, got %s", resp.Jobs[0].Status)
	}
	// Second job should be BLOCKED.
	if resp.Jobs[1].Status != JobBlocked {
		t.Fatalf("step 1: expected BLOCKED, got %s", resp.Jobs[1].Status)
	}

	// Only first job should be published to NATS.
	if len(published) != 1 {
		t.Fatalf("expected 1 published job, got %d", len(published))
	}

	// Verify stored jobs have pipeline fields.
	job0, _ := store.Get(context.Background(), resp.Jobs[0].ID)
	if job0.PipelineID != resp.PipelineID {
		t.Fatalf("job0 pipeline_id mismatch")
	}
	if job0.StepIndex != 0 {
		t.Fatalf("job0 step_index: expected 0, got %d", job0.StepIndex)
	}
	if job0.Profile != "ci-debug" {
		t.Fatalf("job0 profile: expected ci-debug, got %q", job0.Profile)
	}

	job1, _ := store.Get(context.Background(), resp.Jobs[1].ID)
	if job1.StepCondition != "on success" {
		t.Fatalf("job1 condition: expected 'on success', got %q", job1.StepCondition)
	}
}

func TestHandlePipeline_EmptySteps(t *testing.T) {
	store := newMemStore()
	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, nil, nil, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	body := `{"steps":[]}`
	req := httptest.NewRequest(http.MethodPost, "/pipeline", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestHandlePipeline_InvalidAgent(t *testing.T) {
	store := newMemStore()
	logger := slog.Default()
	recipes := map[string]map[string]any{"ci-debug": {"version": "1.0.0"}}
	api := NewAPI(store, nil, nil, 2, nil, recipes, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	body := `{"steps":[{"agent":"nonexistent","task":"test","condition":"always"}]}`
	req := httptest.NewRequest(http.MethodPost, "/pipeline", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test --test_filter=TestHandlePipeline`
Expected: FAIL — route not registered.

**Step 3: Implement handlePipeline**

Add route in `RegisterRoutes`:

```go
mux.HandleFunc("POST /pipeline", a.handlePipeline)
```

Add handler method to `api.go`:

```go
func (a *API) handlePipeline(w http.ResponseWriter, r *http.Request) {
	var req PipelineRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		a.writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if len(req.Steps) == 0 {
		a.writeError(w, http.StatusBadRequest, "at least one step is required")
		return
	}
	if len(req.Steps) > 10 {
		a.writeError(w, http.StatusBadRequest, "maximum 10 steps per pipeline")
		return
	}

	// Validate all agents exist.
	for _, step := range req.Steps {
		if _, ok := a.recipes[step.Agent]; !ok {
			a.writeError(w, http.StatusBadRequest, "unknown agent: "+step.Agent)
			return
		}
	}

	now := time.Now().UTC()
	pipelineID, err := ulid.New(ulid.Timestamp(now), rand.Reader)
	if err != nil {
		a.writeError(w, http.StatusInternalServerError, "failed to generate pipeline ID")
		return
	}

	// LLM enrichment (best-effort).
	enrichments, _ := enrichPipeline(r.Context(), a.inferenceURL, req.Steps)

	var jobs []SubmitResponse
	for i, step := range req.Steps {
		id, err := ulid.New(ulid.Timestamp(now.Add(time.Duration(i)*time.Millisecond)), rand.Reader)
		if err != nil {
			a.writeError(w, http.StatusInternalServerError, "failed to generate job ID")
			return
		}

		status := JobBlocked
		if i == 0 {
			status = JobPending
		}

		job := &JobRecord{
			ID:            id.String(),
			Task:          step.Task,
			Profile:       step.Agent,
			Status:        status,
			CreatedAt:     now,
			UpdatedAt:     now,
			MaxRetries:    a.defaultMaxRetries,
			Source:        "pipeline",
			PipelineID:    pipelineID.String(),
			StepIndex:     i,
			StepCondition: step.Condition,
			Attempts:      []Attempt{},
		}

		// Apply enrichment if available.
		if enrichments != nil && i < len(enrichments) {
			job.Title = enrichments[i].Title
			job.Summary = enrichments[i].Summary
		}

		if err := a.store.Put(r.Context(), job); err != nil {
			a.logger.Error("failed to store pipeline job", "step", i, "error", err)
			a.writeError(w, http.StatusInternalServerError, "failed to store pipeline job")
			return
		}

		// Only publish step 0 to NATS for immediate dispatch.
		if i == 0 && a.publish != nil {
			if err := a.publish(job.ID); err != nil {
				a.logger.Error("failed to publish pipeline job", "id", job.ID, "error", err)
				a.writeError(w, http.StatusInternalServerError, "failed to enqueue pipeline")
				return
			}
		}

		jobs = append(jobs, SubmitResponse{
			ID:        job.ID,
			Status:    job.Status,
			CreatedAt: job.CreatedAt,
		})
	}

	a.writeJSON(w, http.StatusAccepted, PipelineResponse{
		PipelineID: pipelineID.String(),
		Jobs:       jobs,
	})
}
```

**Step 4: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/api.go projects/agent_platform/orchestrator/api_test.go
git commit -m "feat(agent-orchestrator): add POST /pipeline endpoint for linked-list execution"
```

---

### Task 5: Add step chaining to the consumer completion handler

**Files:**

- Modify: `projects/agent_platform/orchestrator/consumer.go:22-30` (Consumer struct — needs publish func)
- Modify: `projects/agent_platform/orchestrator/consumer.go:203-243` (terminal state handling)

**Step 1: Add publish function to Consumer**

The Consumer needs to publish job IDs to NATS to unblock next steps. Add `publish` field:

```go
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	publish     func(jobID string) error
	maxDuration time.Duration
	recipes     map[string]map[string]any
	logger      *slog.Logger
}

func NewConsumer(cons jetstream.Consumer, store Store, sandbox Sandbox, publish func(string) error, maxDuration time.Duration, recipes map[string]map[string]any, logger *slog.Logger) *Consumer {
	return &Consumer{
		cons:        cons,
		store:       store,
		sandbox:     sandbox,
		publish:     publish,
		maxDuration: maxDuration,
		recipes:     recipes,
		logger:      logger,
	}
}
```

**Step 2: Add advancePipeline method**

Add after `flushOutput`:

```go
// advancePipeline evaluates the next step in a pipeline and either unblocks it,
// skips it (and cascades), or does nothing if the pipeline is complete.
func (c *Consumer) advancePipeline(ctx context.Context, completed *JobRecord) {
	if completed.PipelineID == "" {
		return
	}

	logger := c.logger.With("pipelineID", completed.PipelineID, "completedStep", completed.StepIndex)

	pipelineJobs, err := c.store.ListByPipeline(ctx, completed.PipelineID)
	if err != nil {
		logger.Error("failed to list pipeline jobs", "error", err)
		return
	}

	// Find the next step.
	var next *JobRecord
	for i := range pipelineJobs {
		if pipelineJobs[i].StepIndex == completed.StepIndex+1 {
			next = &pipelineJobs[i]
			break
		}
	}
	if next == nil {
		logger.Info("pipeline complete, no more steps")
		return
	}

	if next.Status != JobBlocked {
		logger.Info("next step not blocked, skipping advance", "nextStatus", next.Status)
		return
	}

	// Evaluate condition.
	conditionMet := false
	switch next.StepCondition {
	case "always":
		conditionMet = true
	case "on success":
		conditionMet = completed.Status == JobSucceeded
	case "on failure":
		conditionMet = completed.Status == JobFailed
	default:
		conditionMet = true // Default to always.
	}

	if !conditionMet {
		logger.Info("condition not met, skipping step", "condition", next.StepCondition, "predecessorStatus", completed.Status)
		next.Status = JobSkipped
		if err := c.store.Put(ctx, next); err != nil {
			logger.Error("failed to skip step", "error", err)
		}
		// Cascade: skip all remaining BLOCKED steps.
		c.cascadeSkip(ctx, pipelineJobs, next.StepIndex)
		return
	}

	// Prepend predecessor context to next step's task.
	next.Task = c.buildStepContext(completed, next.Task)
	next.Status = JobPending
	if err := c.store.Put(ctx, next); err != nil {
		logger.Error("failed to unblock step", "error", err)
		return
	}

	// Publish to NATS for dispatch.
	if c.publish != nil {
		if err := c.publish(next.ID); err != nil {
			logger.Error("failed to publish next step", "error", err)
		}
	}

	logger.Info("advanced pipeline to next step", "nextStep", next.StepIndex, "nextAgent", next.Profile)
}

// cascadeSkip marks all BLOCKED steps after the given index as SKIPPED.
func (c *Consumer) cascadeSkip(ctx context.Context, jobs []JobRecord, afterIndex int) {
	for i := range jobs {
		if jobs[i].StepIndex > afterIndex && jobs[i].Status == JobBlocked {
			jobs[i].Status = JobSkipped
			if err := c.store.Put(ctx, &jobs[i]); err != nil {
				c.logger.Error("failed to cascade skip", "jobID", jobs[i].ID, "error", err)
			}
		}
	}
}

// buildStepContext prepends predecessor output to the next step's task.
func (c *Consumer) buildStepContext(pred *JobRecord, task string) string {
	if len(pred.Attempts) == 0 {
		return task
	}

	lastAttempt := pred.Attempts[len(pred.Attempts)-1]
	output := lastAttempt.Output
	if len(output) > 2000 {
		output = output[len(output)-2000:]
	}

	var resultCtx string
	if lastAttempt.Result != nil {
		resultCtx = fmt.Sprintf("\nResult: type=%s url=%s summary=%s", lastAttempt.Result.Type, lastAttempt.Result.URL, lastAttempt.Result.Summary)
	}

	return fmt.Sprintf(`Previous step (agent: %s, status: %s) output:
---
%s%s
---

Your task:
%s`, pred.Profile, string(pred.Status), output, resultCtx, task)
}
```

**Step 3: Call advancePipeline from processJob**

In `processJob`, after each terminal state (failed with no retries, succeeded, cancelled), add the call. Replace the three terminal blocks (lines ~227-242) with:

```go
	if failed {
		logger.Info("task failed, retries exhausted", "attempt", attemptNum, "error", execErr)
		job.Status = JobFailed
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Error("failed to store failed state", "error", err)
		}
		c.advancePipeline(jobCtx, job)
		_ = msg.Ack()
		return
	}

	logger.Info("task succeeded", "attempt", attemptNum)
	job.Status = JobSucceeded
	if err := c.store.Put(jobCtx, job); err != nil {
		logger.Error("failed to store succeeded state", "error", err)
	}
	c.advancePipeline(jobCtx, job)
	_ = msg.Ack()
```

Also add after the cancellation check block (~line 204-211):

```go
	if job.Status == JobCancelled {
		logger.Info("job was cancelled during execution")
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Error("failed to store cancelled job", "error", err)
		}
		c.advancePipeline(jobCtx, job)
		_ = msg.Ack()
		return
	}
```

**Step 4: Update main.go NewConsumer call**

In `main.go`, pass the publish function to NewConsumer. Find the `NewConsumer` call and add the publish parameter.

**Step 5: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: All tests pass. (Consumer tests use fakes that don't exercise advancePipeline — integration testing will cover this.)

**Step 6: Commit**

```bash
git add projects/agent_platform/orchestrator/consumer.go projects/agent_platform/orchestrator/main.go
git commit -m "feat(agent-orchestrator): add pipeline step chaining to consumer completion handler"
```

---

### Task 6: Add forward cancellation to handleCancel

**Files:**

- Modify: `projects/agent_platform/orchestrator/api.go:184-205` (handleCancel)
- Modify: `projects/agent_platform/orchestrator/api_test.go` (new test)

**Step 1: Write the failing test**

```go
func TestHandleCancel_ForwardCascade(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["S0"] = &JobRecord{ID: "S0", Task: "a", Status: JobRunning, PipelineID: "P1", StepIndex: 0, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}
	store.jobs["S1"] = &JobRecord{ID: "S1", Task: "b", Status: JobBlocked, PipelineID: "P1", StepIndex: 1, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}
	store.jobs["S2"] = &JobRecord{ID: "S2", Task: "c", Status: JobBlocked, PipelineID: "P1", StepIndex: 2, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodPost, "/jobs/S0/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// S1 and S2 should be cancelled.
	s1, _ := store.Get(context.Background(), "S1")
	if s1.Status != JobCancelled {
		t.Fatalf("S1: expected CANCELLED, got %s", s1.Status)
	}
	s2, _ := store.Get(context.Background(), "S2")
	if s2.Status != JobCancelled {
		t.Fatalf("S2: expected CANCELLED, got %s", s2.Status)
	}
}
```

**Step 2: Run test to verify it fails**

Expected: FAIL — S1 and S2 still BLOCKED.

**Step 3: Update handleCancel with forward cascade**

Replace `handleCancel` in `api.go`:

```go
func (a *API) handleCancel(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(r.Context(), id)
	if err != nil || job == nil {
		a.writeError(w, http.StatusNotFound, "job not found")
		return
	}

	if job.Status != JobPending && job.Status != JobRunning && job.Status != JobBlocked {
		a.writeError(w, http.StatusConflict, "job cannot be cancelled in status "+string(job.Status))
		return
	}

	job.Status = JobCancelled
	if err := a.store.Put(r.Context(), job); err != nil {
		a.logger.Error("failed to update job", "id", id, "error", err)
		a.writeError(w, http.StatusInternalServerError, "failed to update job")
		return
	}

	// Forward cascade: cancel all BLOCKED steps after this one in the pipeline.
	if job.PipelineID != "" {
		pipelineJobs, err := a.store.ListByPipeline(r.Context(), job.PipelineID)
		if err == nil {
			for i := range pipelineJobs {
				if pipelineJobs[i].StepIndex > job.StepIndex && pipelineJobs[i].Status == JobBlocked {
					pipelineJobs[i].Status = JobCancelled
					_ = a.store.Put(r.Context(), &pipelineJobs[i])
				}
			}
		}
	}

	a.writeJSON(w, http.StatusOK, job)
}
```

**Step 4: Run tests**

Run: `bazel test //projects/agent_platform/orchestrator:orchestrator_test`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/api.go projects/agent_platform/orchestrator/api_test.go
git commit -m "feat(agent-orchestrator): add forward cancellation for pipeline steps"
```

---

### Task 7: Update the UI to use POST /pipeline and show per-step status

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/api.js` (new pipeline API + list by pipeline)
- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx` (group by pipeline, per-step status)

**Step 1: Update api.js**

Replace `submitPipeline` and add pipeline-aware listing:

```js
export async function submitPipeline(spec) {
  const res = await fetch(`${API}/pipeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { pipeline_id, jobs }
}
```

**Step 2: Update App.jsx — group jobs by pipeline_id**

In the `App` component, add job grouping logic before rendering. Jobs with a `pipeline_id` are grouped together; the group uses the first step's data for the compact row. Non-pipeline jobs render as before.

Replace the `JobList` component to group pipeline jobs:

- Parse `job.pipeline_id` to group jobs
- Render pipeline groups with `PipelineFlow` using real per-step statuses from the grouped jobs
- Show per-step status dots in the compact flow (green/blue/amber/red/grey)
- In expanded view, render each step as its own mini-row with status dot, title, task, output toggle
- SKIPPED steps: dashed border, muted text, "Skipped" label
- Cascade visual: red break-line between failed and skipped steps

**Step 3: Add Vite proxy for /pipeline**

In `vite.config.js`, add:

```js
"/pipeline": "http://localhost:8080",
```

**Step 4: Manually test with dev server**

1. Open http://localhost:5173
2. Write a prompt and click "Infer pipeline"
3. Click "Submit to orchestrator"
4. Verify pipeline creates individual step jobs
5. Verify compact flow shows per-step status dots
6. Verify expanded view shows step details with live output

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/api.js projects/agent_platform/orchestrator/ui/src/App.jsx projects/agent_platform/orchestrator/ui/vite.config.js
git commit -m "feat(agent-orchestrator): update UI for pipeline execution with per-step status"
```

---

### Task 8: Add model field to recipe settings

**Files:**

- Modify: `projects/agent_platform/orchestrator/recipe.go` (extract model from settings)
- Modify: `projects/agent_platform/chart/orchestrator/values.yaml` (add model to recipe settings)

**Step 1: Check current recipe rendering**

Read `projects/agent_platform/orchestrator/recipe.go` to understand how recipes are rendered and how the runner receives them.

**Step 2: Add model to recipe settings in values.yaml**

For agents that benefit from Opus, set `model: claude-opus-4-6` in their recipe settings. For others, set `model: claude-sonnet-4-6` or leave empty (falls back to SandboxTemplate default).

Example for PR Review (benefits from deeper reasoning):

```yaml
settings:
  max_turns: 30
  max_tool_repetitions: 5
  model: claude-opus-4-6
```

**Step 3: Verify the runner reads model from recipe**

Check `projects/agent_platform/goose_agent/` or the runner code to see if the runner already reads `settings.model`. If not, this is a runner-side change that can be a separate task.

**Step 4: Commit**

```bash
git add projects/agent_platform/chart/orchestrator/values.yaml
git commit -m "feat(agent-orchestrator): add model field to recipe settings for per-agent model selection"
```

---

### Task 9: Bump chart version and update umbrella chart

**Files:**

- Modify: `projects/agent_platform/chart/orchestrator/Chart.yaml` (bump version)
- Modify: `projects/agent_platform/chart/Chart.yaml` (bump umbrella version)
- Modify: `projects/agent_platform/chart/values.yaml` (mirror new values)
- Modify: `projects/agent_platform/deploy/application.yaml` (bump targetRevision)

**Step 1: Bump versions**

Bump the orchestrator subchart patch version and the umbrella chart minor version.

**Step 2: Run format**

Run: `format`
This regenerates BUILD files and updates subchart tarballs.

**Step 3: Commit**

```bash
git add projects/agent_platform/chart/
git commit -m "chore(agent-platform): bump chart versions for pipeline execution"
```
