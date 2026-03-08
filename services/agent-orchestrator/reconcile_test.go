package main

import (
	"context"
	"log/slog"
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

	var republished []string
	publish := func(jobID string) error {
		republished = append(republished, jobID)
		return nil
	}

	reconcileOrphanedJobs(ctx, store, publish, nil, "goose-sandboxes", slog.Default())

	// Both orphaned jobs should be reset to PENDING.
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

	// Both should be re-published to NATS.
	if len(republished) != 2 {
		t.Fatalf("republished count = %d, want 2", len(republished))
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

	var republished []string
	publish := func(jobID string) error {
		republished = append(republished, jobID)
		return nil
	}

	reconcileOrphanedJobs(ctx, store, publish, nil, "goose-sandboxes", slog.Default())

	job, _ := store.Get(ctx, "job-exhausted")
	if job.Status != JobFailed {
		t.Errorf("status = %s, want FAILED", job.Status)
	}

	// Should NOT be re-published since retries are exhausted.
	if len(republished) != 0 {
		t.Errorf("republished count = %d, want 0", len(republished))
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

	published := false
	publish := func(string) error {
		published = true
		return nil
	}

	// Should be a no-op.
	reconcileOrphanedJobs(ctx, store, publish, nil, "goose-sandboxes", slog.Default())

	if published {
		t.Error("should not have published anything")
	}
}
