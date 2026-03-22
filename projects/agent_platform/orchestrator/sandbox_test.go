package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"
)

// newTestSandbox creates a minimal SandboxExecutor suitable for testing HTTP
// methods. Kubernetes-dependent fields are left nil; only the HTTP client,
// inactivity timeout, and logger are set.
func newTestSandbox() *SandboxExecutor {
	return &SandboxExecutor{
		httpClient:        &http.Client{Timeout: 5 * time.Second},
		inactivityTimeout: 30 * time.Minute,
		logger:            slog.Default(),
	}
}

// ---- pollStatus tests -------------------------------------------------------

func TestPollStatus_Done(t *testing.T) {
	exitCode := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/status" || r.Method != http.MethodGet {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		json.NewEncoder(w).Encode(map[string]any{
			"state":     "done",
			"exit_code": exitCode,
		})
	}))
	defer srv.Close()

	s := newTestSandbox()
	state, code, err := s.pollStatus(context.Background(), srv.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "done" {
		t.Errorf("state = %q, want %q", state, "done")
	}
	if code != exitCode {
		t.Errorf("exit_code = %d, want %d", code, exitCode)
	}
}

func TestPollStatus_Running_NoExitCode(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"state": "running"})
	}))
	defer srv.Close()

	s := newTestSandbox()
	state, code, err := s.pollStatus(context.Background(), srv.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "running" {
		t.Errorf("state = %q, want %q", state, "running")
	}
	// nil exit_code in the JSON should be represented as -1.
	if code != -1 {
		t.Errorf("exit_code = %d, want -1 (nil)", code)
	}
}

func TestPollStatus_Failed(t *testing.T) {
	exitCode := 1
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"state":     "failed",
			"exit_code": exitCode,
		})
	}))
	defer srv.Close()

	s := newTestSandbox()
	state, code, err := s.pollStatus(context.Background(), srv.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "failed" {
		t.Errorf("state = %q, want %q", state, "failed")
	}
	if code != exitCode {
		t.Errorf("exit_code = %d, want %d", code, exitCode)
	}
}

func TestPollStatus_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	s := newTestSandbox()
	_, _, err := s.pollStatus(context.Background(), srv.URL)
	if err == nil {
		t.Fatal("expected error for 500 response, got nil")
	}
}

func TestPollStatus_BadJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "not json at all")
	}))
	defer srv.Close()

	s := newTestSandbox()
	_, _, err := s.pollStatus(context.Background(), srv.URL)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

// ---- pollOutput tests -------------------------------------------------------

func TestPollOutput_ReturnsBodyAndParsesOffsetHeader(t *testing.T) {
	outputData := []byte("hello from goose\n")
	newOffset := 42
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/output" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		// Verify the client sent the current offset as a query param.
		if got := r.URL.Query().Get("offset"); got != "0" {
			t.Errorf("offset param = %q, want %q", got, "0")
		}
		w.Header().Set("X-Output-Offset", strconv.Itoa(newOffset))
		w.WriteHeader(http.StatusOK)
		w.Write(outputData)
	}))
	defer srv.Close()

	s := newTestSandbox()
	buf := newSyncBuffer(0)
	gotOffset, err := s.pollOutput(context.Background(), srv.URL, 0, buf)
	if err != nil {
		t.Fatalf("pollOutput: %v", err)
	}
	if gotOffset != newOffset {
		t.Errorf("offset = %d, want %d", gotOffset, newOffset)
	}
	if buf.String() != string(outputData) {
		t.Errorf("buffer = %q, want %q", buf.String(), string(outputData))
	}
}

func TestPollOutput_NoOffsetHeader_KeepsOriginalOffset(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// No X-Output-Offset header — simulate old runner.
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("some data"))
	}))
	defer srv.Close()

	s := newTestSandbox()
	buf := newSyncBuffer(0)
	originalOffset := 17
	gotOffset, err := s.pollOutput(context.Background(), srv.URL, originalOffset, buf)
	if err != nil {
		t.Fatalf("pollOutput: %v", err)
	}
	// Without the header the offset should remain unchanged.
	if gotOffset != originalOffset {
		t.Errorf("offset = %d, want %d (unchanged)", gotOffset, originalOffset)
	}
}

func TestPollOutput_EmptyBody_NoWrite(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Output-Offset", "5")
		w.WriteHeader(http.StatusOK)
		// Deliberately empty body.
	}))
	defer srv.Close()

	s := newTestSandbox()
	buf := newSyncBuffer(0)
	gotOffset, err := s.pollOutput(context.Background(), srv.URL, 0, buf)
	if err != nil {
		t.Fatalf("pollOutput: %v", err)
	}
	if gotOffset != 5 {
		t.Errorf("offset = %d, want 5", gotOffset)
	}
	if buf.Len() != 0 {
		t.Errorf("buffer should be empty, got %d bytes", buf.Len())
	}
}

func TestPollOutput_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	s := newTestSandbox()
	buf := newSyncBuffer(0)
	originalOffset := 10
	gotOffset, err := s.pollOutput(context.Background(), srv.URL, originalOffset, buf)
	if err == nil {
		t.Fatal("expected error for non-200 response, got nil")
	}
	// Offset should remain unchanged on error.
	if gotOffset != originalOffset {
		t.Errorf("offset on error = %d, want original %d", gotOffset, originalOffset)
	}
}

func TestPollOutput_SendsOffsetAsQueryParam(t *testing.T) {
	var receivedOffset string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedOffset = r.URL.Query().Get("offset")
		w.Header().Set("X-Output-Offset", "100")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	s := newTestSandbox()
	buf := newSyncBuffer(0)
	s.pollOutput(context.Background(), srv.URL, 55, buf)
	if receivedOffset != "55" {
		t.Errorf("server received offset = %q, want %q", receivedOffset, "55")
	}
}

// ---- dispatchTask tests -----------------------------------------------------

func TestDispatchTask_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/run" {
			t.Errorf("unexpected %s %s", r.Method, r.URL.Path)
		}
		if ct := r.Header.Get("Content-Type"); ct != "application/json" {
			t.Errorf("Content-Type = %q, want application/json", ct)
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	s := newTestSandbox()
	if err := s.dispatchTask(context.Background(), srv.URL, "fix the bug", "/recipes/fix.yaml"); err != nil {
		t.Fatalf("dispatchTask: %v", err)
	}
}

func TestDispatchTask_PayloadContainsTaskAndRecipePath(t *testing.T) {
	var body []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	task := "run some tests"
	recipePath := "/opt/recipes/test.yaml"
	s := newTestSandbox()
	s.dispatchTask(context.Background(), srv.URL, task, recipePath)

	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatalf("bad JSON payload: %v", err)
	}
	if payload["task"] != task {
		t.Errorf("payload.task = %v, want %q", payload["task"], task)
	}
	if payload["recipe_path"] != recipePath {
		t.Errorf("payload.recipe_path = %v, want %q", payload["recipe_path"], recipePath)
	}
}

func TestDispatchTask_EmptyRecipePath_OmittedFromPayload(t *testing.T) {
	var body []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	s := newTestSandbox()
	s.dispatchTask(context.Background(), srv.URL, "task without recipe", "")

	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatalf("bad JSON payload: %v", err)
	}
	if _, ok := payload["recipe_path"]; ok {
		t.Error("recipe_path should be omitted when empty (omitempty)")
	}
}

func TestDispatchTask_InactivityTimeoutInPayload(t *testing.T) {
	var body []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	timeout := 45 * time.Minute
	s := &SandboxExecutor{
		httpClient:        &http.Client{Timeout: 5 * time.Second},
		inactivityTimeout: timeout,
		logger:            slog.Default(),
	}
	s.dispatchTask(context.Background(), srv.URL, "long task", "")

	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatalf("bad JSON payload: %v", err)
	}
	// inactivity_timeout should be seconds.
	got, ok := payload["inactivity_timeout"].(float64)
	if !ok {
		t.Fatalf("inactivity_timeout missing or wrong type in payload: %v", payload)
	}
	want := timeout.Seconds()
	if got != want {
		t.Errorf("inactivity_timeout = %v, want %v", got, want)
	}
}

func TestDispatchTask_NonAcceptedResponse_ReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "too many requests", http.StatusTooManyRequests)
	}))
	defer srv.Close()

	s := newTestSandbox()
	if err := s.dispatchTask(context.Background(), srv.URL, "task", ""); err == nil {
		t.Fatal("expected error for non-202 response, got nil")
	}
}

// ---- RunnerBaseURL (legacy trivial test kept for regression) ----------------

func TestRunnerBaseURL(t *testing.T) {
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	fqdn := "goose-sandbox-abc123.goose-sandboxes.svc.cluster.local"
	url := fmt.Sprintf("http://%s:8081", fqdn)
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	expected := "http://goose-sandbox-abc123.goose-sandboxes.svc.cluster.local:8081"
	if url != expected {
		t.Errorf("url = %q, want %q", url, expected)
	}
}

func TestPollStatusWithPlan(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"state":        "running",
			"current_step": 1,
			"plan": []map[string]string{
				{"agent": "research", "description": "investigate", "status": "completed"},
				{"agent": "code-fix", "description": "fix", "status": "running"},
			},
		})
	}))
	defer srv.Close()

	executor := &SandboxExecutor{
		httpClient: srv.Client(),
		logger:     slog.Default(),
	}

	state, exitCode, plan, err := executor.pollStatusWithPlan(context.Background(), srv.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "running" {
		t.Errorf("state: got %q, want %q", state, "running")
	}
	if exitCode != -1 {
		t.Errorf("exitCode: got %d, want -1", exitCode)
	}
	if len(plan) != 2 {
		t.Fatalf("expected 2 plan steps, got %d", len(plan))
	}
	if plan[0].Agent != "research" {
		t.Errorf("plan[0].Agent: got %q, want %q", plan[0].Agent, "research")
	}
	if plan[0].Description != "investigate" {
		t.Errorf("plan[0].Description: got %q, want %q", plan[0].Description, "investigate")
	}
	if plan[0].Status != "completed" {
		t.Errorf("plan[0].Status: got %q, want %q", plan[0].Status, "completed")
	}
	if plan[1].Agent != "code-fix" {
		t.Errorf("plan[1].Agent: got %q, want %q", plan[1].Agent, "code-fix")
	}
	if plan[1].Status != "running" {
		t.Errorf("plan[1].Status: got %q, want %q", plan[1].Status, "running")
	}
}

func TestPollStatusWithPlanDone(t *testing.T) {
	exitCode := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"state":        "done",
			"exit_code":    exitCode,
			"current_step": 2,
			"plan": []map[string]string{
				{"agent": "research", "description": "investigate", "status": "completed"},
				{"agent": "code-fix", "description": "fix", "status": "completed"},
			},
		})
	}))
	defer srv.Close()

	executor := &SandboxExecutor{
		httpClient: srv.Client(),
		logger:     slog.Default(),
	}

	state, ec, plan, err := executor.pollStatusWithPlan(context.Background(), srv.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "done" {
		t.Errorf("state: got %q, want %q", state, "done")
	}
	if ec != 0 {
		t.Errorf("exitCode: got %d, want 0", ec)
	}
	if len(plan) != 2 {
		t.Fatalf("expected 2 plan steps, got %d", len(plan))
	}
}

func TestPollStatusWithPlanNoPlan(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"state": "running",
		})
	}))
	defer srv.Close()

	executor := &SandboxExecutor{
		httpClient: srv.Client(),
		logger:     slog.Default(),
	}

	state, exitCode, plan, err := executor.pollStatusWithPlan(context.Background(), srv.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "running" {
		t.Errorf("state: got %q, want %q", state, "running")
	}
	if exitCode != -1 {
		t.Errorf("exitCode: got %d, want -1", exitCode)
	}
	if len(plan) != 0 {
		t.Errorf("expected empty plan, got %d steps", len(plan))
	}
}

func TestPollStatusWithPlan_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	executor := &SandboxExecutor{
		httpClient: srv.Client(),
		logger:     slog.Default(),
	}

	_, _, _, err := executor.pollStatusWithPlan(context.Background(), srv.URL)
	if err == nil {
		t.Fatal("expected error for 500 response, got nil")
	}
}

func TestPollStatusWithPlan_BadJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "not valid json")
	}))
	defer srv.Close()

	executor := &SandboxExecutor{
		httpClient: srv.Client(),
		logger:     slog.Default(),
	}

	_, _, _, err := executor.pollStatusWithPlan(context.Background(), srv.URL)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

// ---- pollUntilDone tests ----------------------------------------------------

// TestPollUntilDone_ZeroMaxPollErrors_FallbackToTen verifies that when
// maxPollErrors is 0 (zero-value struct field), pollUntilDone applies a
// defensive default of 10 and does not abort after a single status poll
// failure.
//
// Without the fallback, a zero threshold would evaluate
// consecutiveErrors(1) >= maxErrors(0) as true on the very first error,
// causing pollUntilDone to give up on any transient network hiccup. The
// fallback of 10 means the function tolerates bursts of errors and only
// terminates after 10 consecutive failures.
//
// The test uses a context that expires shortly after the initial 5-second
// timer fires. With a working fallback the first failure leaves
// consecutiveErrors=1<10, the loop continues, and the context eventually
// expires → DeadlineExceeded. A broken implementation with maxErrors=0 would
// instead return "unreachable after 0 consecutive poll failures" before the
// context expires.
//
// Note: this test takes ~6 seconds because pollUntilDone's initial timer is
// hardcoded to 5 seconds.
func TestPollUntilDone_ZeroMaxPollErrors_FallbackToTen(t *testing.T) {
	// Server: output always OK; status always returns 500 to simulate a
	// persistent, transient outage.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/output":
			w.Header().Set("X-Output-Offset", "0")
			w.WriteHeader(http.StatusOK)
		default: // /status
			http.Error(w, "service unavailable", http.StatusServiceUnavailable)
		}
	}))
	defer srv.Close()

	s := newTestSandbox()
	s.maxPollErrors = 0 // zero-value struct field — defensive fallback must apply (10)

	// Timeout long enough for one poll cycle (initial timer fires at 5 s) but
	// far shorter than ten failures (5 s + 9×30 s = 275 s). This verifies the
	// effective threshold is NOT 0 or 1 without waiting for all 10 failures.
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()

	outputBuf := newSyncBuffer(0)
	_, err := s.pollUntilDone(ctx, srv.URL, "test-claim", func() bool { return false }, outputBuf, nil)

	// With fallback maxErrors=10: after the first failure at ~5 s,
	// consecutiveErrors=1 which is less than 10, so the loop continues and
	// waits for the next ticker. The context expires at 6 s → DeadlineExceeded.
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Errorf("got %v, want context.DeadlineExceeded (fallback=10 not yet reached after 1 failure)", err)
	}
}
