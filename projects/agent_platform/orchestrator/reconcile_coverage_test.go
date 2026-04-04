package main

// reconcile_coverage_test.go adds focused coverage for reconcileOrphanedJobs
// paths not exercised by reconcile_test.go or reconcile_helpers_test.go:
//
//   - fetchOutput error in the "done" runner state (job still marked SUCCEEDED
//     with empty output rather than aborting).
//   - fetchOutput error in the "failed" runner state (attempt still annotated
//     with exit code before falling through to retry logic).
//   - Output truncation (> maxOutputBytes) in both "done" and "failed" paths
//     where fetchOutput returns a large body.
//   - store.Put failure in the "running" re-attach path (lines 107-109 of
//     reconcile.go) — must not panic or crash the reconcile loop.
//   - store.Put failure in the "done" completion path — must not panic.
//   - store.Put failure in the "failed" exhausted-retries path — must not panic.
//   - checkRunner returning an unknown state falls through to reset.

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"testing"
	"time"
)

// ---- fetchOutput error paths -------------------------------------------------

// TestReconcileOrphanedJobs_DoneRunnerFetchOutputError verifies that when the
// runner reports "done" but fetchOutput returns an error, the job is still
// marked SUCCEEDED (the output fetch failure is non-fatal) and the attempt
// output remains empty.
func TestReconcileOrphanedJobs_DoneRunnerFetchOutputError(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-done-fetch-err",
		Task:       "task where output fetch fails",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-done-fetch-err-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "done", 0, nil
	}
	fetchOutput := func(_ context.Context, _ string) (string, error) {
		return "", fmt.Errorf("runner unreachable: connection refused")
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, 0, slog.Default())

	job, err := store.Get(ctx, "job-done-fetch-err")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Job must still be marked SUCCEEDED even though the output fetch failed.
	if job.Status != JobSucceeded {
		t.Errorf("status = %s, want SUCCEEDED (output fetch error is non-fatal)", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.FinishedAt == nil {
		t.Error("FinishedAt should be set even when output fetch fails")
	}
	if last.ExitCode == nil || *last.ExitCode != 0 {
		t.Errorf("exit code = %v, want 0", last.ExitCode)
	}
	// Output must be empty because the fetch failed.
	if last.Output != "" {
		t.Errorf("output = %q, want empty (fetch failed)", last.Output)
	}
}

// TestReconcileOrphanedJobs_FailedRunnerFetchOutputError verifies that when
// the runner reports "failed" but fetchOutput returns an error, the attempt
// still gets the exit code stamped and falls through to retry logic (PENDING).
func TestReconcileOrphanedJobs_FailedRunnerFetchOutputError(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-failed-fetch-err",
		Task:       "task where output fetch fails on failure",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 3,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-failed-fetch-err-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "failed", 2, nil
	}
	fetchOutput := func(_ context.Context, _ string) (string, error) {
		return "", fmt.Errorf("container already removed")
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, 0, slog.Default())

	job, err := store.Get(ctx, "job-failed-fetch-err")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Has retries remaining → should be reset to PENDING for retry.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING (has retries remaining)", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.FinishedAt == nil {
		t.Error("FinishedAt should be set even when output fetch fails")
	}
	if last.ExitCode == nil || *last.ExitCode != 2 {
		t.Errorf("exit code = %v, want 2 (from runner)", last.ExitCode)
	}
	// Output must be empty because the fetch failed.
	if last.Output != "" {
		t.Errorf("output = %q, want empty (fetch failed)", last.Output)
	}
}

// ---- fetchOutput output truncation ------------------------------------------

// TestReconcileOrphanedJobs_DoneRunnerOutputTruncated verifies that when the
// runner reports "done" and fetchOutput returns output exceeding maxOutputBytes,
// the attempt output is truncated to the tail and Truncated is set to true.
func TestReconcileOrphanedJobs_DoneRunnerOutputTruncated(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-done-truncated",
		Task:       "task with very large output",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-done-truncated-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Generate output larger than maxOutputBytes.
	largeOutput := strings.Repeat("x", maxOutputBytes+500)
	tailMarker := "TAIL_MARKER"
	fullOutput := largeOutput + tailMarker

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "done", 0, nil
	}
	fetchOutput := func(_ context.Context, _ string) (string, error) {
		return fullOutput, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, 0, slog.Default())

	job, err := store.Get(ctx, "job-done-truncated")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobSucceeded {
		t.Errorf("status = %s, want SUCCEEDED", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]

	// Output must be truncated (only the tail is kept).
	if len(last.Output) > maxOutputBytes {
		t.Errorf("output length %d exceeds maxOutputBytes %d", len(last.Output), maxOutputBytes)
	}
	// The tail of the original output must be present after truncation.
	if !strings.Contains(last.Output, tailMarker) {
		t.Errorf("output tail %q not found after truncation", tailMarker)
	}
	// Truncated flag must be set.
	if !last.Truncated {
		t.Error("Truncated = false, want true for oversized output")
	}
}

// TestReconcileOrphanedJobs_FailedRunnerOutputTruncated verifies the same
// output-truncation behaviour for the "failed" runner state path.
func TestReconcileOrphanedJobs_FailedRunnerOutputTruncated(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-failed-truncated",
		Task:       "failing task with large output",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 3,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-failed-truncated-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	largeOutput := strings.Repeat("y", maxOutputBytes+500)
	tailMarker := "FAIL_TAIL"
	fullOutput := largeOutput + tailMarker

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "failed", 1, nil
	}
	fetchOutput := func(_ context.Context, _ string) (string, error) {
		return fullOutput, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, 0, slog.Default())

	job, err := store.Get(ctx, "job-failed-truncated")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Has retries remaining → PENDING.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]

	if len(last.Output) > maxOutputBytes {
		t.Errorf("output length %d exceeds maxOutputBytes %d", len(last.Output), maxOutputBytes)
	}
	if !strings.Contains(last.Output, tailMarker) {
		t.Errorf("output tail %q not found after truncation", tailMarker)
	}
	if !last.Truncated {
		t.Error("Truncated = false, want true for oversized output")
	}
}

// ---- store.Put failure paths ------------------------------------------------

// TestReconcileOrphanedJobs_RunningStatePutFailure verifies that a store.Put
// failure in the "running" re-attach path (job left as RUNNING) is handled
// gracefully without panicking or aborting the reconcile loop for other jobs.
func TestReconcileOrphanedJobs_RunningStatePutFailure(t *testing.T) {
	inner := newMemStore()
	ctx := context.Background()

	// Job 1: runner is "running" — Put called to re-stamp UpdatedAt.
	_ = inner.Put(ctx, &JobRecord{
		ID:         "job-running-put-fail",
		Task:       "still running task",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-running-put-fail-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})
	// Job 2: runner is "idle" — will fall through to reset path.
	_ = inner.Put(ctx, &JobRecord{
		ID:         "job-idle-after-running-fail",
		Task:       "should still be processed",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-idle-after-running-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	failStore := &failPutStore{inner: inner}

	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		if claimName == "orch-running-put-fail-1" {
			return "running", 0, nil
		}
		return "idle", 0, nil // second job falls through
	}

	// Must not panic — Put failures are logged and the loop continues.
	reconcileOrphanedJobs(ctx, failStore, nil, "goose-sandboxes", checkRunner, nil, 0, slog.Default())
}

// TestReconcileOrphanedJobs_DoneStatePutFailure verifies that a store.Put
// failure when marking a "done" job as SUCCEEDED does not panic and the loop
// continues to process remaining jobs.
func TestReconcileOrphanedJobs_DoneStatePutFailure(t *testing.T) {
	inner := newMemStore()
	ctx := context.Background()

	_ = inner.Put(ctx, &JobRecord{
		ID:         "job-done-put-fail",
		Task:       "finished task",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-done-put-fail-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	failStore := &failPutStore{inner: inner}

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "done", 0, nil
	}

	// Must not panic.
	reconcileOrphanedJobs(ctx, failStore, nil, "goose-sandboxes", checkRunner, nil, 0, slog.Default())
}

// TestReconcileOrphanedJobs_FailedExhaustedPutFailure verifies that a
// store.Put failure when marking a failed job (no retries remaining) as FAILED
// is handled without panic.
func TestReconcileOrphanedJobs_FailedExhaustedPutFailure(t *testing.T) {
	inner := newMemStore()
	ctx := context.Background()

	// MaxRetries=1 with 1 attempt → retriesRemaining=0 → FAILED path.
	_ = inner.Put(ctx, &JobRecord{
		ID:         "job-failed-exhausted-put-fail",
		Task:       "exhausted task",
		Status:     JobRunning,
		MaxRetries: 1,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-failed-exhausted-put-fail-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	failStore := &failPutStore{inner: inner}

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "failed", 1, nil
	}

	// Must not panic.
	reconcileOrphanedJobs(ctx, failStore, nil, "goose-sandboxes", checkRunner, nil, 0, slog.Default())
}

// ---- unknown runner state ----------------------------------------------------

// TestReconcileOrphanedJobs_UnknownRunnerStateResetsJob verifies that a runner
// reporting an unrecognised state (not "running", "done", or "failed") falls
// through to the reset path and the job is set to PENDING.
func TestReconcileOrphanedJobs_UnknownRunnerStateResetsJob(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-unknown-state",
		Task:       "task with unknown runner state",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-unknown-state-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "starting", 0, nil // unknown / unexpected state
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, 0, slog.Default())

	job, err := store.Get(ctx, "job-unknown-state")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Unknown state should fall through to the reset path → PENDING.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING for unknown runner state", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.ExitCode == nil || *last.ExitCode != -1 {
		t.Errorf("exit code = %v, want -1 for reset attempt", last.ExitCode)
	}
}

// TestReconcileOrphanedJobs_FetchOutputEmptyStringIsIgnored verifies that when
// fetchOutput returns an empty string (success but no data), the existing
// attempt output is not overwritten, matching the `if output != ""` guard.
func TestReconcileOrphanedJobs_FetchOutputEmptyStringIsIgnored(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	existingOutput := "partial output already flushed"
	store.Put(ctx, &JobRecord{
		ID:         "job-empty-fetch-output",
		Task:       "task with no new output from runner",
		Status:     JobRunning,
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-empty-fetch-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
			Output:           existingOutput,
		}},
	})

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "done", 0, nil
	}
	fetchOutput := func(_ context.Context, _ string) (string, error) {
		return "", nil // empty output — nothing new to fetch
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, 0, slog.Default())

	job, err := store.Get(ctx, "job-empty-fetch-output")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobSucceeded {
		t.Errorf("status = %s, want SUCCEEDED", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	// The existing output must not be overwritten by the empty fetch result.
	if last.Output != existingOutput {
		t.Errorf("output = %q, want existing %q (empty fetch should not overwrite)", last.Output, existingOutput)
	}
}

// ---- table-driven appendOutput tests (extended) ------------------------------

// TestAppendOutput_TableDriven verifies appendOutput across a range of inputs
// in a single table-driven test. Complements the individual tests in
// reconcile_helpers_test.go.
func TestAppendOutput_TableDriven(t *testing.T) {
	tests := []struct {
		name     string
		existing string
		suffix   string
		want     string
	}{
		{
			name:     "both empty",
			existing: "",
			suffix:   "",
			want:     "",
		},
		{
			name:     "existing empty suffix non-empty",
			existing: "",
			suffix:   "new line",
			want:     "new line",
		},
		{
			name:     "existing non-empty suffix empty",
			existing: "first",
			suffix:   "",
			want:     "first\n",
		},
		{
			name:     "both non-empty",
			existing: "line one",
			suffix:   "line two",
			want:     "line one\nline two",
		},
		{
			name:     "existing already ends in newline",
			existing: "text\n",
			suffix:   "appended",
			want:     "text\n\nappended",
		},
		{
			name:     "multi-line existing",
			existing: "a\nb\nc",
			suffix:   "d",
			want:     "a\nb\nc\nd",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := appendOutput(tc.existing, tc.suffix)
			if got != tc.want {
				t.Errorf("appendOutput(%q, %q) = %q, want %q",
					tc.existing, tc.suffix, got, tc.want)
			}
		})
	}
}

// ---- syncBuffer table-driven tests (extended) --------------------------------

// TestSyncBuffer_TableDriven provides table-driven coverage for syncBuffer's
// truncation behaviour, complementing the targeted tests in watchdog_test.go.
func TestSyncBuffer_TableDriven(t *testing.T) {
	tests := []struct {
		name       string
		maxRetain  int
		writes     []string // writes applied in sequence
		wantMinLen int      // minimum expected length (≥)
		wantMaxLen int      // maximum expected length (≤)
		wantTail   string   // substring that must appear at the end of String()
	}{
		{
			name:       "single write within cap",
			maxRetain:  20,
			writes:     []string{"hello"},
			wantMinLen: 5,
			wantMaxLen: 5,
			wantTail:   "hello",
		},
		{
			name:       "multiple small writes, cumulative under 2*cap",
			maxRetain:  10,
			writes:     []string{"aaaa", "bbbb", "cccc"}, // 12 bytes — under 2*10=20
			wantMinLen: 12,
			wantMaxLen: 12,
			wantTail:   "cccc",
		},
		{
			name:       "cumulative writes exceed 2*cap triggers truncation",
			maxRetain:  5,
			writes:     []string{"aaaaa", "bbbbb", "CCCCC"}, // 15 bytes > 2*5=10 → truncate to 5
			wantMinLen: 5,
			wantMaxLen: 5,
			wantTail:   "CCCCC",
		},
		{
			name:       "cap zero disables truncation for large writes",
			maxRetain:  0,
			writes:     []string{strings.Repeat("x", 100000)},
			wantMinLen: 100000,
			wantMaxLen: 100000,
		},
		{
			name:       "write that exactly fills 2*cap does not truncate",
			maxRetain:  5,
			writes:     []string{strings.Repeat("z", 10)}, // exactly 2*5 — no truncation
			wantMinLen: 10,
			wantMaxLen: 10,
		},
		{
			name:       "write one byte over 2*cap triggers truncation to cap",
			maxRetain:  5,
			writes:     []string{strings.Repeat("z", 11)}, // 11 > 2*5=10 → keep last 5
			wantMinLen: 5,
			wantMaxLen: 5,
			wantTail:   "zzzzz",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			buf := newSyncBuffer(tc.maxRetain)
			for _, w := range tc.writes {
				n, err := buf.Write([]byte(w))
				if err != nil {
					t.Fatalf("Write(%q) error: %v", w, err)
				}
				if n != len(w) {
					t.Errorf("Write(%q) returned n=%d, want %d", w, n, len(w))
				}
			}

			l := buf.Len()
			s := buf.String()

			if l != len(s) {
				t.Errorf("Len() = %d but len(String()) = %d — inconsistent", l, len(s))
			}
			if l < tc.wantMinLen {
				t.Errorf("Len() = %d < wantMinLen %d", l, tc.wantMinLen)
			}
			if l > tc.wantMaxLen {
				t.Errorf("Len() = %d > wantMaxLen %d", l, tc.wantMaxLen)
			}
			if tc.wantTail != "" && !strings.HasSuffix(s, tc.wantTail) {
				t.Errorf("String() = %q, want suffix %q", s, tc.wantTail)
			}
		})
	}
}
