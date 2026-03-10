package main

import (
	"context"
	"fmt"
	"log/slog"
	"runtime/debug"
	"sync"
	"time"
)

// defaultSweepTimeout is the maximum duration a single sweep may run before
// its context is cancelled. This bounds each patrol iteration so that a hung
// network call cannot block the loop indefinitely.
//
// The value is intentionally well below the 1-hour patrol interval so that
// a stuck sweep times out cleanly and the next scheduled sweep fires on time.
const defaultSweepTimeout = 5 * time.Minute

// Runner manages the lifecycle of multiple agent loops.
type Runner struct {
	agents       []Agent
	sweepTimeout time.Duration
}

// NewRunner creates a runner for the given agents.
func NewRunner(agents []Agent) *Runner {
	return &Runner{
		agents:       agents,
		sweepTimeout: defaultSweepTimeout,
	}
}

// Run starts all agent loops and blocks until ctx is cancelled.
//
// Each agent loop is supervised: if runAgent returns for any reason other
// than ctx cancellation (e.g. an unexpected panic that was recovered, or a
// future code path that returns early), the loop is restarted after a short
// back-off. This prevents a one-time transient failure from permanently
// stopping patrol coverage.
func (r *Runner) Run(ctx context.Context) {
	var wg sync.WaitGroup

	for _, agent := range r.agents {
		wg.Add(1)
		go func(a Agent) {
			defer wg.Done()
			for ctx.Err() == nil {
				r.runAgent(ctx, a)
				if ctx.Err() != nil {
					// Normal shutdown — context was cancelled.
					return
				}
				// runAgent returned without ctx being done. This should not
				// happen in normal operation; log a warning and restart.
				slog.Warn("agent loop exited unexpectedly, restarting",
					"agent", a.Name())
				select {
				case <-time.After(5 * time.Second):
				case <-ctx.Done():
					return
				}
			}
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

// sweep executes one full collect→analyze→execute cycle for the given agent.
//
// Two safety mechanisms are applied on every call:
//
//  1. Per-sweep timeout: a child context with sweepTimeout is used for all
//     agent calls. This ensures that a single stalled HTTP request (e.g. a
//     half-open TCP connection to SigNoz or the orchestrator) cannot block
//     the patrol goroutine indefinitely, preventing the scheduling gap that
//     was observed in production.
//
//  2. Panic recovery: if any agent method panics, the panic is caught, logged
//     with a full stack trace, and the sweep returns normally so the loop
//     continues. Without this, a nil-pointer or other panic would crash the
//     entire process.
func (r *Runner) sweep(ctx context.Context, agent Agent) {
	// Bound this sweep with a hard deadline independent of the caller's ctx.
	sweepCtx, cancel := context.WithTimeout(ctx, r.sweepTimeout)
	defer cancel()

	// Recover from any panic to keep the patrol loop alive.
	defer func() {
		if rec := recover(); rec != nil {
			slog.Error("sweep panicked — loop will continue",
				"agent", agent.Name(),
				"panic", fmt.Sprintf("%v", rec),
				"stack", string(debug.Stack()),
			)
		}
	}()

	start := time.Now()
	logger := slog.With("agent", agent.Name())

	findings, err := agent.Collect(sweepCtx)
	if err != nil {
		logger.Error("collect failed", "error", err)
		return
	}

	actions, err := agent.Analyze(sweepCtx, findings)
	if err != nil {
		logger.Error("analyze failed", "error", err)
		return
	}

	if err := agent.Execute(sweepCtx, actions); err != nil {
		logger.Error("execute failed", "error", err)
		return
	}

	logger.Info("sweep complete",
		"findings", len(findings),
		"actions", len(actions),
		"duration", time.Since(start),
	)
}
