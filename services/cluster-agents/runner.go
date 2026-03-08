package main

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// Runner manages the lifecycle of multiple agent loops.
type Runner struct {
	agents []Agent
}

// NewRunner creates a runner for the given agents.
func NewRunner(agents []Agent) *Runner {
	return &Runner{agents: agents}
}

// Run starts all agent loops and blocks until ctx is cancelled.
func (r *Runner) Run(ctx context.Context) {
	var wg sync.WaitGroup

	for _, agent := range r.agents {
		wg.Add(1)
		go func(a Agent) {
			defer wg.Done()
			r.runAgent(ctx, a)
		}(agent)
	}

	wg.Wait()
}

func (r *Runner) runAgent(ctx context.Context, agent Agent) {
	slog.Info("agent loop starting", "agent", agent.Name(), "interval", agent.Interval())

	// Run immediately on startup, then on ticker.
	r.sweep(ctx, agent)

	ticker := time.NewTicker(agent.Interval())
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			slog.Info("agent loop stopping", "agent", agent.Name())
			return
		case <-ticker.C:
			r.sweep(ctx, agent)
		}
	}
}

func (r *Runner) sweep(ctx context.Context, agent Agent) {
	start := time.Now()
	logger := slog.With("agent", agent.Name())

	findings, err := agent.Collect(ctx)
	if err != nil {
		logger.Error("collect failed", "error", err)
		return
	}

	actions, err := agent.Analyze(ctx, findings)
	if err != nil {
		logger.Error("analyze failed", "error", err)
		return
	}

	if err := agent.Execute(ctx, actions); err != nil {
		logger.Error("execute failed", "error", err)
		return
	}

	logger.Info("sweep complete",
		"findings", len(findings),
		"actions", len(actions),
		"duration", time.Since(start),
	)
}
