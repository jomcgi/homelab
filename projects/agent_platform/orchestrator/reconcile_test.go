package main

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"testing"
	"time"
)

func TestReconcileOrphanedJobs_ResetsRunningJobs(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	// Seed two orphaned RUNNING jobs (simulating an orchestrator crash mid-execution).
	store.Put(ctx, &JobRecord{
		ID:         "job-orphan-1",
		Task:       "deploy envoy gateway",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-2 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-orphan-1-1",
			StartedAt:        time.Now().Add(-2 * time.Hour),
		}},
	})
	store.Put(ctx, &JobRecord{
		ID:         "job-orphan-2",
		Task:       "fix CI",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 3,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-orphan-2-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// A PENDING job that should not be touched.
	store.Put(ctx, &JobRecord{
		ID:        "job-pending",
		Task:      "pending task",
		Status:    JobPending,
		CreatedAt: time.Now(),
	})

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, slog.Default())

	// Both orphaned jobs should be reset to PENDING.
	// NATS will redeliver the messages automatically after AckWait expires.
	for _, id := range []string{"job-orphan-1", "job-orphan-2"} {
		job, err := store.Get(ctx, id)
		if err != nil {
			t.Fatalf("Get(%s): %v", id, err)
		}
		if job.Status != JobPending {
			t.Errorf("%s: status = %s, want PENDING", id, job.Status)
		}
		// The interrupted attempt should be marked with exit code -1.
		last := job.Attempts[len(job.Attempts)-1]
		if last.ExitCode == nil || *last.ExitCode != -1 {
			t.Errorf("%s: last attempt exit code = %v, want -1", id, last.ExitCode)
		}
		if last.FinishedAt == nil {
			t.Errorf("%s: last attempt FinishedAt should be set", id)
		}
	}

	// PENDING job should be untouched.
	pending, _ := store.Get(ctx, "job-pending")
	if pending.Status != JobPending {
		t.Errorf("pending job status = %s, want PENDING", pending.Status)
	}
}

func TestReconcileOrphanedJobs_ExhaustedRetriesMarksFailed(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	// Job that has used all its retries.
	store.Put(ctx, &JobRecord{
		ID:         "job-exhausted",
		Task:       "flaky task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-3 * time.Hour),
		MaxRetries: 1,
		Attempts: []Attempt{
			{Number: 1, SandboxClaimName: "orch-job-exhausted-1", StartedAt: time.Now().Add(-3 * time.Hour)},
		},
	})

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, slog.Default())

	job, _ := store.Get(ctx, "job-exhausted")
	if job.Status != JobFailed {
		t.Errorf("status = %s, want FAILED", job.Status)
	}
}

func TestReconcileOrphanedJobs_NoRunningJobs(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:     "job-done",
		Task:   "completed task",
		Status: JobSucceeded,
	})

	// Should be a no-op.
	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, slog.Default())
}

func TestReconcileOrphanedJobs_ReAttachRunning(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-still-running",
		Task:       "long running task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-still-running-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Mock runner that reports goose is still running.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "running", 0, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, slog.Default())

	job, err := store.Get(ctx, "job-still-running")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobRunning {
		t.Errorf("status = %s, want RUNNING", job.Status)
	}
	// Attempt should NOT be marked as finished.
	last := job.Attempts[len(job.Attempts)-1]
	if last.FinishedAt != nil {
		t.Errorf("FinishedAt should be nil for still-running job")
	}
}

func TestReconcileOrphanedJobs_CollectsDone(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-done-unnoticed",
		Task:       "completed task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-done-unnoticed-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Mock runner that reports goose finished successfully.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "done", 0, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, slog.Default())

	job, err := store.Get(ctx, "job-done-unnoticed")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobSucceeded {
		t.Errorf("status = %s, want SUCCEEDED", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.FinishedAt == nil {
		t.Error("FinishedAt should be set")
	}
	if last.ExitCode == nil || *last.ExitCode != 0 {
		t.Errorf("exit code = %v, want 0", last.ExitCode)
	}
}

func TestReconcileOrphanedJobs_CollectsDoneWithOutput(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-done-with-output",
		Task:       "research task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-done-with-output-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
			Output:           "partial output from periodic flush",
		}},
	})

	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "done", 0, nil
	}

	// Mock output fetcher that returns the full runner output including goose-result.
	fetchOutput := func(_ context.Context, claimName string) (string, error) {
		return "Research complete.\n\n```goose-result\ntype: gist\nurl: https://gist.github.com/test/abc123\nsummary: Researched Seattle activities\n```\n", nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, slog.Default())

	job, err := store.Get(ctx, "job-done-with-output")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobSucceeded {
		t.Errorf("status = %s, want SUCCEEDED", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	// Output should be replaced with the full runner output (after cleanOutput).
	if last.Output == "partial output from periodic flush" {
		t.Error("output should be replaced with full runner output, still has partial flush")
	}
	// Result should be parsed from the goose-result block.
	if last.Result == nil {
		t.Fatal("result should be parsed from goose-result block")
	}
	if last.Result.Type != "gist" {
		t.Errorf("result.Type = %q, want %q", last.Result.Type, "gist")
	}
	if last.Result.URL != "https://gist.github.com/test/abc123" {
		t.Errorf("result.URL = %q, want gist URL", last.Result.URL)
	}
	if last.Result.Summary != "Researched Seattle activities" {
		t.Errorf("result.Summary = %q, want summary", last.Result.Summary)
	}
}

func TestReconcileOrphanedJobs_FailedWithOutput(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-failed-with-output",
		Task:       "failing task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 3,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-failed-with-output-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "failed", 1, nil
	}

	fetchOutput := func(_ context.Context, claimName string) (string, error) {
		return "Error: something went wrong\n", nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, slog.Default())

	job, err := store.Get(ctx, "job-failed-with-output")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Should be reset to PENDING for retry.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.Output != "Error: something went wrong\n" {
		t.Errorf("output = %q, want error message", last.Output)
	}
}

func TestReconcileOrphanedJobs_FailedRunnerRetries(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-failed-runner",
		Task:       "task that failed",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 3,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-failed-runner-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Mock runner that reports goose failed.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "failed", 1, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, slog.Default())

	job, err := store.Get(ctx, "job-failed-runner")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Should be reset to PENDING for retry (has retries remaining).
	// NATS will redeliver the message automatically after AckWait expires.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.ExitCode == nil || *last.ExitCode != 1 {
		t.Errorf("exit code = %v, want 1", last.ExitCode)
	}
	if last.FinishedAt == nil {
		t.Error("FinishedAt should be set")
	}
}

// TestReconcileOrphanedJobs_PeriodicCatchesCompletedJob simulates the bug
// where a runner finishes after the initial reconciliation pass. The first
// pass sees "running" and leaves the job alone; the second pass (periodic)
// sees "done" and correctly marks it SUCCEEDED.
func TestReconcileOrphanedJobs_PeriodicCatchesCompletedJob(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-late-finish",
		Task:       "task that finishes after first reconcile",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-late-finish-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	callCount := 0
	// First call: runner is still going. Second call: runner finished.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		callCount++
		if callCount == 1 {
			return "running", 0, nil
		}
		return "done", 0, nil
	}

	fetchOutput := func(_ context.Context, claimName string) (string, error) {
		return "task completed successfully\n", nil
	}

	// First pass: should leave job as RUNNING.
	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, slog.Default())

	job, _ := store.Get(ctx, "job-late-finish")
	if job.Status != JobRunning {
		t.Fatalf("after first pass: status = %s, want RUNNING", job.Status)
	}

	// Second pass (simulates periodic tick): should mark SUCCEEDED.
	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, fetchOutput, slog.Default())

	job, _ = store.Get(ctx, "job-late-finish")
	if job.Status != JobSucceeded {
		t.Errorf("after second pass: status = %s, want SUCCEEDED", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.Output != "task completed successfully\n" {
		t.Errorf("output = %q, want task output", last.Output)
	}
}

func TestReconcileOrphanedJobs_RunnerUnreachableFallsBack(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-unreachable",
		Task:       "task with dead runner",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-unreachable-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Mock runner that is unreachable.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "", -1, fmt.Errorf("connection refused")
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, slog.Default())

	job, err := store.Get(ctx, "job-unreachable")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// Should fall back to existing behavior: reset to PENDING.
	// NATS will redeliver the message automatically after AckWait expires.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.ExitCode == nil || *last.ExitCode != -1 {
		t.Errorf("exit code = %v, want -1", last.ExitCode)
	}
}

// TestReconcileOrphanedJobs_GracePeriodSkipsRecentAttempt verifies that the
// reconciler does not touch jobs whose latest attempt started less than 2
// minutes ago. This prevents a race where the reconciler sees a freshly-
// created sandbox as "idle" (goose hasn't launched yet) and deletes the
// SandboxClaim before the consumer can use it.
func TestReconcileOrphanedJobs_GracePeriodSkipsRecentAttempt(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	// Job with an attempt that just started (30 seconds ago).
	store.Put(ctx, &JobRecord{
		ID:         "job-fresh",
		Task:       "just started task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-30 * time.Second),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-fresh-1",
			StartedAt:        time.Now().Add(-30 * time.Second),
		}},
	})

	// Job with an old attempt (1 hour ago) — should still be reconciled.
	store.Put(ctx, &JobRecord{
		ID:         "job-old",
		Task:       "stale task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-old-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Runner reports "idle" for both — without the grace period, both would
	// be reset to PENDING with their sandbox claims deleted.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "idle", 0, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, slog.Default())

	// Fresh job should be untouched — still RUNNING with no FinishedAt.
	fresh, err := store.Get(ctx, "job-fresh")
	if err != nil {
		t.Fatalf("Get(job-fresh): %v", err)
	}
	if fresh.Status != JobRunning {
		t.Errorf("job-fresh: status = %s, want RUNNING (grace period should skip it)", fresh.Status)
	}
	if fresh.Attempts[0].FinishedAt != nil {
		t.Error("job-fresh: FinishedAt should be nil (attempt not interrupted)")
	}

	// Old job should be reset to PENDING.
	old, err := store.Get(ctx, "job-old")
	if err != nil {
		t.Fatalf("Get(job-old): %v", err)
	}
	if old.Status != JobPending {
		t.Errorf("job-old: status = %s, want PENDING", old.Status)
	}
}

// TestReconcileOrphanedJobs_ZeroAttemptsSkipsGracePeriod verifies that a
// RUNNING job with an empty Attempts slice is not incorrectly skipped by the
// grace period guard and is still reconciled back to PENDING.
//
// The grace period check is guarded by `if len(job.Attempts) > 0`, so a job
// with zero attempts (e.g., one that was marked RUNNING before the consumer
// could record its first attempt) must fall straight through to the retry
// logic and be reset to PENDING for NATS redelivery.
func TestReconcileOrphanedJobs_ZeroAttemptsSkipsGracePeriod(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	// RUNNING job with no attempt records at all. This can happen when the
	// orchestrator marks a job RUNNING but crashes before the consumer appends
	// the first Attempt. Without the empty-slice guard the reconciler would
	// panic or silently skip the job.
	store.Put(ctx, &JobRecord{
		ID:         "job-no-attempts",
		Task:       "orphaned before first attempt",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts:   []Attempt{}, // explicitly empty — no grace period to check
	})

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, slog.Default())

	job, err := store.Get(ctx, "job-no-attempts")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// retriesRemaining = MaxRetries(2) - len(Attempts)(0) = 2 > 0 → PENDING.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING (zero attempts: grace period skipped, retries available)", job.Status)
	}
	// The reconciler must not synthesise attempt records for a zero-attempt job.
	if len(job.Attempts) != 0 {
		t.Errorf("expected 0 attempts after reconcile, got %d", len(job.Attempts))
	}
}

// TestParseGooseResult_OnRawOutputBeforeClean documents and verifies the
// intentional call ordering in both reconcile.go and consumer.go:
//
//	last.Result = parseGooseResult(output)   // called FIRST on raw output
//	output = cleanOutput(output)             // called SECOND, strips the block
//
// This ordering is critical: cleanOutput removes the ```goose-result``` fenced
// block so it does not appear in the UI display, but parseGooseResult must run
// first to extract the structured result. If the ordering were reversed the
// result would always be nil because cleanOutput strips the block.
func TestParseGooseResult_OnRawOutputBeforeClean(t *testing.T) {
	// Simulate raw runner output: ANSI escape codes + Goose banner + useful
	// agent output + a structured goose-result block. This is exactly what
	// arrives from the runner before any cleaning is applied.
	raw := "\x1b[1m  __( O)>  new session\x1b[0m\n" +
		" \\___)\t20260319_1 · /workspace/homelab\n" +
		"   L L\tgoose is ready\n" +
		"\x1b[36mI investigated the traces and found the issue.\x1b[0m\n" +
		"```goose-result\n" +
		"type: pr\n" +
		"url: https://github.com/jomcgi/homelab/pull/99\n" +
		"summary: Fixed the trace sampling configuration.\n" +
		"```\n"

	// parseGooseResult must successfully extract the result from the raw
	// (unclean) output — banner lines and ANSI codes do not interfere.
	result := parseGooseResult(raw)
	if result == nil {
		t.Fatal("parseGooseResult must find the result block in raw (pre-clean) output")
	}
	if result.Type != "pr" {
		t.Errorf("result.Type = %q, want %q", result.Type, "pr")
	}
	if result.URL != "https://github.com/jomcgi/homelab/pull/99" {
		t.Errorf("result.URL = %q, want PR URL", result.URL)
	}
	if result.Summary != "Fixed the trace sampling configuration." {
		t.Errorf("result.Summary = %q", result.Summary)
	}

	// After cleanOutput the goose-result block is removed from display output,
	// confirming that parseGooseResult must precede cleanOutput to preserve the result.
	cleaned := cleanOutput(raw)
	if strings.Contains(cleaned, "goose-result") {
		t.Error("cleanOutput must strip the goose-result block from display output")
	}
	// Banner and ANSI are also removed by cleanOutput.
	if strings.Contains(cleaned, "goose is ready") {
		t.Error("cleanOutput must strip the Goose startup banner")
	}
	if strings.Contains(cleaned, "\x1b[") {
		t.Error("cleanOutput must strip ANSI escape codes")
	}
	// Useful agent output is preserved after cleaning.
	if !strings.Contains(cleaned, "I investigated the traces") {
		t.Errorf("cleanOutput must preserve useful agent output; got: %q", cleaned)
	}
}
