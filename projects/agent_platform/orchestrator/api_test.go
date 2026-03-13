package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"testing"
	"time"
)

// memStore is an in-memory implementation of Store for unit tests.
type memStore struct {
	jobs map[string]*JobRecord
}

func newMemStore() *memStore {
	return &memStore{jobs: make(map[string]*JobRecord)}
}

func (m *memStore) Put(_ context.Context, job *JobRecord) error {
	cp := *job
	cp.UpdatedAt = time.Now().UTC()
	m.jobs[job.ID] = &cp
	return nil
}

func (m *memStore) Delete(_ context.Context, id string) error {
	delete(m.jobs, id)
	return nil
}

func (m *memStore) Get(_ context.Context, id string) (*JobRecord, error) {
	job, ok := m.jobs[id]
	if !ok {
		return nil, fmt.Errorf("not found")
	}
	return job, nil
}

func (m *memStore) List(_ context.Context, statusFilter, tagFilter []string, limit, offset int) ([]JobRecord, int, error) {
	filterSet := make(map[string]bool)
	for _, f := range statusFilter {
		filterSet[strings.ToUpper(f)] = true
	}

	var keys []string
	for k := range m.jobs {
		keys = append(keys, k)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(keys)))

	var all []JobRecord
	for _, k := range keys {
		job := m.jobs[k]
		if len(filterSet) > 0 && !filterSet[string(job.Status)] {
			continue
		}
		if len(tagFilter) > 0 && !hasAllTags(job.Tags, tagFilter) {
			continue
		}
		all = append(all, *job)
	}

	total := len(all)
	if offset >= total {
		return nil, total, nil
	}
	end := offset + limit
	if end > total {
		end = total
	}
	return all[offset:end], total, nil
}

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

func newTestAPI(store Store) (*API, *http.ServeMux) {
	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, nil, nil, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)
	return api, mux
}

func TestHandleSubmit(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	body := `{"task":"run tests"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp SubmitResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.ID == "" {
		t.Fatal("expected non-empty ID")
	}
	if resp.Status != JobPending {
		t.Fatalf("expected PENDING, got %s", resp.Status)
	}
	// ULID should be 26 chars
	if len(resp.ID) != 26 {
		t.Fatalf("expected ULID (26 chars), got %q (%d chars)", resp.ID, len(resp.ID))
	}
}

func TestHandleSubmit_WithProfile(t *testing.T) {
	store := newMemStore()
	logger := slog.Default()
	recipes := map[string]map[string]any{"ci-debug": {"version": "1.0.0"}}
	api := NewAPI(store, nil, nil, 2, nil, recipes, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	body := `{"task":"fix the build","profile":"ci-debug"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp SubmitResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	// Verify profile was stored on the job record.
	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if job.Profile != "ci-debug" {
		t.Fatalf("expected profile ci-debug, got %q", job.Profile)
	}
}

func TestHandleSubmit_NoProfile(t *testing.T) {
	store := newMemStore()
	_, mux := newTestAPI(store)

	body := `{"task":"run tests"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp SubmitResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	// Verify empty profile preserves default behavior.
	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if job.Profile != "" {
		t.Fatalf("expected empty profile, got %q", job.Profile)
	}
}

func TestHandleSubmit_InvalidProfile(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	body := `{"task":"run tests","profile":"nonexistent"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestHandleSubmit_MissingTask(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	body := `{"task":""}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestHandleGet(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["TEST123"] = &JobRecord{
		ID:        "TEST123",
		Task:      "deploy app",
		Status:    JobRunning,
		CreatedAt: now,
		UpdatedAt: now,
		Attempts:  []Attempt{},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/TEST123", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var job JobRecord
	if err := json.NewDecoder(rec.Body).Decode(&job); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if job.ID != "TEST123" {
		t.Fatalf("expected TEST123, got %s", job.ID)
	}
	if job.Status != JobRunning {
		t.Fatalf("expected RUNNING, got %s", job.Status)
	}
}

func TestHandleGet_NotFound(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodGet, "/jobs/NONEXISTENT", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestHandleList_StatusFilter(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["JOB1"] = &JobRecord{ID: "JOB1", Task: "a", Status: JobPending, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}
	store.jobs["JOB2"] = &JobRecord{ID: "JOB2", Task: "b", Status: JobRunning, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}
	store.jobs["JOB3"] = &JobRecord{ID: "JOB3", Task: "c", Status: JobSucceeded, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs?status=PENDING,RUNNING", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp ListResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(resp.Jobs) != 2 {
		t.Fatalf("expected 2 jobs, got %d", len(resp.Jobs))
	}
	if resp.Total != 2 {
		t.Fatalf("expected total 2, got %d", resp.Total)
	}
}

func TestHandleCancel(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["CANCEL1"] = &JobRecord{ID: "CANCEL1", Task: "test", Status: JobPending, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodPost, "/jobs/CANCEL1/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var job JobRecord
	if err := json.NewDecoder(rec.Body).Decode(&job); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if job.Status != JobCancelled {
		t.Fatalf("expected CANCELLED, got %s", job.Status)
	}
}

func TestHandleCancel_AlreadySucceeded(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["DONE1"] = &JobRecord{ID: "DONE1", Task: "test", Status: JobSucceeded, CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodPost, "/jobs/DONE1/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestHandleOutput(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	exitCode := 0
	store.jobs["OUT1"] = &JobRecord{
		ID:        "OUT1",
		Task:      "test",
		Status:    JobSucceeded,
		CreatedAt: now,
		UpdatedAt: now,
		Attempts: []Attempt{
			{
				Number:   1,
				ExitCode: &exitCode,
				Output:   "all tests passed",
			},
		},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/OUT1/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp OutputResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Output != "all tests passed" {
		t.Fatalf("expected 'all tests passed', got %q", resp.Output)
	}
	if resp.Attempt != 1 {
		t.Fatalf("expected attempt 1, got %d", resp.Attempt)
	}
	if resp.ExitCode == nil || *resp.ExitCode != 0 {
		t.Fatalf("expected exit code 0, got %v", resp.ExitCode)
	}
}

func TestHandleAgents(t *testing.T) {
	logger := slog.Default()
	agents := []AgentInfo{
		{ID: "ci-debug", Label: "CI Debug", Icon: "gear", Background: "#dbeafe", Foreground: "#1e40af", Description: "Debug CI", Category: "analyse", Recipe: map[string]any{"version": "1.0.0"}},
		{ID: "code-fix", Label: "Code Fix", Icon: "gear", Background: "#dbeafe", Foreground: "#1e40af", Description: "Fix code", Category: "action"},
	}
	recipes := map[string]map[string]any{"ci-debug": {"version": "1.0.0"}}
	api := NewAPI(newMemStore(), nil, nil, 2, agents, recipes, "", logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/agents", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp AgentsResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if len(resp.Agents) != 2 {
		t.Fatalf("expected 2 agents, got %d", len(resp.Agents))
	}
	if resp.Agents[0].ID != "ci-debug" {
		t.Fatalf("expected first agent ci-debug, got %s", resp.Agents[0].ID)
	}
	// Recipe should be stripped from response
	if resp.Agents[0].Recipe != nil {
		t.Fatal("expected recipe to be stripped from response")
	}
}

func TestHandleAgentsEmpty(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodGet, "/agents", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp AgentsResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if resp.Agents == nil || len(resp.Agents) != 0 {
		t.Fatalf("expected empty agents array, got %v", resp.Agents)
	}
}

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

func TestHandleHealth(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
}

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

func TestGetJob_IncludesPipelineResult(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["PIPE01"] = &JobRecord{
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
		CreatedAt: now,
		UpdatedAt: now,
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/PIPE01", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var result JobRecord
	if err := json.NewDecoder(rec.Body).Decode(&result); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if len(result.Attempts) != 1 {
		t.Fatalf("expected 1 attempt, got %d", len(result.Attempts))
	}
	lastAttempt := result.Attempts[0]
	if lastAttempt.Result == nil {
		t.Fatal("expected result on attempt")
	}
	if lastAttempt.Result.Type != "pipeline" {
		t.Errorf("type = %q, want pipeline", lastAttempt.Result.Type)
	}
	if len(lastAttempt.Result.Pipeline) != 2 {
		t.Fatalf("expected 2 pipeline steps, got %d", len(lastAttempt.Result.Pipeline))
	}
	if lastAttempt.Result.Pipeline[0].Agent != "research" {
		t.Errorf("step 0 agent = %q, want research", lastAttempt.Result.Pipeline[0].Agent)
	}
	if lastAttempt.Result.Pipeline[1].Condition != "on success" {
		t.Errorf("step 1 condition = %q, want 'on success'", lastAttempt.Result.Pipeline[1].Condition)
	}
}
