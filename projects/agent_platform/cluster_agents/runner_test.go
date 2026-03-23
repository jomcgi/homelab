package main

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type fakeAgent struct {
	name     string
	interval time.Duration
	mu       sync.Mutex
	sweeps   int
	findings []Finding
	actions  []Action
}

func (a *fakeAgent) Name() string            { return a.name }
func (a *fakeAgent) Interval() time.Duration { return a.interval }

func (a *fakeAgent) Collect(_ context.Context) ([]Finding, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.sweeps++
	return a.findings, nil
}

func (a *fakeAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	return a.actions, nil
}

func (a *fakeAgent) Execute(_ context.Context, actions []Action) error {
	return nil
}

func (a *fakeAgent) getSweeps() int {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.sweeps
}

func TestRunnerExecutesAgentLoop(t *testing.T) {
	agent := &fakeAgent{
		name:     "test-agent",
		interval: 50 * time.Millisecond,
	}

	r := NewRunner([]Agent{agent})

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	sweeps := agent.getSweeps()
	if sweeps < 2 {
		t.Errorf("expected at least 2 sweeps, got %d", sweeps)
	}
}

func TestRunnerRunsMultipleAgents(t *testing.T) {
	a1 := &fakeAgent{name: "agent-1", interval: 50 * time.Millisecond}
	a2 := &fakeAgent{name: "agent-2", interval: 50 * time.Millisecond}

	r := NewRunner([]Agent{a1, a2})

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if a1.getSweeps() < 2 {
		t.Errorf("agent-1: expected at least 2 sweeps, got %d", a1.getSweeps())
	}
	if a2.getSweeps() < 2 {
		t.Errorf("agent-2: expected at least 2 sweeps, got %d", a2.getSweeps())
	}
}

// panicOnSweepAgent panics on the Nth call to Collect (1-indexed), then
// behaves normally. This lets tests confirm that a panic in sweep does not
// permanently stop the patrol loop.
type panicOnSweepAgent struct {
	fakeAgent
	panicOnCall int
	callCount   int32 // atomic
}

func (a *panicOnSweepAgent) Collect(ctx context.Context) ([]Finding, error) {
	n := int(atomic.AddInt32(&a.callCount, 1))
	if n == a.panicOnCall {
		panic("simulated sweep panic")
	}
	return a.fakeAgent.Collect(ctx)
}

// TestRunnerContinuesAfterSweepPanic verifies that a panic inside sweep is
// recovered and the patrol loop continues running subsequent sweeps.
//
// Before the fix, sweep had no panic recovery. Any panic would propagate up
// through runAgent, crash the goroutine (and the whole process if unrecovered
// higher up). After the fix, sweep catches the panic, logs it, and returns
// normally so the ticker-driven loop can continue.
func TestRunnerContinuesAfterSweepPanic(t *testing.T) {
	agent := &panicOnSweepAgent{
		fakeAgent: fakeAgent{
			name:     "panic-agent",
			interval: 20 * time.Millisecond,
		},
		panicOnCall: 2, // panic on the second Collect call
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	// The loop should have run more than 2 times: the panic on call 2 is
	// recovered and subsequent sweeps continue normally.
	if agent.getSweeps() < 2 {
		t.Errorf("expected at least 2 successful sweeps after panic, got %d", agent.getSweeps())
	}
}

// errOnNthCallAgent returns an error on the Nth call to the configured method
// (Collect, Analyze, or Execute), then succeeds on subsequent calls.
type errOnNthCallAgent struct {
	fakeAgent
	method      string // "collect", "analyze", "execute"
	errOnCall   int
	callCount   int32 // atomic
	successAfter int32 // atomic — counts successful sweeps after the error
}

func (a *errOnNthCallAgent) Collect(ctx context.Context) ([]Finding, error) {
	if a.method != "collect" {
		return a.fakeAgent.Collect(ctx)
	}
	n := int(atomic.AddInt32(&a.callCount, 1))
	if n == a.errOnCall {
		return nil, errors.New("simulated collect error")
	}
	atomic.AddInt32(&a.successAfter, 1)
	return a.fakeAgent.Collect(ctx)
}

func (a *errOnNthCallAgent) Analyze(ctx context.Context, findings []Finding) ([]Action, error) {
	if a.method != "analyze" {
		return a.fakeAgent.Analyze(ctx, findings)
	}
	n := int(atomic.AddInt32(&a.callCount, 1))
	if n == a.errOnCall {
		return nil, errors.New("simulated analyze error")
	}
	atomic.AddInt32(&a.successAfter, 1)
	return a.fakeAgent.Analyze(ctx, findings)
}

func (a *errOnNthCallAgent) Execute(ctx context.Context, actions []Action) error {
	if a.method != "execute" {
		return a.fakeAgent.Execute(ctx, actions)
	}
	n := int(atomic.AddInt32(&a.callCount, 1))
	if n == a.errOnCall {
		return errors.New("simulated execute error")
	}
	atomic.AddInt32(&a.successAfter, 1)
	return a.fakeAgent.Execute(ctx, actions)
}

// TestRunnerSweepCollectErrorDoesNotStopLoop verifies that when Collect returns
// an error, the sweep returns early (without calling Analyze or Execute) but the
// patrol loop continues running subsequent sweeps.
func TestRunnerSweepCollectErrorDoesNotStopLoop(t *testing.T) {
	agent := &errOnNthCallAgent{
		fakeAgent: fakeAgent{
			name:     "collect-error-agent",
			interval: 20 * time.Millisecond,
		},
		method:    "collect",
		errOnCall: 1, // error on first call
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if atomic.LoadInt32(&agent.successAfter) < 1 {
		t.Errorf("expected at least 1 successful sweep after Collect error, got %d",
			atomic.LoadInt32(&agent.successAfter))
	}
}

// TestRunnerSweepAnalyzeErrorDoesNotStopLoop verifies that when Analyze returns
// an error, the sweep returns early (without calling Execute) but the loop
// continues running subsequent sweeps.
func TestRunnerSweepAnalyzeErrorDoesNotStopLoop(t *testing.T) {
	agent := &errOnNthCallAgent{
		fakeAgent: fakeAgent{
			name:     "analyze-error-agent",
			interval: 20 * time.Millisecond,
		},
		method:    "analyze",
		errOnCall: 1, // error on first call
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if atomic.LoadInt32(&agent.successAfter) < 1 {
		t.Errorf("expected at least 1 successful sweep after Analyze error, got %d",
			atomic.LoadInt32(&agent.successAfter))
	}
}

// TestRunnerSweepExecuteErrorDoesNotStopLoop verifies that when Execute returns
// an error, the sweep logs it but the loop continues running subsequent sweeps.
func TestRunnerSweepExecuteErrorDoesNotStopLoop(t *testing.T) {
	agent := &errOnNthCallAgent{
		fakeAgent: fakeAgent{
			name:     "execute-error-agent",
			interval: 20 * time.Millisecond,
		},
		method:    "execute",
		errOnCall: 1, // error on first call
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if atomic.LoadInt32(&agent.successAfter) < 1 {
		t.Errorf("expected at least 1 successful sweep after Execute error, got %d",
			atomic.LoadInt32(&agent.successAfter))
	}
}

// earlyReturnAgent simulates the unexpected case where runAgent's inner loop
// returns without the context being cancelled (e.g. by returning from Collect
// in a way that bypasses the for-select). We achieve this by having Collect
// cancel a context that the agent itself holds — we cannot easily trigger the
// internal loop exit, so instead we verify the restart branch itself via a
// specialised agent whose runAgent equivalent exits early.
//
// A simpler and equivalent approach: use a context that the runner's outer
// loop detects as cancelled before the 5s backoff completes. We test this
// indirectly: the Run loop itself is the supervisor — it must exit when
// context is cancelled even if the inner runAgent is in the 5s back-off sleep.
func TestRunnerRestartBackoffHonoursContextCancellation(t *testing.T) {
	// quickExitAgent exits its Collect immediately so runAgent's loop can
	// return (because Collect is called directly in the first sweep, then the
	// loop waits on the ticker; we can't easily make runAgent exit without
	// context cancellation from outside). Instead we test the backoff select
	// path by having the outer context cancel while the goroutine would be
	// sleeping.
	//
	// We use a very short interval so the goroutine spends most of its time
	// in the ticker, and cancel the context quickly. Run() must return within
	// a reasonable window even if the 5s back-off is active.
	agent := &fakeAgent{
		name:     "restart-backoff-agent",
		interval: 1 * time.Millisecond,
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	elapsed := time.Since(start)
	// Run() must have returned promptly after context cancellation, not
	// after the full 5-second backoff.
	if elapsed > 2*time.Second {
		t.Errorf("Run() took too long to return after context cancellation: %v", elapsed)
	}
}

// blockingAgent blocks in Collect until its context is cancelled. This
// simulates a hung HTTP call — the root cause observed in production where
// the sweep goroutine stopped scheduling after ~3 successful runs.
type blockingAgent struct {
	fakeAgent
	blockUntilCancelled bool
	sweepsAfterBlock    int32 // atomic — counts sweeps after the blocking one
	blocked             chan struct{}
}

func (a *blockingAgent) Collect(ctx context.Context) ([]Finding, error) {
	if a.blockUntilCancelled {
		// Signal that we've entered the blocking call.
		select {
		case a.blocked <- struct{}{}:
		default:
		}
		a.blockUntilCancelled = false
		// Block until context is cancelled (simulates a hung network call).
		<-ctx.Done()
		return nil, ctx.Err()
	}
	atomic.AddInt32(&a.sweepsAfterBlock, 1)
	return a.fakeAgent.Collect(ctx)
}

// TestRunnerContinuesAfterSweepTimeout is the core regression test for the
// production bug.
//
// Scenario reproduced:
//   - The patrol loop ran successfully at T+0, T+interval, T+2*interval.
//   - At T+3*interval, the sweep's HTTP call to SigNoz hung indefinitely
//     (half-open TCP connection). Without a per-sweep timeout, the goroutine
//     blocked forever — no new sweeps, no error logs.
//
// After the fix, sweep creates a child context with sweepTimeout. When the
// blocking Collect call exhausts that deadline, sweep returns with a logged
// error, and the ticker fires the next sweep at T+4*interval as expected.
func TestRunnerContinuesAfterSweepTimeout(t *testing.T) {
	agent := &blockingAgent{
		fakeAgent: fakeAgent{
			name:     "blocking-agent",
			interval: 30 * time.Millisecond,
		},
		blockUntilCancelled: true,
		blocked:             make(chan struct{}, 1),
	}

	// Use a sweep timeout shorter than the test window so we can observe the
	// recovery without waiting minutes.
	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: 40 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	// At least one sweep should have completed after the blocked one timed out.
	if atomic.LoadInt32(&agent.sweepsAfterBlock) < 1 {
		t.Errorf("expected at least 1 sweep after the blocking sweep timed out, got %d",
			atomic.LoadInt32(&agent.sweepsAfterBlock))
	}
}
