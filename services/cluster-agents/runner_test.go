package main

import (
	"context"
	"sync"
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
