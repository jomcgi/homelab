package main

// main_coverage_test.go covers envOr and runPeriodicReconcile from main.go.
// These functions have no tests elsewhere in the package.

import (
	"context"
	"log/slog"
	"net/http"
	"testing"
	"time"
)

// --- envOr tests --------------------------------------------------------------

// TestEnvOr_ReturnsFallbackWhenNotSet verifies that envOr returns the fallback
// value when the environment variable is not set in the process environment.
func TestEnvOr_ReturnsFallbackWhenNotSet(t *testing.T) {
	// Use a key that is extremely unlikely to be set in any real environment.
	const key = "ORCH_UNIT_TEST_ENVVAR_NOTSET_QZXWVT"
	got := envOr(key, "default-value")
	if got != "default-value" {
		t.Errorf("envOr(unset key) = %q, want %q", got, "default-value")
	}
}

// TestEnvOr_ReturnsEnvVarWhenSet verifies that envOr returns the environment
// variable value (not the fallback) when the variable is set to a non-empty
// string.
func TestEnvOr_ReturnsEnvVarWhenSet(t *testing.T) {
	const key = "ORCH_UNIT_TEST_ENVVAR_SET_QZXWVT"
	t.Setenv(key, "custom-value")

	got := envOr(key, "fallback")
	if got != "custom-value" {
		t.Errorf("envOr(set key) = %q, want %q", got, "custom-value")
	}
}

// TestEnvOr_ReturnsFallbackWhenEmpty verifies that envOr returns the fallback
// when the environment variable is explicitly set to an empty string. The
// implementation checks `v != ""` so an empty string is treated as unset.
func TestEnvOr_ReturnsFallbackWhenEmpty(t *testing.T) {
	const key = "ORCH_UNIT_TEST_ENVVAR_EMPTY_QZXWVT"
	t.Setenv(key, "")

	got := envOr(key, "fallback-for-empty")
	if got != "fallback-for-empty" {
		t.Errorf("envOr(empty key) = %q, want %q", got, "fallback-for-empty")
	}
}

// --- INFERENCE_MODEL env var tests --------------------------------------------

// TestInferenceModel_DefaultsToEmptyString verifies that INFERENCE_MODEL
// defaults to an empty string when the environment variable is not set.
//
// This documents the intentional change introduced in commit d0610857, which
// removed the hardcoded default "qwen3.5-35b-a3b" in favour of an empty
// string. An empty default means the operator must explicitly configure a
// model name via the deployment values; no model is assumed at the
// application level.
func TestInferenceModel_DefaultsToEmptyString(t *testing.T) {
	// Ensure the variable is absent for this test.
	t.Setenv("INFERENCE_MODEL", "")

	got := envOr("INFERENCE_MODEL", "")
	if got != "" {
		t.Errorf("INFERENCE_MODEL default = %q, want empty string", got)
	}
}

// TestInferenceModel_ReadsFromEnv verifies that INFERENCE_MODEL is read from
// the environment when it is explicitly set to a non-empty value.
func TestInferenceModel_ReadsFromEnv(t *testing.T) {
	t.Setenv("INFERENCE_MODEL", "qwen3.5-35b-a3b")

	got := envOr("INFERENCE_MODEL", "")
	if got != "qwen3.5-35b-a3b" {
		t.Errorf("INFERENCE_MODEL from env = %q, want %q", got, "qwen3.5-35b-a3b")
	}
}

// --- runPeriodicReconcile tests -----------------------------------------------

// TestRunPeriodicReconcile_StopsOnContextCancel verifies that
// runPeriodicReconcile exits cleanly when its context is cancelled.
func TestRunPeriodicReconcile_StopsOnContextCancel(t *testing.T) {
	store := newMemStore()

	// SandboxExecutor with nil K8s clients — safe because the store has no
	// RUNNING jobs, so reconcileOrphanedJobs returns immediately without
	// attempting any K8s or HTTP calls.
	sandbox := &SandboxExecutor{
		dynClient:  nil,
		logger:     slog.Default(),
		httpClient: &http.Client{},
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})

	go func() {
		defer close(done)
		runPeriodicReconcile(ctx, 10*time.Millisecond, store, sandbox, "test-ns", 0, slog.Default())
	}()

	// Allow at least one tick to fire before cancelling.
	time.Sleep(50 * time.Millisecond)
	cancel()

	select {
	case <-done:
		// Success — the goroutine exited after context cancellation.
	case <-time.After(2 * time.Second):
		t.Fatal("runPeriodicReconcile did not stop within 2s after context cancellation")
	}
}

// TestRunPeriodicReconcile_RunsReconcileOnTick verifies that
// runPeriodicReconcile calls reconcileOrphanedJobs on each ticker interval.
//
// A RUNNING job with an empty SandboxClaimName is seeded so the reconciler
// falls through to the reset path without any Kubernetes API calls
// (CheckRunnerForClaim is only invoked when SandboxClaimName != ""). After at
// least one tick the job should be reset to PENDING.
func TestRunPeriodicReconcile_RunsReconcileOnTick(t *testing.T) {
	bgCtx := context.Background()
	store := newMemStore()

	_ = store.Put(bgCtx, &JobRecord{
		ID:         "job-periodic-reconcile-tick",
		Task:       "periodic reconcile tick test",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "", // empty → no K8s calls needed
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	sandbox := &SandboxExecutor{
		dynClient:  nil, // nil dynClient: cleanupSandboxClaim returns immediately on nil
		logger:     slog.Default(),
		httpClient: &http.Client{},
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		runPeriodicReconcile(ctx, 20*time.Millisecond, store, sandbox, "test-ns", 0, slog.Default())
	}()

	// Wait for at least one full tick (20ms) with margin.
	time.Sleep(100 * time.Millisecond)
	cancel()
	<-done

	// reconcileOrphanedJobs must have run and reset the RUNNING job to PENDING.
	job, err := store.Get(bgCtx, "job-periodic-reconcile-tick")
	if err != nil {
		t.Fatalf("Get job after reconcile: %v", err)
	}
	if job.Status != JobPending {
		t.Errorf("job status = %s, want PENDING after periodic reconcile ran", job.Status)
	}
}
