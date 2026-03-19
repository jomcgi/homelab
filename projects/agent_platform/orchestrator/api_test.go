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

func newTestAPI(store Store) (*API, *http.ServeMux) {
	logger := slog.Default()
	api := NewAPI(store, nil, nil, 2, logger)
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

func TestHandleSubmit_DefaultSource(t *testing.T) {
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

	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if job.Source != "api" {
		t.Fatalf("expected source 'api', got %q", job.Source)
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

func TestHandleHealth(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
}
