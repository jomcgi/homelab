package main

// orchestrator_coverage_test.go covers the remaining edge cases and error paths
// across api.go, consumer.go, reconcile.go, clean.go, and sandbox.go that are
// not exercised by the other test files.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	dynamicfake "k8s.io/client-go/dynamic/fake"
)

// ============================================================
// Shared test helpers (local to this file)
// ============================================================

// failPutStore wraps a Store and always returns an error for Put operations.
type failPutStore struct {
	inner Store
}

func (f *failPutStore) Get(ctx context.Context, id string) (*JobRecord, error) {
	return f.inner.Get(ctx, id)
}

func (f *failPutStore) Put(_ context.Context, _ *JobRecord) error {
	return errors.New("put failed")
}

func (f *failPutStore) Delete(ctx context.Context, id string) error {
	return f.inner.Delete(ctx, id)
}

func (f *failPutStore) List(ctx context.Context, sf, tf []string, limit, offset int) ([]JobRecord, int, error) {
	return f.inner.List(ctx, sf, tf, limit, offset)
}

// failListStore wraps a Store and always returns an error for List operations.
type failListStore struct {
	inner Store
}

func (f *failListStore) Get(ctx context.Context, id string) (*JobRecord, error) {
	return f.inner.Get(ctx, id)
}

func (f *failListStore) Put(ctx context.Context, job *JobRecord) error {
	return f.inner.Put(ctx, job)
}

func (f *failListStore) Delete(ctx context.Context, id string) error {
	return f.inner.Delete(ctx, id)
}

func (f *failListStore) List(_ context.Context, _, _ []string, _, _ int) ([]JobRecord, int, error) {
	return nil, 0, errors.New("list failed")
}

// newCoverageDynClient creates a fake dynamic client for coverage tests.
func newCoverageDynClient(objects ...runtime.Object) *dynamicfake.FakeDynamicClient {
	dynScheme := runtime.NewScheme()
	return dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxClaimGVR: "SandboxClaimList",
			sandboxGVR:      "SandboxList",
		},
		objects...,
	)
}

// ============================================================
// api.go — handleList() edge cases
// ============================================================

// TestHandleList_InvalidOffsetStringIsIgnored verifies that a non-numeric
// offset string (e.g. "abc") is silently ignored and offset=0 is used.
func TestHandleList_InvalidOffsetStringIsIgnored(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	store.jobs["JOB-OFF-STR"] = &JobRecord{
		ID: "JOB-OFF-STR", Task: "t", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPI(store)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs?offset=abc", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	if len(resp.Jobs) != 1 {
		t.Errorf("expected 1 job with invalid offset ignored, got %d", len(resp.Jobs))
	}
}

// TestHandleList_LimitExactly101IsClamped verifies that limit=101 is clamped
// to 100 (the boundary one above the max).
func TestHandleList_LimitExactly101IsClamped(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	for i := 0; i < 3; i++ {
		id := fmt.Sprintf("JOB-CLAMP101-%d", i)
		store.jobs[id] = &JobRecord{
			ID: id, Task: "t", Status: JobPending,
			CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
		}
	}

	_, mux := newTestAPI(store)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs?limit=101", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var resp ListResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	if len(resp.Jobs) != 3 {
		t.Errorf("expected 3 jobs with limit=101 clamped to 100, got %d", len(resp.Jobs))
	}
}

// TestHandleList_StoreListError verifies that a store.List failure returns 500.
func TestHandleList_StoreListError(t *testing.T) {
	_, mux := newTestAPIFull(&failListStore{inner: newMemStore()}, nil, nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/jobs", nil))
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 on store.List failure, got %d", rec.Code)
	}
}

// ============================================================
// api.go — handleCancel() store.Put failure (race condition path)
// ============================================================

// TestHandleCancel_StorePutFailure verifies that when store.Put fails after
// the status check, a 500 is returned (simulates a race/write failure).
func TestHandleCancel_StorePutFailure(t *testing.T) {
	inner := newMemStore()
	now := time.Now().UTC()
	inner.jobs["CANCEL-PUT-FAIL"] = &JobRecord{
		ID: "CANCEL-PUT-FAIL", Task: "test", Status: JobPending,
		CreatedAt: now, UpdatedAt: now, Attempts: []Attempt{},
	}

	_, mux := newTestAPIFull(&failPutStore{inner: inner}, nil, nil)
	req := httptest.NewRequest(http.MethodPost, "/jobs/CANCEL-PUT-FAIL/cancel", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when store.Put fails on cancel, got %d: %s", rec.Code, rec.Body.String())
	}
}

// ============================================================
// api.go — handleOutput() with nil Attempt.Result
// ============================================================

// TestHandleOutput_NilResult verifies that when the latest attempt has a nil
// Result, the output endpoint returns 200 and result is omitted without panic.
func TestHandleOutput_NilResult(t *testing.T) {
	store := newMemStore()
	now := time.Now().UTC()
	exitCode := 0
	store.jobs["NIL-RESULT"] = &JobRecord{
		ID:        "NIL-RESULT",
		Task:      "test",
		Status:    JobSucceeded,
		CreatedAt: now,
		UpdatedAt: now,
		Attempts: []Attempt{
			{
				Number:   1,
				ExitCode: &exitCode,
				Output:   "done\n",
				Result:   nil,
			},
		},
	}

	_, mux := newTestAPI(store)
	req := httptest.NewRequest(http.MethodGet, "/jobs/NIL-RESULT/output", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp OutputResponse
	json.NewDecoder(rec.Body).Decode(&resp)

	if resp.Result != nil {
		t.Errorf("expected nil Result in response, got %+v", resp.Result)
	}
	if resp.Output != "done\n" {
		t.Errorf("output = %q, want %q", resp.Output, "done\n")
	}
}

// ============================================================
// consumer.go — processJob() with empty job ID
// ============================================================

// TestProcessJob_EmptyJobIDIsACKed verifies that a NATS message whose payload
// is an empty string (empty job ID) is ACKed to prevent infinite redelivery.
func TestProcessJob_EmptyJobIDIsACKed(t *testing.T) {
	store := newMemStore()
	msg := newFakeMsg([]byte("")) // empty job ID → store.Get fails → ACK
	c := newTestConsumer(store, &fakeSandbox{})
	c.processJob(context.Background(), msg)
	if !msg.acked.Load() {
		t.Error("expected ACK for message with empty job ID (poison message)")
	}
	if msg.nacked.Load() {
		t.Error("expected no NAK for message with empty job ID")
	}
}

// TestProcessJob_SandboxClaimNameIsLowercased verifies that the claim name
// derived from a job ID with uppercase letters is all-lowercase.
func TestProcessJob_SandboxClaimNameIsLowercased(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-UPPER-CASE-ID")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	var capturedClaimName string
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, claimName, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			capturedClaimName = claimName
			return &ExecResult{ExitCode: 0}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if capturedClaimName == "" {
		t.Fatal("expected non-empty claim name")
	}
	if strings.ToLower(capturedClaimName) != capturedClaimName {
		t.Errorf("claim name %q is not all-lowercase", capturedClaimName)
	}
}

// ============================================================
// consumer.go — flushProgress() with plan data but empty output buffer
// ============================================================

// TestFlushProgress_PlanDataFlushedWithEmptyOutput verifies that flushProgress
// writes plan data to the store even when the output buffer is empty.
func TestFlushProgress_PlanDataFlushedWithEmptyOutput(t *testing.T) {
	store := newMemStore()
	job := &JobRecord{
		ID:       "JOB-PLAN-FLUSH",
		Task:     "plan flush test",
		Status:   JobRunning,
		Attempts: []Attempt{{Number: 1, StartedAt: time.Now().UTC()}},
	}
	_ = store.Put(context.Background(), job)

	c := newTestConsumer(store, &fakeSandbox{})
	buf := newSyncBuffer(maxOutputBytes) // empty buffer
	planBuf := &planTracker{}
	plan := []PlanStep{
		{Agent: "planner", Description: "Step 1", Status: "running"},
		{Agent: "coder", Description: "Step 2", Status: "pending"},
	}
	planBuf.Update(plan, 0)

	c.flushProgress(context.Background(), job.ID, buf, planBuf)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if len(got.Plan) != 2 {
		t.Errorf("expected plan flushed with 2 steps, got %d", len(got.Plan))
	}
	if got.Plan[0].Description != "Step 1" {
		t.Errorf("plan[0].Description = %q, want %q", got.Plan[0].Description, "Step 1")
	}
}

// TestFlushProgress_EmptyPlanBufDoesNotOverwriteExistingPlan verifies that
// when planBuf has no data, the existing plan on the job is not cleared.
func TestFlushProgress_EmptyPlanBufDoesNotOverwriteExistingPlan(t *testing.T) {
	store := newMemStore()
	existingPlan := []PlanStep{{Agent: "agent", Description: "Existing step", Status: "completed"}}
	job := &JobRecord{
		ID:       "JOB-PLAN-NOOVERWRITE",
		Task:     "test",
		Status:   JobRunning,
		Plan:     existingPlan,
		Attempts: []Attempt{{Number: 1, StartedAt: time.Now().UTC()}},
	}
	_ = store.Put(context.Background(), job)

	c := newTestConsumer(store, &fakeSandbox{})
	buf := newSyncBuffer(maxOutputBytes)
	buf.Write([]byte("some output"))
	planBuf := &planTracker{} // empty plan tracker

	c.flushProgress(context.Background(), job.ID, buf, planBuf)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	// The plan in the store came from the re-read job (which has existingPlan),
	// and since planBuf is empty, it should remain the same.
	if len(got.Plan) != 1 || got.Plan[0].Description != "Existing step" {
		t.Errorf("plan was unexpectedly modified: %+v", got.Plan)
	}
}

// ============================================================
// reconcile.go — store.Put() failure paths
// ============================================================

// TestReconcileOrphanedJobs_ForceFail_StorePutFails verifies that when
// store.Put() fails during force-fail, the error is logged without panic.
func TestReconcileOrphanedJobs_ForceFail_StorePutFails(t *testing.T) {
	inner := newMemStore()
	ctx := context.Background()

	_ = inner.Put(ctx, &JobRecord{
		ID:         "job-force-fail-put-err",
		Task:       "force fail test",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "",
			StartedAt:        time.Now().Add(-3 * time.Hour),
		}},
	})

	failStore := &failPutStore{inner: inner}
	// maxDuration=1h, attempt started 3h ago → force-fail path triggered.
	reconcileOrphanedJobs(ctx, failStore, nil, "goose-sandboxes", nil, nil, 1*time.Hour, slog.Default())
}

// TestReconcileOrphanedJobs_AllJobsWithEmptyClaims verifies that multiple
// RUNNING jobs with empty SandboxClaimNames are reset to PENDING without panic.
func TestReconcileOrphanedJobs_AllJobsWithEmptyClaims(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	for i := 0; i < 3; i++ {
		id := fmt.Sprintf("job-empty-claim-%d", i)
		_ = store.Put(ctx, &JobRecord{
			ID:         id,
			Task:       "task",
			Status:     JobRunning,
			MaxRetries: 2,
			Attempts: []Attempt{{
				Number:           1,
				SandboxClaimName: "",
				StartedAt:        time.Now().Add(-1 * time.Hour),
			}},
		})
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, 0, slog.Default())

	for i := 0; i < 3; i++ {
		id := fmt.Sprintf("job-empty-claim-%d", i)
		job, err := store.Get(ctx, id)
		if err != nil {
			t.Fatalf("Get(%s): %v", id, err)
		}
		if job.Status != JobPending {
			t.Errorf("%s: status = %s, want PENDING", id, job.Status)
		}
	}
}

// TestReconcileOrphanedJobs_PutFailureDuringReset verifies that store.Put
// failure during the PENDING reset is logged without panic.
func TestReconcileOrphanedJobs_PutFailureDuringReset(t *testing.T) {
	inner := newMemStore()
	ctx := context.Background()

	_ = inner.Put(ctx, &JobRecord{
		ID:         "job-reset-put-fail",
		Task:       "test",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	failStore := &failPutStore{inner: inner}
	reconcileOrphanedJobs(ctx, failStore, nil, "goose-sandboxes", nil, nil, 0, slog.Default())
}

// ============================================================
// reconcile.go — cleanupSandboxClaim() extra paths
// ============================================================

// TestCleanupSandboxClaim_NilClientIsNoOp verifies nil dynClient returns
// immediately even with a real claim name — no panic.
func TestCleanupSandboxClaim_NilClientIsNoOp(t *testing.T) {
	cleanupSandboxClaim(context.Background(), nil, "ns", "some-claim", slog.Default())
}

// TestCleanupSandboxClaim_DoubleDelete verifies that deleting an already-
// deleted claim (IsNotFound) is silently swallowed without panic.
func TestCleanupSandboxClaim_DoubleDelete(t *testing.T) {
	ns := "test-ns"
	claimName := "cleanup-double-delete-test"

	dynClient := newCoverageDynClient()
	s := &SandboxExecutor{
		dynClient: dynClient,
		namespace: ns,
		template:  "tmpl",
		logger:    slog.Default(),
	}
	if err := s.createClaim(context.Background(), claimName); err != nil {
		t.Fatalf("createClaim: %v", err)
	}

	cleanupSandboxClaim(context.Background(), dynClient, ns, claimName, slog.Default())
	// Second call → IsNotFound, must not panic or log a warning.
	cleanupSandboxClaim(context.Background(), dynClient, ns, claimName, slog.Default())

	_, err := dynClient.Resource(sandboxClaimGVR).Namespace(ns).Get(
		context.Background(), claimName, metav1.GetOptions{})
	if err == nil {
		t.Fatal("expected error getting deleted claim, got nil")
	}
}

// ============================================================
// clean.go — edge cases not covered by clean_test.go
// ============================================================

// TestCleanOutput_UnclosedGooseResultBlock verifies that an unclosed
// ```goose-result block does not panic and the content is preserved.
func TestCleanOutput_UnclosedGooseResultBlock(t *testing.T) {
	raw := "output before\n\n```goose-result\ntype: pr\nurl: https://github.com/foo\n"
	got := cleanOutput(raw)
	if !strings.Contains(got, "output before") {
		t.Errorf("expected content before unclosed block preserved, got %q", got)
	}
	if !strings.Contains(got, "```goose-result") {
		t.Errorf("expected unclosed goose-result block to remain, got %q", got)
	}
}

// TestCleanOutput_RecipeMarkerAtEndOfString verifies that "Loading recipe:"
// appearing at the end of the string (no \n\n) removes from the marker to EOF.
func TestCleanOutput_RecipeMarkerAtEndOfString(t *testing.T) {
	raw := "useful output\n\nLoading recipe: Deep Plan\nDescription: does stuff"
	got := cleanOutput(raw)
	if strings.Contains(got, "Loading recipe:") {
		t.Errorf("expected recipe marker removed when no trailing \\n\\n, got %q", got)
	}
	if !strings.Contains(got, "useful output") {
		t.Errorf("expected content before recipe marker preserved, got %q", got)
	}
}

// TestCleanOutput_AdjacentBanners verifies that two goose banners directly
// adjacent are both stripped cleanly.
func TestCleanOutput_AdjacentBanners(t *testing.T) {
	raw := "   L L\tgoose is ready\n   L L\tgoose is ready\nactual output\n"
	got := cleanOutput(raw)
	if strings.Contains(got, "goose is ready") {
		t.Errorf("expected both adjacent banners stripped, got %q", got)
	}
	if !strings.Contains(got, "actual output") {
		t.Errorf("expected actual output preserved after adjacent banners, got %q", got)
	}
}

// TestCleanOutput_BannerWithNoArtLines verifies that a bare "goose is ready"
// line with no preceding art lines is still stripped.
func TestCleanOutput_BannerWithNoArtLines(t *testing.T) {
	raw := "some output\ngoose is ready\nmore output\n"
	got := cleanOutput(raw)
	if strings.Contains(got, "goose is ready") {
		t.Errorf("expected lone 'goose is ready' stripped, got %q", got)
	}
	if !strings.Contains(got, "some output") || !strings.Contains(got, "more output") {
		t.Errorf("expected surrounding content preserved, got %q", got)
	}
}

// ============================================================
// sandbox.go — resolveSandboxServiceFQDN() edge cases
// ============================================================

// TestResolveSandboxServiceFQDN_MissingStatus verifies that a sandbox with no
// "status" field returns an error containing "no status".
func TestResolveSandboxServiceFQDN_MissingStatus(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-no-status"

	sandboxObj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "agents.x-k8s.io/v1alpha1",
			"kind":       "Sandbox",
			"metadata":   map[string]interface{}{"name": sandboxName, "namespace": ns},
			// No "status".
		},
	}

	dynClient := newCoverageDynClient()
	if _, err := dynClient.Resource(sandboxGVR).Namespace(ns).Create(
		context.Background(), sandboxObj, metav1.CreateOptions{}); err != nil {
		t.Fatalf("creating sandbox: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}
	_, err := s.resolveSandboxServiceFQDN(context.Background(), sandboxName)
	if err == nil {
		t.Fatal("expected error for sandbox with missing status, got nil")
	}
	if !strings.Contains(err.Error(), "no status") {
		t.Errorf("expected 'no status' in error, got: %v", err)
	}
}

// TestResolveSandboxServiceFQDN_MissingServiceFQDN verifies that a sandbox
// whose status lacks "serviceFQDN" returns an error containing "serviceFQDN".
func TestResolveSandboxServiceFQDN_MissingServiceFQDN(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-no-fqdn"

	sandboxObj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "agents.x-k8s.io/v1alpha1",
			"kind":       "Sandbox",
			"metadata":   map[string]interface{}{"name": sandboxName, "namespace": ns},
			"status":     map[string]interface{}{"phase": "Running"},
		},
	}

	dynClient := newCoverageDynClient()
	if _, err := dynClient.Resource(sandboxGVR).Namespace(ns).Create(
		context.Background(), sandboxObj, metav1.CreateOptions{}); err != nil {
		t.Fatalf("creating sandbox: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}
	_, err := s.resolveSandboxServiceFQDN(context.Background(), sandboxName)
	if err == nil {
		t.Fatal("expected error for sandbox with missing serviceFQDN, got nil")
	}
	if !strings.Contains(err.Error(), "serviceFQDN") {
		t.Errorf("expected 'serviceFQDN' in error, got: %v", err)
	}
}

// ============================================================
// sandbox.go — pollUntilDone() error threshold behaviour
// ============================================================

// TestPollUntilDone_MaxPollErrorsZeroUsesDefault verifies that maxPollErrors=0
// uses the effective default threshold of 10, not 0. With 1 error then success,
// the call must NOT fail (contrast: maxPollErrors=1 exits after 1 error).
// NOTE: pollUntilDone has a 5s initial timer + 30s ticker, so this test ~35s.
func TestPollUntilDone_MaxPollErrorsZeroUsesDefault(t *testing.T) {
	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/output" {
			w.WriteHeader(http.StatusOK)
			return
		}
		callCount++
		if callCount == 1 {
			// First poll fails; with threshold=0 this would error out,
			// but with the correct default=10 the loop continues.
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		json.NewEncoder(w).Encode(map[string]any{"state": "done", "exit_code": 0})
	}))
	defer srv.Close()

	s := newTestSandbox()
	s.maxPollErrors = 0 // 0 → default 10

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	buf := newSyncBuffer(maxOutputBytes)
	result, err := s.pollUntilDone(ctx, srv.URL, "test-claim", func() bool { return false }, buf, &planTracker{})
	if err != nil {
		t.Fatalf("expected success after 1 error (threshold=0→default 10), got: %v", err)
	}
	if result == nil || result.ExitCode != 0 {
		t.Errorf("expected ExitCode=0, got result=%v", result)
	}
}

// TestPollUntilDone_DeadlineExceededWithRunningState verifies that
// pollUntilDone returns a context error when the context deadline fires
// (before the 5s initial timer) while the runner is in "running" state.
func TestPollUntilDone_DeadlineExceededWithRunningState(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/output" {
			w.WriteHeader(http.StatusOK)
			return
		}
		// Always running — never completes.
		json.NewEncoder(w).Encode(map[string]any{"state": "running"})
	}))
	defer srv.Close()

	s := newTestSandbox()
	// 100ms deadline fires before the 5s initial timer → ctx.Done() wins.
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	buf := newSyncBuffer(maxOutputBytes)
	_, err := s.pollUntilDone(ctx, srv.URL, "test-claim", func() bool { return false }, buf, &planTracker{})
	if err == nil {
		t.Fatal("expected error when context deadline exceeded, got nil")
	}
	if !errors.Is(err, context.DeadlineExceeded) && !errors.Is(err, context.Canceled) {
		t.Errorf("expected context error, got: %v", err)
	}
}
