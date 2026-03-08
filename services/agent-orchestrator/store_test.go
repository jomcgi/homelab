package main

import (
	"context"
	"fmt"
	"log/slog"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// These tests require a running NATS server with JetStream enabled.
// Run with: nats-server -js
// Tagged manual in the BUILD file so they don't run in CI.

func setupTestStore(t *testing.T) *JobStore {
	t.Helper()

	nc, err := nats.Connect(nats.DefaultURL)
	if err != nil {
		t.Fatalf("connecting to NATS: %v", err)
	}
	t.Cleanup(func() { nc.Close() })

	js, err := jetstream.New(nc)
	if err != nil {
		t.Fatalf("creating JetStream context: %v", err)
	}

	ctx := context.Background()
	bucket := "test-job-records-" + time.Now().Format("20060102150405")

	kv, err := js.CreateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket: bucket,
	})
	if err != nil {
		t.Fatalf("creating KV bucket: %v", err)
	}
	t.Cleanup(func() {
		_ = js.DeleteKeyValue(ctx, bucket)
	})

	return NewJobStore(kv, slog.Default())
}

func TestPutGetRoundTrip(t *testing.T) {
	store := setupTestStore(t)
	ctx := context.Background()

	job := &JobRecord{
		ID:         "test-001",
		Task:       "echo hello",
		Status:     JobPending,
		CreatedAt:  time.Now().UTC(),
		MaxRetries: 3,
		Source:     "test",
	}

	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}

	got, err := store.Get(ctx, "test-001")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}

	if got.ID != job.ID {
		t.Errorf("ID = %q, want %q", got.ID, job.ID)
	}
	if got.Task != job.Task {
		t.Errorf("Task = %q, want %q", got.Task, job.Task)
	}
	if got.Status != JobPending {
		t.Errorf("Status = %q, want %q", got.Status, JobPending)
	}
	if got.MaxRetries != 3 {
		t.Errorf("MaxRetries = %d, want 3", got.MaxRetries)
	}
	if got.UpdatedAt.IsZero() {
		t.Error("UpdatedAt should be set by Put")
	}
}

func TestPutGetWithAttempts(t *testing.T) {
	store := setupTestStore(t)
	ctx := context.Background()

	exitCode := 0
	finished := time.Now().UTC()
	job := &JobRecord{
		ID:         "test-002",
		Task:       "run tests",
		Status:     JobSucceeded,
		CreatedAt:  time.Now().UTC(),
		MaxRetries: 1,
		Source:     "ci",
		Attempts: []Attempt{
			{
				Number:           1,
				SandboxClaimName: "sandbox-abc",
				ExitCode:         &exitCode,
				Output:           "all tests passed",
				StartedAt:        time.Now().UTC().Add(-time.Minute),
				FinishedAt:       &finished,
			},
		},
	}

	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}

	got, err := store.Get(ctx, "test-002")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}

	if len(got.Attempts) != 1 {
		t.Fatalf("Attempts len = %d, want 1", len(got.Attempts))
	}
	if got.Attempts[0].SandboxClaimName != "sandbox-abc" {
		t.Errorf("SandboxClaimName = %q, want %q", got.Attempts[0].SandboxClaimName, "sandbox-abc")
	}
	if *got.Attempts[0].ExitCode != 0 {
		t.Errorf("ExitCode = %d, want 0", *got.Attempts[0].ExitCode)
	}
}

func TestListWithStatusFilter(t *testing.T) {
	store := setupTestStore(t)
	ctx := context.Background()

	jobs := []*JobRecord{
		{ID: "job-a", Task: "task a", Status: JobPending, CreatedAt: time.Now().UTC()},
		{ID: "job-b", Task: "task b", Status: JobRunning, CreatedAt: time.Now().UTC()},
		{ID: "job-c", Task: "task c", Status: JobPending, CreatedAt: time.Now().UTC()},
		{ID: "job-d", Task: "task d", Status: JobSucceeded, CreatedAt: time.Now().UTC()},
	}
	for _, j := range jobs {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put(%s): %v", j.ID, err)
		}
	}

	// List all.
	got, total, err := store.List(ctx, nil, nil, 100, 0)
	if err != nil {
		t.Fatalf("List all: %v", err)
	}
	if total != 4 {
		t.Errorf("total = %d, want 4", total)
	}
	if len(got) != 4 {
		t.Errorf("len = %d, want 4", len(got))
	}

	// Filter by PENDING.
	got, total, err = store.List(ctx, []string{"PENDING"}, nil, 100, 0)
	if err != nil {
		t.Fatalf("List PENDING: %v", err)
	}
	if total != 2 {
		t.Errorf("total = %d, want 2", total)
	}
	for _, j := range got {
		if j.Status != JobPending {
			t.Errorf("expected PENDING, got %s for job %s", j.Status, j.ID)
		}
	}

	// Filter by RUNNING.
	got, total, err = store.List(ctx, []string{"RUNNING"}, nil, 100, 0)
	if err != nil {
		t.Fatalf("List RUNNING: %v", err)
	}
	if total != 1 {
		t.Errorf("total = %d, want 1", total)
	}
}

func TestListPagination(t *testing.T) {
	store := setupTestStore(t)
	ctx := context.Background()

	for i := 0; i < 5; i++ {
		job := &JobRecord{
			ID:        fmt.Sprintf("page-%02d", i),
			Task:      fmt.Sprintf("task %d", i),
			Status:    JobPending,
			CreatedAt: time.Now().UTC(),
		}
		if err := store.Put(ctx, job); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	// First page.
	got, total, err := store.List(ctx, nil, nil, 2, 0)
	if err != nil {
		t.Fatalf("List page 1: %v", err)
	}
	if total != 5 {
		t.Errorf("total = %d, want 5", total)
	}
	if len(got) != 2 {
		t.Errorf("page 1 len = %d, want 2", len(got))
	}

	// Second page.
	got, total, err = store.List(ctx, nil, nil, 2, 2)
	if err != nil {
		t.Fatalf("List page 2: %v", err)
	}
	if total != 5 {
		t.Errorf("total = %d, want 5", total)
	}
	if len(got) != 2 {
		t.Errorf("page 2 len = %d, want 2", len(got))
	}

	// Beyond last page.
	got, total, err = store.List(ctx, nil, nil, 2, 10)
	if err != nil {
		t.Fatalf("List beyond: %v", err)
	}
	if total != 5 {
		t.Errorf("total = %d, want 5", total)
	}
	if len(got) != 0 {
		t.Errorf("beyond len = %d, want 0", len(got))
	}
}
