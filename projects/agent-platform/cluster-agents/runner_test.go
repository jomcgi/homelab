package main

import (
	"context"
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
