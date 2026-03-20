package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// newTestAPIFull creates an API with a configurable publish function and health
// check, allowing tests to cover paths that newTestAPI (nil publish, nil check)
// cannot reach.
func newTestAPIFull(store Store, publish func(string) error, healthCheck func() error) (*API, *http.ServeMux) {
	api := NewAPI(store, publish, healthCheck, 2, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)
	return api, mux
}

// --- handleSubmit additional coverage ---

// TestHandleSubmit_PublishFailure verifies that when the publish function fails
// after the job is stored, the KV entry is rolled back and a 500 is returned.
func TestHandleSubmit_PublishFailure(t *testing.T) {
	store := newMemStore()
	publishErr := errors.New("nats unavailable")
	_, mux := newTestAPIFull(store, func(_ string) error { return publishErr }, nil)

	body := `{"task":"deploy app"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 on publish failure, got %d: %s", rec.Code, rec.Body.String())
	}

	// KV should be empty — the rollback must have removed the ghost entry.
	jobs, _, err := store.List(context.Background(), nil, nil, 10, 0)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(jobs) != 0 {
		t.Errorf("expected 0 jobs after rollback, got %d", len(jobs))
	}
}

// TestHandleSubmit_PublishSuccess verifies that when a publish function is
// provided and succeeds, the job ID is forwarded to the publisher.
func TestHandleSubmit_PublishSuccess(t *testing.T) {
	store := newMemStore()
	published := ""
	_, mux := newTestAPIFull(store, func(id string) error {
		published = id
		return nil
	}, nil)

	body := `{"task":"build image"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp SubmitResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if published != resp.ID {
		t.Errorf("published ID %q != response ID %q", published, resp.ID)
	}
}

// TestHandleSubmit_MaxRetriesClamped_Negative verifies that a negative
// MaxRetries value is clamped to 0.
func TestHandleSubmit_MaxRetriesClamped_Negative(t *testing.T) {
	store := newMemStore()
	_, mux := newTestAPI(store)

	body := `{"task":"retry test","max_retries":-5}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp SubmitResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if job.MaxRetries != 0 {
		t.Errorf("MaxRetries = %d, want 0 (clamped from -5)", job.MaxRetries)
	}
}

// TestHandleSubmit_MaxRetriesClamped_OverMax verifies that MaxRetries > 10 is
// clamped to maxMaxRetries (10).
func TestHandleSubmit_MaxRetriesClamped_OverMax(t *testing.T) {
	store := newMemStore()
	_, mux := newTestAPI(store)

	body := `{"task":"retry test","max_retries":99}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp SubmitResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if job.MaxRetries != maxMaxRetries {
		t.Errorf("MaxRetries = %d, want %d (clamped from 99)", job.MaxRetries, maxMaxRetries)
	}
}

// TestHandleSubmit_CustomSource verifies that a non-empty source field in the
// request is preserved on the stored job record.
func TestHandleSubmit_CustomSource(t *testing.T) {
	store := newMemStore()
	_, mux := newTestAPI(store)

	body := `{"task":"run tests","source":"discord"}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", rec.Code)
	}
	var resp SubmitResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if job.Source != "discord" {
		t.Errorf("Source = %q, want %q", job.Source, "discord")
	}
}

// TestHandleSubmit_TagsStored verifies that tags provided in the request are
// persisted on the job record.
func TestHandleSubmit_TagsStored(t *testing.T) {
	store := newMemStore()
	_, mux := newTestAPI(store)

	body := `{"task":"tag test","tags":["ci","priority-high"]}`
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", rec.Code)
	}
	var resp SubmitResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	job, err := store.Get(context.Background(), resp.ID)
	if err != nil {
		t.Fatalf("get job: %v", err)
	}
	if len(job.Tags) != 2 || job.Tags[0] != "ci" || job.Tags[1] != "priority-high" {
		t.Errorf("Tags = %v, want [ci priority-high]", job.Tags)
	}
}

// TestHandleSubmit_InvalidJSON verifies that a malformed request body returns
// HTTP 400.
func TestHandleSubmit_InvalidJSON(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString("{not valid json"))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid JSON, got %d", rec.Code)
	}
}

// --- handleList additional coverage ---

// TestHandleList_EmptyStore verifies that listing from an empty store returns a
// non-nil empty jobs array and total=0.
func TestHandleList_EmptyStore(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodGet, "/jobs", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if resp.Jobs == nil {
		t.Error("expected non-nil jobs array, got nil")
	}
	if len(resp.Jobs) != 0 {
		t.Errorf("expected 0 jobs, got %d", len(resp.Jobs))
	}
	if resp.Total != 0 {
		t.Errorf("expected total=0, got %d", resp.Total)
	}
}

// TestHandleList_TagFilter verifies that only jobs matching ALL requested tags
// are returned when the tags query parameter is set.
func TestHandleList_TagFilter(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()

	// JOB-TAG-A has both "ci" and "urgent" — should match.
	store.jobs["JOB-TAG-A"] = &JobRecord{
		ID: "JOB-TAG-A", Task: "a", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}, Tags: []string{"ci", "urgent"},
	}
	// JOB-TAG-B has only "ci" — should NOT match.
	store.jobs["JOB-TAG-B"] = &JobRecord{
		ID: "JOB-TAG-B", Task: "b", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}, Tags: []string{"ci"},
	}
	// JOB-TAG-C has only "urgent" — should NOT match.
	store.jobs["JOB-TAG-C"] = &JobRecord{
		ID: "JOB-TAG-C", Task: "c", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{}, Tags: []string{"urgent"},
	}
	// JOB-TAG-D has no tags — should NOT match.
	store.jobs["JOB-TAG-D"] = &JobRecord{
		ID: "JOB-TAG-D", Task: "d", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs?tags=ci,urgent", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if len(resp.Jobs) != 1 {
		t.Fatalf("expected 1 job with both tags, got %d", len(resp.Jobs))
	}
	if resp.Jobs[0].ID != "JOB-TAG-A" {
		t.Errorf("expected JOB-TAG-A, got %s", resp.Jobs[0].ID)
	}
}

// TestHandleList_Pagination verifies that limit and offset query parameters
// correctly page through results.
func TestHandleList_Pagination(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	// 5 jobs with reverse-sortable keys (Z > Y > X > W > V).
	for _, id := range []string{"JOB-P-Z", "JOB-P-Y", "JOB-P-X", "JOB-P-W", "JOB-P-V"} {
		store.jobs[id] = &JobRecord{
			ID: id, Task: id, Status: JobPending,
			CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
		}
	}

	_, mux := newTestAPI(store)

	// Page 1: limit=2, offset=0.
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs?limit=2&offset=0", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("page 1: expected 200, got %d", rec.Code)
	}
	var p1 ListResponse
	json.NewDecoder(rec.Body).Decode(&p1)
	if p1.Total != 5 {
		t.Errorf("page 1 total = %d, want 5", p1.Total)
	}
	if len(p1.Jobs) != 2 {
		t.Errorf("page 1 len = %d, want 2", len(p1.Jobs))
	}

	// Page 2: limit=2, offset=2.
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, httptest.NewRequest(http.MethodGet, "/jobs?limit=2&offset=2", nil))
	var p2 ListResponse
	json.NewDecoder(rec2.Body).Decode(&p2)
	if len(p2.Jobs) != 2 {
		t.Errorf("page 2 len = %d, want 2", len(p2.Jobs))
	}

	// Page 3: limit=2, offset=4 — only 1 job remaining.
	rec3 := httptest.NewRecorder()
	mux.ServeHTTP(rec3, httptest.NewRequest(http.MethodGet, "/jobs?limit=2&offset=4", nil))
	var p3 ListResponse
	json.NewDecoder(rec3.Body).Decode(&p3)
	if len(p3.Jobs) != 1 {
		t.Errorf("page 3 len = %d, want 1", len(p3.Jobs))
	}

	// Offset beyond total: should return empty jobs with correct total.
	rec4 := httptest.NewRecorder()
	mux.ServeHTTP(rec4, httptest.NewRequest(http.MethodGet, "/jobs?limit=2&offset=10", nil))
	var p4 ListResponse
	json.NewDecoder(rec4.Body).Decode(&p4)
	if len(p4.Jobs) != 0 {
		t.Errorf("page beyond end len = %d, want 0", len(p4.Jobs))
	}
	if p4.Total != 5 {
		t.Errorf("page beyond end total = %d, want 5", p4.Total)
	}
}

// TestHandleList_LimitClamped verifies that a limit > 100 is silently clamped
// to 100.
func TestHandleList_LimitClamped(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	for _, id := range []string{"JOB-L-A", "JOB-L-B", "JOB-L-C"} {
		store.jobs[id] = &JobRecord{
			ID: id, Task: id, Status: JobPending,
			CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
		}
	}

	_, mux := newTestAPI(store)

	// limit=200 exceeds max; the handler clamps to 100 internally.
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs?limit=200", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	// All 3 jobs should still be returned (clamp to 100 ≥ 3).
	if len(resp.Jobs) != 3 {
		t.Errorf("expected 3 jobs, got %d", len(resp.Jobs))
	}
}

// TestHandleList_InvalidLimitIsIgnored verifies that a non-numeric limit query
// parameter is silently ignored and the default of 20 is applied.
func TestHandleList_InvalidLimitIsIgnored(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["JOB-INV"] = &JobRecord{
		ID: "JOB-INV", Task: "t", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs?limit=notanumber", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	// The single job should still be returned using default limit.
	if len(resp.Jobs) != 1 {
		t.Errorf("expected 1 job, got %d", len(resp.Jobs))
	}
}

// TestHandleList_NegativeOffsetIsIgnored verifies that a negative offset query
// parameter is silently ignored and offset=0 is used.
func TestHandleList_NegativeOffsetIsIgnored(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["JOB-OFF"] = &JobRecord{
		ID: "JOB-OFF", Task: "t", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs?offset=-10", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	if len(resp.Jobs) != 1 {
		t.Errorf("expected 1 job with negative offset ignored, got %d", len(resp.Jobs))
	}
}

// --- handleCancel additional coverage ---

// TestHandleCancel_RunningJob verifies that a RUNNING job can be cancelled
// (not just PENDING jobs).
func TestHandleCancel_RunningJob(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["RUNNING1"] = &JobRecord{
		ID: "RUNNING1", Task: "test", Status: JobRunning,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodPost, "/jobs/RUNNING1/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var job JobRecord
	json.NewDecoder(rec.Body).Decode(&job)

	if job.Status != JobCancelled {
		t.Errorf("expected CANCELLED, got %s", job.Status)
	}
}

// TestHandleCancel_FailedJob verifies that a FAILED job cannot be cancelled
// and returns 409.
func TestHandleCancel_FailedJob(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["FAILED1"] = &JobRecord{
		ID: "FAILED1", Task: "test", Status: JobFailed,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodPost, "/jobs/FAILED1/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestHandleCancel_CancelledJob verifies that an already-CANCELLED job returns
// 409 Conflict.
func TestHandleCancel_CancelledJob(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["CANCELLED1"] = &JobRecord{
		ID: "CANCELLED1", Task: "test", Status: JobCancelled,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodPost, "/jobs/CANCELLED1/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestHandleCancel_NotFound verifies that cancelling a non-existent job returns
// 404.
func TestHandleCancel_NotFound(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodPost, "/jobs/NONEXISTENT/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

// --- handleOutput additional coverage ---

// TestHandleOutput_NoAttempts verifies that requesting output for a job with
// no attempts returns 404.
func TestHandleOutput_NoAttempts(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["NOATTEMPTS"] = &JobRecord{
		ID: "NOATTEMPTS", Task: "test", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/NOATTEMPTS/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for job with no attempts, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestHandleOutput_NotFound verifies that requesting output for a non-existent
// job returns 404.
func TestHandleOutput_NotFound(t *testing.T) {
	_, mux := newTestAPI(newMemStore())

	req := httptest.NewRequest(http.MethodGet, "/jobs/NONEXISTENT/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

// TestHandleOutput_TruncatedFlag verifies that the Truncated field is
// propagated from the latest attempt to the output response.
func TestHandleOutput_TruncatedFlag(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	exitCode := 0
	store.jobs["TRUNC1"] = &JobRecord{
		ID:        "TRUNC1",
		Task:      "test",
		Status:    JobSucceeded,
		CreatedAt: now,
		UpdatedAt: now,
		Attempts: []Attempt{
			{
				Number:    1,
				ExitCode:  &exitCode,
				Output:    "...last 32KB of output...",
				Truncated: true,
			},
		},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/TRUNC1/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp OutputResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if !resp.Truncated {
		t.Error("expected Truncated=true in response, got false")
	}
}

// TestHandleOutput_LatestAttempt verifies that when a job has multiple
// attempts, the output endpoint returns the last (most recent) one.
func TestHandleOutput_LatestAttempt(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	exit1, exit0 := 1, 0
	store.jobs["MULTI-ATT"] = &JobRecord{
		ID:        "MULTI-ATT",
		Task:      "test",
		Status:    JobSucceeded,
		CreatedAt: now,
		UpdatedAt: now,
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exit1, Output: "first attempt output"},
			{Number: 2, ExitCode: &exit0, Output: "second attempt output"},
		},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/MULTI-ATT/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp OutputResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if resp.Attempt != 2 {
		t.Errorf("expected attempt 2 (latest), got %d", resp.Attempt)
	}
	if resp.Output != "second attempt output" {
		t.Errorf("expected latest attempt output, got %q", resp.Output)
	}
}

// TestHandleOutput_StatusFieldIncluded verifies that the job status is included
// in the output response. This is critical for the chat bot: when an attempt
// fails but the job is retrying (status=PENDING), the bot must keep polling
// instead of reporting "Job failed".
func TestHandleOutput_StatusFieldIncluded(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	exitFail := -1

	// Job with a failed attempt but still retrying (PENDING).
	store.jobs["RETRYING"] = &JobRecord{
		ID:         "RETRYING",
		Task:       "retrying task",
		Status:     JobPending,
		CreatedAt:  now,
		UpdatedAt:  now,
		MaxRetries: 3,
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitFail, Output: "sandbox gone"},
		},
	}

	_, mux := newTestAPI(store)

	req := httptest.NewRequest(http.MethodGet, "/jobs/RETRYING/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp OutputResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if resp.Status != JobPending {
		t.Errorf("status = %q, want %q (job is retrying, not terminal)", resp.Status, JobPending)
	}
	if resp.ExitCode == nil || *resp.ExitCode != -1 {
		t.Errorf("exit_code = %v, want -1 (last attempt failed)", resp.ExitCode)
	}
}

// --- handleHealth additional coverage ---

// TestHandleHealth_Error verifies that when the health check function returns
// an error the endpoint returns 503 ServiceUnavailable with an error field.
func TestHandleHealth_Error(t *testing.T) {
	healthErr := errors.New("KV bucket unreachable")
	_, mux := newTestAPIFull(newMemStore(), nil, func() error { return healthErr })

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 when health check fails, got %d: %s", rec.Code, rec.Body.String())
	}

	var body map[string]string
	json.NewDecoder(rec.Body).Decode(&body)

	if body["status"] != "unhealthy" {
		t.Errorf("expected status=unhealthy, got %q", body["status"])
	}
	if body["error"] == "" {
		t.Error("expected non-empty error field in health response")
	}
}

// TestHandleHealth_NilHealthCheck verifies that when no health check is
// configured the endpoint always returns 200 ok.
func TestHandleHealth_NilHealthCheck(t *testing.T) {
	_, mux := newTestAPIFull(newMemStore(), nil, nil)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 with nil health check, got %d", rec.Code)
	}

	var body map[string]string
	json.NewDecoder(rec.Body).Decode(&body)

	if body["status"] != "ok" {
		t.Errorf("expected status=ok, got %q", body["status"])
	}
}
