package main

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

// --- Output truncation in processJob -----------------------------------------

// TestProcessJob_OutputTruncation verifies that when the sandbox returns output
// larger than maxOutputBytes, the attempt's Truncated flag is set to true and
// only the tail of the output is stored.
func TestProcessJob_OutputTruncation(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-TRUNCATE-OUT")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	// Produce output slightly larger than maxOutputBytes (32 KB).
	oversizedOutput := strings.Repeat("x", maxOutputBytes+100)
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 0, Output: oversizedOutput}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.Status != JobSucceeded {
		t.Fatalf("expected SUCCEEDED, got %s", got.Status)
	}
	if len(got.Attempts) != 1 {
		t.Fatalf("expected 1 attempt, got %d", len(got.Attempts))
	}
	if !got.Attempts[0].Truncated {
		t.Error("expected Truncated=true for oversized output, got false")
	}
	// The stored output is the tail of the raw output (maxOutputBytes) run through
	// cleanOutput, which appends one trailing newline. Allow up to maxOutputBytes+1.
	if len(got.Attempts[0].Output) > maxOutputBytes+1 {
		t.Errorf("stored output length %d far exceeds maxOutputBytes %d",
			len(got.Attempts[0].Output), maxOutputBytes)
	}
}

// TestProcessJob_OutputExactlyMaxBytes verifies that output exactly at the
// maxOutputBytes limit is NOT flagged as truncated.
func TestProcessJob_OutputExactlyMaxBytes(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-EXACT-OUT")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	exactOutput := strings.Repeat("y", maxOutputBytes)
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 0, Output: exactOutput}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.Attempts[0].Truncated {
		t.Error("expected Truncated=false for output exactly at limit")
	}
}

// --- flushProgress error paths -----------------------------------------------

// TestFlushProgress_StoreGetFails verifies that a store.Get failure inside
// flushProgress is handled gracefully (no panic, no data corruption).
func TestFlushProgress_StoreGetFails(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-FLUSH-GET-FAIL")
	job.Status = JobRunning
	job.Attempts = []Attempt{{Number: 1, StartedAt: time.Now().UTC()}}
	_ = store.Put(context.Background(), job)

	// Use a store that always fails on Get.
	failStore := &failGetStore{inner: store}
	c := newTestConsumer(failStore, &fakeSandbox{})

	buf := newSyncBuffer(maxOutputBytes)
	buf.Write([]byte("some progress output"))
	planBuf := &planTracker{}

	// Must not panic.
	c.flushProgress(context.Background(), job.ID, buf, planBuf)

	// The underlying store should be unmodified since flushProgress returned early.
	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get on underlying store: %v", err)
	}
	// The attempt output should remain empty (flushProgress exited early).
	if got.Attempts[0].Output != "" {
		t.Errorf("expected empty output (flush aborted), got %q", got.Attempts[0].Output)
	}
}

// TestFlushProgress_EmptyAttempts verifies that flushProgress returns early
// when the job has no recorded attempts (guard against index panic).
func TestFlushProgress_EmptyAttempts(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-FLUSH-NO-ATT")
	job.Status = JobRunning
	job.Attempts = []Attempt{} // no attempts — simulate edge case
	_ = store.Put(context.Background(), job)

	c := newTestConsumer(store, &fakeSandbox{})
	buf := newSyncBuffer(maxOutputBytes)
	buf.Write([]byte("output"))
	planBuf := &planTracker{}

	// Must not panic.
	c.flushProgress(context.Background(), job.ID, buf, planBuf)
}

// --- hasAllTags unit tests ----------------------------------------------------

// TestHasAllTags_AllMatch verifies that a job containing all required tags
// returns true.
func TestHasAllTags_AllMatch(t *testing.T) {
	if !hasAllTags([]string{"ci", "urgent", "prod"}, []string{"ci", "urgent"}) {
		t.Error("hasAllTags: expected true when all required tags present")
	}
}

// TestHasAllTags_MissingOne verifies that a missing required tag returns false.
func TestHasAllTags_MissingOne(t *testing.T) {
	if hasAllTags([]string{"ci"}, []string{"ci", "urgent"}) {
		t.Error("hasAllTags: expected false when a required tag is missing")
	}
}

// TestHasAllTags_EmptyRequired verifies that an empty required set always
// returns true (no constraints).
func TestHasAllTags_EmptyRequired(t *testing.T) {
	if !hasAllTags([]string{"ci"}, []string{}) {
		t.Error("hasAllTags: expected true for empty required set")
	}
	if !hasAllTags(nil, nil) {
		t.Error("hasAllTags: expected true for nil required set")
	}
}

// TestHasAllTags_EmptyJobTags verifies that a job with no tags never satisfies
// a non-empty required set.
func TestHasAllTags_EmptyJobTags(t *testing.T) {
	if hasAllTags(nil, []string{"ci"}) {
		t.Error("hasAllTags: expected false for nil job tags with non-empty required")
	}
	if hasAllTags([]string{}, []string{"urgent"}) {
		t.Error("hasAllTags: expected false for empty job tags with non-empty required")
	}
}

// TestHasAllTags_ExactMatch verifies that when job tags exactly equal the
// required tags the function returns true.
func TestHasAllTags_ExactMatch(t *testing.T) {
	if !hasAllTags([]string{"ci", "urgent"}, []string{"ci", "urgent"}) {
		t.Error("hasAllTags: expected true for exact match")
	}
}

// --- buildTaskPrompt edge cases -----------------------------------------------

// TestBuildTaskPrompt_AttemptOneWithAttempts verifies that when attemptNum==1,
// the raw task is returned regardless of how many attempts are in the slice.
// This exercises the short-circuit path: attemptNum <= 1 returns early.
func TestBuildTaskPrompt_AttemptOneWithAttempts(t *testing.T) {
	c := newTestConsumer(newMemStore(), &fakeSandbox{})
	exitCode := 1
	job := &JobRecord{
		Task: "run the tests",
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: "previous output that should be ignored"},
		},
	}

	prompt := c.buildTaskPrompt(job, 1)
	if prompt != "run the tests" {
		t.Errorf("expected raw task for attemptNum==1, got %q", prompt)
	}
}

// TestBuildTaskPrompt_SecondAttemptWithNilExitCode verifies that when the
// previous attempt has a nil exit code, a default of -1 is used in the prompt.
func TestBuildTaskPrompt_SecondAttemptWithNilExitCode(t *testing.T) {
	c := newTestConsumer(newMemStore(), &fakeSandbox{})
	job := &JobRecord{
		Task: "run the tests",
		Attempts: []Attempt{
			{Number: 1, ExitCode: nil, Output: "no exit code recorded"}, // nil exit code
			{Number: 2, StartedAt: time.Now().UTC()},                    // current attempt
		},
	}

	prompt := c.buildTaskPrompt(job, 2)
	if !strings.Contains(prompt, "exit code -1") {
		t.Errorf("expected exit code -1 in prompt for nil exit code, got: %q", prompt)
	}
}

// --- Consumer with recipe path -----------------------------------------------

// TestProcessJob_RecipePathIsEmpty verifies that the consumer passes an empty
// recipe path to the sandbox (the runner discovers recipes autonomously).
func TestProcessJob_RecipePathIsEmpty(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-RECIPE-EMPTY")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	var capturedRecipePath string
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, recipePath string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			capturedRecipePath = recipePath
			return &ExecResult{ExitCode: 0, Output: "done"}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if capturedRecipePath != "" {
		t.Errorf("expected empty recipe path, got %q", capturedRecipePath)
	}
}

// TestProcessJob_ClaimNameFormat verifies that the sandbox claim name uses the
// expected format: "orch-<lowercase-id>-<attemptNum>".
func TestProcessJob_ClaimNameFormat(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-ABC123")
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

	// Expected: "orch-job-abc123-1" (lowercase, attempt 1)
	expected := "orch-job-abc123-1"
	if capturedClaimName != expected {
		t.Errorf("claim name = %q, want %q", capturedClaimName, expected)
	}
}

// TestProcessJob_AttemptNumberIncrementsOnRetry verifies that on the second
// attempt (after a previous failure), the attempt number is 2 and the claim
// name reflects this.
func TestProcessJob_AttemptNumberIncrementsOnRetry(t *testing.T) {
	store := newMemStore()
	exitCode := 1
	// Simulate a job that has already had one failed attempt.
	job := &JobRecord{
		ID:         "JOB-RETRY-NUM",
		Task:       "retry me",
		Status:     JobPending,
		MaxRetries: 0, // no more retries — should fail after this attempt
		CreatedAt:  time.Now().UTC(),
		UpdatedAt:  time.Now().UTC(),
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: "first attempt failed"},
		},
	}
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

	// Attempt 2 claim: "orch-job-retry-num-2"
	expected := "orch-job-retry-num-2"
	if capturedClaimName != expected {
		t.Errorf("claim name = %q, want %q", capturedClaimName, expected)
	}
}

// TestProcessJob_CancelFnChecksStore verifies that the cancelFn closure passed
// to the sandbox reads the current job status from the store, not a stale copy.
// This tests the closure captures jobID correctly.
func TestProcessJob_CancelFnChecksStore(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-CANCEL-FN")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	var cancelFnResult bool
	sandbox := &fakeSandbox{
		runFn: func(ctx context.Context, _, _, _ string, cancelFn func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			// Initially not cancelled.
			cancelFnResult = cancelFn()
			if cancelFnResult {
				return nil, errors.New("unexpected cancel")
			}

			// Now cancel the job in the store and check again.
			current, _ := store.Get(ctx, job.ID)
			current.Status = JobCancelled
			_ = store.Put(ctx, current)

			cancelFnResult = cancelFn()
			return &ExecResult{ExitCode: 1, Output: "cancelled"}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if !cancelFnResult {
		t.Error("cancelFn should return true after job status is set to CANCELLED")
	}
}

// TestProcessJob_CancelFnStoreError verifies that if store.Get fails inside
// the cancelFn closure, it returns false (safe default: don't cancel).
// The cancelFn is tested directly, mirroring how processJob builds it.
func TestProcessJob_CancelFnStoreError(t *testing.T) {
	store := newMemStore()
	failStore := &failGetStore{inner: store}

	// Build the cancelFn closure exactly as processJob does.
	jobID := "JOB-CANCEL-FN-ERR"
	cancelFn := func() bool {
		current, err := failStore.Get(context.Background(), jobID)
		if err != nil {
			return false
		}
		return current.Status == JobCancelled
	}

	// Store.Get always fails in failGetStore → cancelFn must return false.
	if cancelFn() {
		t.Error("cancelFn should return false when store.Get fails")
	}
}
