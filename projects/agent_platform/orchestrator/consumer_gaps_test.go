package main

// consumer_gaps_test.go covers the remaining gaps identified in the coverage report:
//
//  1. Consumer.Run shutdown drain — wg.Wait ensures in-flight goroutines
//     complete before Run returns, even with multi-message concurrency.
//  2. processJob all-completed plan — when every plan step has status
//     "completed", CurrentStep must be set to the last index (sentinel).

import (
	"context"
	"log/slog"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// ============================================================
// 1. Consumer.Run shutdown drain: wg.Wait drains in-flight jobs
// ============================================================

// TestConsumerRun_ShutdownDrainsInFlightJobs verifies that when the context is
// cancelled while a job goroutine is still executing, Consumer.Run does not
// return until that goroutine completes. This exercises the wg.Wait() call
// deferred at the top of Run(), which is not covered by TestConsumerRun_DispatchesJobMessage
// (that test cancels after the sandbox has already returned).
func TestConsumerRun_ShutdownDrainsInFlightJobs(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-DRAIN")
	_ = store.Put(context.Background(), job)

	ctx, cancel := context.WithCancel(context.Background())

	// sandboxStarted is closed when the sandbox begins executing.
	// sandboxRelease is closed to allow the sandbox to finish.
	sandboxStarted := make(chan struct{})
	sandboxRelease := make(chan struct{})

	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			close(sandboxStarted)
			<-sandboxRelease
			return &ExecResult{ExitCode: 0, Output: "drained"}, nil
		},
	}

	msgDelivered := false
	cons := &runnableFakeConsumer{
		fetchFn: func(_ int, _ ...jetstream.FetchOpt) (jetstream.MessageBatch, error) {
			if !msgDelivered {
				msgDelivered = true
				return &fakeMsgBatch{msgs: []jetstream.Msg{newFakeMsg([]byte(job.ID))}}, nil
			}
			// Block subsequent fetches until context is cancelled.
			<-ctx.Done()
			return nil, ctx.Err()
		},
	}

	c := NewConsumer(cons, store, sandbox, nil, nil, 5*time.Minute, slog.Default())
	runDone := make(chan struct{})
	go func() {
		defer close(runDone)
		c.Run(ctx)
	}()

	// Wait for the sandbox to be invoked (job goroutine is in-flight).
	select {
	case <-sandboxStarted:
	case <-time.After(5 * time.Second):
		cancel()
		t.Fatal("sandbox not called within 5s")
	}

	// Cancel the context. Run() should NOT return until the sandbox finishes.
	cancel()

	// Run() must not return while the sandbox is still blocked.
	select {
	case <-runDone:
		t.Fatal("Consumer.Run returned before in-flight goroutine completed")
	case <-time.After(200 * time.Millisecond):
		// Good — Run is still waiting (wg.Wait draining).
	}

	// Release the sandbox, allowing the job goroutine to complete.
	close(sandboxRelease)

	select {
	case <-runDone:
		// Pass — Run exited only after the goroutine drained.
	case <-time.After(5 * time.Second):
		t.Fatal("Consumer.Run did not exit within 5s after sandbox released")
	}

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.Status != JobSucceeded {
		t.Errorf("job status = %s, want SUCCEEDED", got.Status)
	}
}

// TestConsumerRun_MultiMsgConcurrency verifies that Consumer.Run can dispatch
// multiple messages concurrently. Two jobs are delivered in a single batch;
// both must complete even though they execute in parallel goroutines. This
// exercises the goroutine launch inside the for msg := range msgs.Messages()
// loop and the wg.Wait() drain at shutdown.
func TestConsumerRun_MultiMsgConcurrency(t *testing.T) {
	store := newMemStore()
	job1 := pendingJob("JOB-MULTI-1")
	job2 := pendingJob("JOB-MULTI-2")
	_ = store.Put(context.Background(), job1)
	_ = store.Put(context.Background(), job2)

	ctx, cancel := context.WithCancel(context.Background())

	// Gate to ensure both goroutines are running simultaneously.
	var concurrentWg sync.WaitGroup
	concurrentWg.Add(2)
	allRunning := make(chan struct{})
	go func() {
		concurrentWg.Wait()
		close(allRunning)
	}()

	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			concurrentWg.Done()
			// Wait until both goroutines have started to prove concurrency.
			select {
			case <-allRunning:
			case <-time.After(5 * time.Second):
			}
			return &ExecResult{ExitCode: 0, Output: "ok"}, nil
		},
	}

	msgDelivered := false
	cons := &runnableFakeConsumer{
		fetchFn: func(_ int, _ ...jetstream.FetchOpt) (jetstream.MessageBatch, error) {
			if !msgDelivered {
				msgDelivered = true
				return &fakeMsgBatch{msgs: []jetstream.Msg{
					newFakeMsg([]byte(job1.ID)),
					newFakeMsg([]byte(job2.ID)),
				}}, nil
			}
			<-ctx.Done()
			return nil, ctx.Err()
		},
	}

	c := NewConsumer(cons, store, sandbox, nil, nil, 5*time.Minute, slog.Default())
	runDone := make(chan struct{})
	go func() {
		defer close(runDone)
		c.Run(ctx)
	}()

	// Wait for both sandboxes to run concurrently.
	select {
	case <-allRunning:
	case <-time.After(10 * time.Second):
		cancel()
		t.Fatal("both job goroutines did not start within 10s")
	}

	cancel()

	select {
	case <-runDone:
	case <-time.After(10 * time.Second):
		t.Fatal("Consumer.Run did not exit within 10s")
	}

	for _, id := range []string{job1.ID, job2.ID} {
		got, err := store.Get(context.Background(), id)
		if err != nil {
			t.Fatalf("store.Get(%s): %v", id, err)
		}
		if got.Status != JobSucceeded {
			t.Errorf("job %s status = %s, want SUCCEEDED", id, got.Status)
		}
	}
}

// ============================================================
// 2. processJob all-completed plan: CurrentStep sentinel
// ============================================================

// TestProcessJob_AllCompletedPlan_CurrentStepSentinel verifies that when every
// step in the result plan has status "completed" (no "running" or "pending"
// steps), processJob sets CurrentStep to the last step index (len-1). This
// exercises the sentinel logic at consumer.go lines 242–251 where the for-loop
// falls through all completed steps and the last assignment sets CurrentStep to
// the final index.
func TestProcessJob_AllCompletedPlan_CurrentStepSentinel(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-ALL-COMPLETED")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	// All three steps are "completed" — no running or pending step in the plan.
	allCompletedPlan := []PlanStep{
		{Agent: "step-1", Description: "First step", Status: "completed"},
		{Agent: "step-2", Description: "Second step", Status: "completed"},
		{Agent: "step-3", Description: "Third step", Status: "completed"},
	}
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 0, Output: "all done", Plan: allCompletedPlan}, nil
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
	if len(got.Plan) != 3 {
		t.Fatalf("expected 3 plan steps, got %d", len(got.Plan))
	}
	// Sentinel: CurrentStep must equal the last index (2) when all steps complete.
	wantCurrentStep := len(allCompletedPlan) - 1
	if got.CurrentStep != wantCurrentStep {
		t.Errorf("CurrentStep = %d, want %d (last index when all steps completed)", got.CurrentStep, wantCurrentStep)
	}
}

// TestProcessJob_PartialCompletedPlan_CurrentStep verifies that when the plan
// contains a mix of completed and non-completed steps, CurrentStep points at
// the first non-completed (running or pending) step, not the last index.
func TestProcessJob_PartialCompletedPlan_CurrentStep(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-PARTIAL-COMPLETED")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	partialPlan := []PlanStep{
		{Agent: "step-1", Description: "First step", Status: "completed"},
		{Agent: "step-2", Description: "Second step", Status: "running"},
		{Agent: "step-3", Description: "Third step", Status: "pending"},
	}
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 0, Output: "done", Plan: partialPlan}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	// CurrentStep should be index 1 (the first "running" step breaks the loop).
	if got.CurrentStep != 1 {
		t.Errorf("CurrentStep = %d, want 1 (index of first non-completed step)", got.CurrentStep)
	}
}

// TestProcessJob_SingleStepAllCompleted_CurrentStepIsZero verifies the edge
// case where a single-step plan is completed — CurrentStep must be 0 (the only
// valid index), not left at its default zero and not out-of-bounds.
func TestProcessJob_SingleStepAllCompleted_CurrentStepIsZero(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SINGLE-STEP")
	_ = store.Put(context.Background(), job)

	msg := newFakeMsg([]byte(job.ID))

	singleStepPlan := []PlanStep{
		{Agent: "only-step", Description: "The only step", Status: "completed"},
	}
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			return &ExecResult{ExitCode: 0, Output: "done", Plan: singleStepPlan}, nil
		},
	}

	c := newTestConsumer(store, sandbox)
	c.processJob(context.Background(), msg)

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.CurrentStep != 0 {
		t.Errorf("CurrentStep = %d, want 0 for single-step completed plan", got.CurrentStep)
	}
}
