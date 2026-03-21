package main

import (
	"context"
	"fmt"
	"log/slog"
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// --- appendOutput tests -------------------------------------------------------

// TestAppendOutput_EmptyExisting verifies that when existing is empty the suffix
// is returned as-is without a leading newline.
func TestAppendOutput_EmptyExisting(t *testing.T) {
	got := appendOutput("", "new message")
	if got != "new message" {
		t.Errorf(`appendOutput("", "new message") = %q, want "new message"`, got)
	}
}

// TestAppendOutput_NonEmptyExisting verifies that the suffix is appended with a
// separating newline when existing content is non-empty.
func TestAppendOutput_NonEmptyExisting(t *testing.T) {
	got := appendOutput("previous output", "new message")
	want := "previous output\nnew message"
	if got != want {
		t.Errorf("appendOutput = %q, want %q", got, want)
	}
}

// TestAppendOutput_MultiLine verifies that multi-line existing content is
// extended correctly with a newline separator.
func TestAppendOutput_MultiLine(t *testing.T) {
	existing := "line 1\nline 2"
	got := appendOutput(existing, "appended line")
	want := "line 1\nline 2\nappended line"
	if got != want {
		t.Errorf("appendOutput multi-line = %q, want %q", got, want)
	}
}

// TestAppendOutput_EmptySuffix verifies that appending an empty suffix to a
// non-empty existing string produces a trailing newline (consistent with the
// fmt.Sprintf implementation in reconcile.go).
func TestAppendOutput_EmptySuffix(t *testing.T) {
	got := appendOutput("existing", "")
	// appendOutput is defined as fmt.Sprintf("%s\n%s", existing, suffix)
	want := fmt.Sprintf("%s\n%s", "existing", "")
	if got != want {
		t.Errorf("appendOutput empty suffix = %q, want %q", got, want)
	}
}

// --- cleanupSandboxClaim tests -----------------------------------------------

// TestCleanupSandboxClaim_NilDynClient verifies that a nil dynClient causes
// cleanupSandboxClaim to return immediately without panicking.
func TestCleanupSandboxClaim_NilDynClient(t *testing.T) {
	// Must not panic.
	cleanupSandboxClaim(context.Background(), nil, "goose-sandboxes", "claim-name", slog.Default())
}

// TestCleanupSandboxClaim_ClaimNotFound verifies that a "not found" API error is
// silently swallowed without logging a warning.
func TestCleanupSandboxClaim_ClaimNotFound(t *testing.T) {
	ns := "test-ns"
	dynClient := newDynClient() // empty fake client — claim does not exist

	// Must not panic or surface an error.
	cleanupSandboxClaim(context.Background(), dynClient, ns, "nonexistent-claim", slog.Default())
}

// TestCleanupSandboxClaim_DeletesExistingClaim verifies that an existing claim
// is removed when cleanupSandboxClaim is called.
func TestCleanupSandboxClaim_DeletesExistingClaim(t *testing.T) {
	ns := "test-ns"
	claimName := "cleanup-test-claim"

	dynClient := newDynClient()
	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, template: "tmpl", logger: slog.Default()}
	if err := s.createClaim(context.Background(), claimName); err != nil {
		t.Fatalf("createClaim: %v", err)
	}

	cleanupSandboxClaim(context.Background(), dynClient, ns, claimName, slog.Default())

	// Verify the claim is gone — the dynamic client should return an error on Get.
	_, err := dynClient.Resource(sandboxClaimGVR).Namespace(ns).Get(
		context.Background(), claimName, metav1.GetOptions{})
	if err == nil {
		t.Fatal("expected error getting deleted claim, got nil")
	}
}

// --- reconcileOrphanedJobs additional coverage --------------------------------

// TestReconcileOrphanedJobs_IdleRunnerResetsJob verifies that a runner
// reporting "idle" (task not running) causes the job to fall through to the
// reset path and be set to PENDING.
func TestReconcileOrphanedJobs_IdleRunnerResetsJob(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-idle-runner",
		Task:       "task with idle runner",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-idle-runner-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "idle", 0, nil // "idle" falls through to the reset path
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, 0, slog.Default())

	job, err := store.Get(ctx, "job-idle-runner")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING for idle runner", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.ExitCode == nil || *last.ExitCode != -1 {
		t.Errorf("exit code = %v, want -1 for idle runner fallthrough", last.ExitCode)
	}
}

// TestReconcileOrphanedJobs_FailedRunnerExhaustsRetries verifies that a runner
// reporting "failed" with no retries remaining marks the job as FAILED.
func TestReconcileOrphanedJobs_FailedRunnerExhaustsRetries(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	// MaxRetries=1, 1 attempt already recorded → retriesRemaining=0 → FAILED.
	store.Put(ctx, &JobRecord{
		ID:         "job-failed-exhausted",
		Task:       "exhausted task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 1,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-failed-exhausted-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	checkRunner := func(_ context.Context, _ string) (string, int, error) {
		return "failed", 2, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, 0, slog.Default())

	job, err := store.Get(ctx, "job-failed-exhausted")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobFailed {
		t.Errorf("status = %s, want FAILED when retries exhausted", job.Status)
	}
}

// TestReconcileOrphanedJobs_MultipleJobsMixed verifies that reconciliation
// processes only RUNNING jobs, leaving PENDING and SUCCEEDED records untouched.
func TestReconcileOrphanedJobs_MultipleJobsMixed(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-mixed-orphan",
		Task:       "orphan",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-2 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-mixed-orphan-1",
			StartedAt:        time.Now().Add(-2 * time.Hour),
		}},
	})
	store.Put(ctx, &JobRecord{
		ID:     "job-mixed-succeeded",
		Task:   "done",
		Status: JobSucceeded,
	})
	store.Put(ctx, &JobRecord{
		ID:     "job-mixed-pending",
		Task:   "waiting",
		Status: JobPending,
	})

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, 0, slog.Default())

	orphan, _ := store.Get(ctx, "job-mixed-orphan")
	if orphan.Status != JobPending {
		t.Errorf("orphan: status = %s, want PENDING", orphan.Status)
	}

	succeeded, _ := store.Get(ctx, "job-mixed-succeeded")
	if succeeded.Status != JobSucceeded {
		t.Errorf("succeeded job status changed: got %s", succeeded.Status)
	}

	pending, _ := store.Get(ctx, "job-mixed-pending")
	if pending.Status != JobPending {
		t.Errorf("pending job status changed: got %s", pending.Status)
	}
}

// TestReconcileOrphanedJobs_JobWithNoClaimName verifies that a RUNNING job
// whose last attempt has no SandboxClaimName is safely reset to PENDING without
// panicking.
func TestReconcileOrphanedJobs_JobWithNoClaimName(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-no-claim",
		Task:       "job without claim",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "", // empty — no sandbox was created
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Must not panic.
	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, 0, slog.Default())

	job, err := store.Get(ctx, "job-no-claim")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING", job.Status)
	}
}

// TestReconcileOrphanedJobs_JobWithNoAttempts verifies that a RUNNING job with
// zero recorded attempts is safely handled without panicking.
func TestReconcileOrphanedJobs_JobWithNoAttempts(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	store.Put(ctx, &JobRecord{
		ID:         "job-no-attempts",
		Task:       "job with no attempts",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts:   []Attempt{}, // no attempts recorded — unusual but must not panic
	})

	// Must not panic.
	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, 0, slog.Default())

	job, err := store.Get(ctx, "job-no-attempts")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	// retriesRemaining = MaxRetries(2) - len(Attempts)(0) = 2 > 0 → PENDING.
	if job.Status != JobPending {
		t.Errorf("status = %s, want PENDING", job.Status)
	}
}
