package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync/atomic"
	"testing"
	"time"

	nats "github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// --- Fake jetstream.Msg ---

// fakeMsg satisfies jetstream.Msg. Only the methods used by processJob need
// real implementations; everything else panics so tests catch unexpected calls.
type fakeMsg struct {
	data    []byte
	acked   atomic.Bool
	nacked  atomic.Bool
	headers nats.Header
}

func newFakeMsg(data []byte) *fakeMsg { return &fakeMsg{data: data} }

func (m *fakeMsg) Data() []byte         { return m.data }
func (m *fakeMsg) Headers() nats.Header { return m.headers }
func (m *fakeMsg) Ack() error           { m.acked.Store(true); return nil }
func (m *fakeMsg) Nak() error           { m.nacked.Store(true); return nil }
func (m *fakeMsg) NakWithDelay(_ time.Duration) error {
	m.nacked.Store(true)
	return nil
}
func (m *fakeMsg) Term() error                       { return nil }
func (m *fakeMsg) TermWithReason(_ string) error     { return nil }
func (m *fakeMsg) InProgress() error                 { return nil }
func (m *fakeMsg) DoubleAck(_ context.Context) error { m.acked.Store(true); return nil }
func (m *fakeMsg) Metadata() (*jetstream.MsgMetadata, error) {
	return &jetstream.MsgMetadata{}, nil
}
func (m *fakeMsg) Subject() string { return "jobs" }
func (m *fakeMsg) Reply() string   { return "" }

// --- Fake Sandbox ---

type fakeSandbox struct {
	// runFn is called by Run; defaults to success with exit code 0.
	runFn func(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, buf *syncBuffer, planBuf *planTracker) (*ExecResult, error)
}

func (f *fakeSandbox) Run(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, buf *syncBuffer, planBuf *planTracker) (*ExecResult, error) {
	if f.runFn != nil {
		return f.runFn(ctx, claimName, task, recipePath, cancelFn, buf, planBuf)
	}
	return &ExecResult{ExitCode: 0, Output: "success"}, nil
}

// --- Helpers ---

func newTestConsumer(store Store, sandbox Sandbox) *Consumer {
	return NewConsumer(nil, store, sandbox, nil, 5*time.Minute, slog.Default())
}

func pendingJob(id string) *JobRecord {
	now := time.Now().UTC()
	return &JobRecord{
		ID:         id,
		Task:       "run tests",
		Status:     JobPending,
		MaxRetries: 0,
		CreatedAt:  now,
		UpdatedAt:  now,
		Attempts:   []Attempt{},
	}
}

// --- Tests ---

func TestProcessJob_HappyPath(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-HAPPY")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{} // default: exit 0, "success"

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	// Message should be ACKed on success.
	if !msg.acked.Load() {
		t.Fatal("expected msg to be ACKed on success")
	}
	if msg.nacked.Load() {
		t.Fatal("expected msg NOT to be NACKed on success")
	}

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.Status != JobSucceeded {
		t.Errorf("expected SUCCEEDED, got %s", got.Status)
	}
	if len(got.Attempts) != 1 {
		t.Fatalf("expected 1 attempt, got %d", len(got.Attempts))
	}
	if got.Attempts[0].Output != "success" {
		t.Errorf("unexpected output: %q", got.Attempts[0].Output)
	}
}

func TestProcessJob_SandboxFailure_ExitCode(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-FAIL")
	job.MaxRetries = 0
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 1, Output: "tests failed"}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if !msg.acked.Load() {
		t.Fatal("expected ACK after retries exhausted")
	}

	got, _ := store.Get(context.Background(), job.ID)
	if got.Status != JobFailed {
		t.Errorf("expected FAILED, got %s", got.Status)
	}
}

func TestProcessJob_SandboxError(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-ERR")
	job.MaxRetries = 0
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return nil, errors.New("sandbox exploded")
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if !msg.acked.Load() {
		t.Fatal("expected ACK after exhausting retries (error path)")
	}

	got, _ := store.Get(context.Background(), job.ID)
	if got.Status != JobFailed {
		t.Errorf("expected FAILED, got %s", got.Status)
	}
	if got.Attempts[0].Output != "sandbox exploded" {
		t.Errorf("expected error captured in output, got %q", got.Attempts[0].Output)
	}
}

func TestProcessJob_RetryOnFailure(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-RETRY")
	job.MaxRetries = 2
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 1, Output: "flaky"}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	// First attempt fails with retries remaining → NAK so NATS redelivers.
	if !msg.nacked.Load() {
		t.Fatal("expected NAK when retries remain")
	}
	if msg.acked.Load() {
		t.Fatal("expected msg NOT ACKed when retries remain")
	}

	got, _ := store.Get(context.Background(), job.ID)
	if got.Status != JobPending {
		t.Errorf("expected status reset to PENDING for retry, got %s", got.Status)
	}
}

func TestProcessJob_SkipsCancelledJob(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-CANCEL-PRE")
	job.Status = JobCancelled
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	executed := false
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			executed = true
			return &ExecResult{ExitCode: 0}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if executed {
		t.Fatal("sandbox should not execute for a cancelled job")
	}
	if !msg.acked.Load() {
		t.Fatal("expected ACK for pre-cancelled job")
	}
}

func TestProcessJob_SkipsRunningJob(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-ALREADY-RUNNING")
	job.Status = JobRunning
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	executed := false
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			executed = true
			return &ExecResult{ExitCode: 0}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if executed {
		t.Fatal("sandbox should not execute for an already-running job")
	}
	if !msg.acked.Load() {
		t.Fatal("expected ACK for already-running job")
	}
}

func TestProcessJob_SkipsSucceededJob(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-ALREADY-DONE")
	job.Status = JobSucceeded
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	executed := false
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			executed = true
			return &ExecResult{ExitCode: 0}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if executed {
		t.Fatal("sandbox should not execute for a succeeded job")
	}
	if !msg.acked.Load() {
		t.Fatal("expected ACK for succeeded job")
	}
}

func TestProcessJob_CancelledDuringExecution(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-CANCEL-MID")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{
		runFn: func(ctx context.Context, claimName, _, _ string, cancelFn func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			// Simulate the job being cancelled externally mid-execution.
			// Read current record (which has the in-progress attempt) and flip status.
			current, _ := store.Get(ctx, job.ID)
			current.Status = JobCancelled
			current.UpdatedAt = time.Now().UTC()
			_ = store.Put(ctx, current)
			return &ExecResult{ExitCode: 1, Output: "cancelled mid-run"}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	// ACKed because the job is cancelled (not retried).
	if !msg.acked.Load() {
		t.Fatal("expected ACK for mid-run cancelled job")
	}

	got, _ := store.Get(context.Background(), job.ID)
	if got.Status != JobCancelled {
		t.Errorf("expected CANCELLED status preserved, got %s", got.Status)
	}
}

func TestProcessJob_MissingJobAcks(t *testing.T) {
	// Job ID in message doesn't exist in the store → ACK to prevent poison loop.
	store := newMemStore()
	msg := newFakeMsg([]byte("NONEXISTENT-JOB"))

	sandbox := &fakeSandbox{}
	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	if !msg.acked.Load() {
		t.Fatal("expected ACK for missing job to avoid poison re-delivery")
	}
}

func TestProcessJob_ContextCancelledBeforeExec(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-CTX")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{
		runFn: func(ctx context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return nil, ctx.Err()
		},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // immediately cancelled

	c := newTestConsumer(store, sandbox)
	c.processJob(ctx, msg)

	// Even with a cancelled context the job record should be updated.
	got, _ := store.Get(context.Background(), job.ID)
	// Status should not be stuck in RUNNING.
	if got.Status == JobRunning {
		t.Errorf("job stuck in RUNNING after context cancellation")
	}
}

func TestProcessJob_StoreUpdateFailureOnStart_Nacks(t *testing.T) {
	// Simulate a store that fails on Put after the first Get.
	store := newMemStore()
	job := pendingJob("JOB-STORE-FAIL")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	// errStore wraps memStore but fails on every Put after the initial seed.
	callCount := 0
	errStore := &errOnPutStore{
		inner:     store,
		failAfter: 0, // fail on the very first Put (transition to RUNNING)
		callCount: &callCount,
	}

	sandbox := &fakeSandbox{}
	c := newTestConsumer(errStore, sandbox)
	c.processJob(context.Background(), msg)

	if !msg.nacked.Load() {
		t.Fatal("expected NAK when store.Put fails transitioning to RUNNING")
	}
}

func TestBuildTaskPrompt_FirstAttempt(t *testing.T) {
	c := newTestConsumer(newMemStore(), &fakeSandbox{})
	job := pendingJob("JOB-PROMPT")
	job.Task = "run the tests"

	prompt := c.buildTaskPrompt(job, 1)
	if prompt != "run the tests" {
		t.Errorf("expected raw task on first attempt, got %q", prompt)
	}
}

func TestBuildTaskPrompt_RetryIncludesPreviousOutput(t *testing.T) {
	c := newTestConsumer(newMemStore(), &fakeSandbox{})
	exitCode := 1
	job := &JobRecord{
		Task: "run the tests",
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: "ERROR: build failed"},
			{Number: 2, StartedAt: time.Now().UTC()}, // current in-progress attempt (appended before buildTaskPrompt is called)
		},
	}

	prompt := c.buildTaskPrompt(job, 2)

	if prompt == "run the tests" {
		t.Error("retry prompt should differ from original task")
	}
	if !contains(prompt, "retry attempt 2") {
		t.Errorf("retry prompt should mention attempt number, got: %q", prompt)
	}
	if !contains(prompt, "ERROR: build failed") {
		t.Errorf("retry prompt should include previous output, got: %q", prompt)
	}
}

func TestBuildTaskPrompt_LongOutputTruncated(t *testing.T) {
	c := newTestConsumer(newMemStore(), &fakeSandbox{})
	exitCode := 1
	longOutput := fmt.Sprintf("%02001d", 0) // 2001 chars
	job := &JobRecord{
		Task: "run the tests",
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: longOutput},
			{Number: 2, StartedAt: time.Now().UTC()}, // current in-progress attempt
		},
	}

	prompt := c.buildTaskPrompt(job, 2)
	// buildTaskPrompt truncates previous output to 2000 chars
	if len(prompt) > 3000 {
		t.Errorf("prompt too long after truncation: %d chars", len(prompt))
	}
}

func TestProcessJob_ParsesStructuredResult(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-RESULT")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			output := "doing work...\n```goose-result\ntype: pr\nurl: https://github.com/jomcgi/homelab/pull/42\nsummary: Fixed the thing. CI passes.\n```\n"
			return &ExecResult{ExitCode: 0, Output: output}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	got, _ := store.Get(context.Background(), job.ID)
	if got.Status != JobSucceeded {
		t.Fatalf("expected SUCCEEDED, got %s", got.Status)
	}
	if len(got.Attempts) != 1 {
		t.Fatalf("expected 1 attempt, got %d", len(got.Attempts))
	}
	result := got.Attempts[0].Result
	if result == nil {
		t.Fatal("expected parsed result, got nil")
	}
	if result.Type != "pr" {
		t.Errorf("result.Type = %q, want %q", result.Type, "pr")
	}
	if result.URL != "https://github.com/jomcgi/homelab/pull/42" {
		t.Errorf("result.URL = %q", result.URL)
	}
	if result.Summary != "Fixed the thing. CI passes." {
		t.Errorf("result.Summary = %q", result.Summary)
	}
}

func TestProcessJob_NoStructuredResult(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-NO-RESULT")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))
	sandbox := &fakeSandbox{} // default: exit 0, "success" (no result block)

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	got, _ := store.Get(context.Background(), job.ID)
	if got.Attempts[0].Result != nil {
		t.Errorf("expected nil result for output without goose-result block, got %+v", got.Attempts[0].Result)
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsAt(s, substr))
}

func containsAt(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// errOnPutStore wraps a Store and fails Put after failAfter calls.
type errOnPutStore struct {
	inner     Store
	failAfter int
	callCount *int
}

func (e *errOnPutStore) Put(ctx context.Context, job *JobRecord) error {
	*e.callCount++
	if *e.callCount > e.failAfter {
		return errors.New("store unavailable")
	}
	return e.inner.Put(ctx, job)
}

func (e *errOnPutStore) Get(ctx context.Context, id string) (*JobRecord, error) {
	return e.inner.Get(ctx, id)
}

func (e *errOnPutStore) Delete(ctx context.Context, id string) error {
	return e.inner.Delete(ctx, id)
}

func (e *errOnPutStore) List(ctx context.Context, statusFilter, tagFilter []string, limit, offset int) ([]JobRecord, int, error) {
	return e.inner.List(ctx, statusFilter, tagFilter, limit, offset)
}

func TestProcessJob_PlanProgressFlushedDuringExecution(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-PLAN-PROGRESS")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	// The sandbox writes plan data to the planTracker, simulating what
	// pollUntilDone does when it receives plan updates from the runner.
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, pb *planTracker) (*ExecResult, error) {
			// Simulate plan progress updates during execution.
			pb.Update([]PlanStep{
				{Agent: "planner", Description: "Create plan", Status: "completed"},
				{Agent: "coder", Description: "Write code", Status: "running"},
				{Agent: "reviewer", Description: "Review changes", Status: "pending"},
			}, 1)

			plan := []PlanStep{
				{Agent: "planner", Description: "Create plan", Status: "completed"},
				{Agent: "coder", Description: "Write code", Status: "completed"},
				{Agent: "reviewer", Description: "Review changes", Status: "completed"},
			}
			return &ExecResult{ExitCode: 0, Output: "done", Plan: plan}, nil
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
	// Final plan from ExecResult should be stored.
	if len(got.Plan) != 3 {
		t.Fatalf("expected 3 plan steps, got %d", len(got.Plan))
	}
	if got.Plan[0].Agent != "planner" {
		t.Errorf("plan[0].Agent = %q, want %q", got.Plan[0].Agent, "planner")
	}
	if got.Plan[2].Status != "completed" {
		t.Errorf("plan[2].Status = %q, want %q", got.Plan[2].Status, "completed")
	}
}

func TestPlanTracker_ConcurrentAccess(t *testing.T) {
	pt := &planTracker{}

	// Verify initial state is empty.
	plan, step := pt.Get()
	if len(plan) != 0 || step != 0 {
		t.Fatalf("expected empty initial state, got %d steps at step %d", len(plan), step)
	}

	// Update and verify.
	pt.Update([]PlanStep{
		{Agent: "planner", Description: "Plan", Status: "completed"},
		{Agent: "coder", Description: "Code", Status: "running"},
	}, 1)

	plan, step = pt.Get()
	if len(plan) != 2 {
		t.Fatalf("expected 2 plan steps, got %d", len(plan))
	}
	if step != 1 {
		t.Errorf("expected step 1, got %d", step)
	}
	if plan[1].Status != "running" {
		t.Errorf("plan[1].Status = %q, want %q", plan[1].Status, "running")
	}
}

func TestFlushProgress_WritesPlanToStore(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-FLUSH-PLAN")
	job.Status = JobRunning
	job.Attempts = []Attempt{{Number: 1, StartedAt: time.Now().UTC()}}
	_ = store.Put(context.Background(), job)

	c := newTestConsumer(store, &fakeSandbox{})
	buf := newSyncBuffer(maxOutputBytes)
	buf.Write([]byte("some output"))

	planBuf := &planTracker{}
	planBuf.Update([]PlanStep{
		{Agent: "planner", Description: "Create plan", Status: "completed"},
		{Agent: "coder", Description: "Write code", Status: "running"},
	}, 1)

	c.flushProgress(context.Background(), job.ID, buf, planBuf)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if len(got.Plan) != 2 {
		t.Fatalf("expected 2 plan steps after flush, got %d", len(got.Plan))
	}
	if got.CurrentStep != 1 {
		t.Errorf("expected CurrentStep=1, got %d", got.CurrentStep)
	}
	if got.Attempts[0].Output != "some output" {
		t.Errorf("output = %q, want %q", got.Attempts[0].Output, "some output")
	}
}
