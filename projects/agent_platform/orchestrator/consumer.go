package main

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

const maxOutputBytes = 32 * 1024 // 32KB tail — full output lives in pod logs / SigNoz

// Sandbox is the interface for executing agent tasks in an isolated environment.
// SandboxExecutor satisfies this interface; tests inject a fake implementation.
type Sandbox interface {
	Run(ctx context.Context, claimName, task, recipe string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error)
}

// Consumer pulls jobs from a NATS JetStream consumer and executes them in sandboxes.
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	maxDuration time.Duration
	recipes     map[string]map[string]any
	logger      *slog.Logger
}

// NewConsumer creates a Consumer that processes jobs from the given JetStream consumer.
func NewConsumer(cons jetstream.Consumer, store Store, sandbox Sandbox, maxDuration time.Duration, recipes map[string]map[string]any, logger *slog.Logger) *Consumer {
	return &Consumer{
		cons:        cons,
		store:       store,
		sandbox:     sandbox,
		maxDuration: maxDuration,
		recipes:     recipes,
		logger:      logger,
	}
}

// Run processes jobs until the context is cancelled.
func (c *Consumer) Run(ctx context.Context) {
	c.logger.Info("consumer started")

	var wg sync.WaitGroup
	defer wg.Wait() // Wait for in-flight jobs on shutdown

	for {
		msgs, err := c.cons.Fetch(1, jetstream.FetchMaxWait(30*time.Second))
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			c.logger.Warn("fetch error", "error", err)
			continue
		}

		for msg := range msgs.Messages() {
			wg.Add(1)
			go func() {
				defer wg.Done()
				c.processJob(ctx, msg)
			}()
		}

		if err := msgs.Error(); err != nil {
			if ctx.Err() != nil {
				return
			}
			// FetchMaxWait timeout is not an error worth logging
			c.logger.Debug("fetch iteration ended", "error", err)
		}
	}
}

func (c *Consumer) processJob(ctx context.Context, msg jetstream.Msg) {
	jobCtx, jobCancel := context.WithTimeout(ctx, c.maxDuration)
	defer jobCancel()

	jobID := string(msg.Data())
	logger := c.logger.With("jobID", jobID)

	job, err := c.store.Get(jobCtx, jobID)
	if err != nil {
		logger.Error("failed to get job", "error", err)
		// ACK to prevent infinite redelivery of poison messages (e.g. deleted/expired KV entry).
		_ = msg.Ack()
		return
	}

	// Only process jobs in PENDING state. RUNNING means another attempt is
	// active (e.g. NATS redelivery after restart); SUCCEEDED/FAILED are terminal.
	// This prevents duplicate long-running jobs after orchestrator restarts.
	if job.Status != JobPending {
		logger.Info("skipping job, not in pending state", "status", job.Status)
		_ = msg.Ack()
		return
	}

	// Create new attempt.
	attemptNum := len(job.Attempts) + 1
	claimName := fmt.Sprintf("orch-%s-%d", strings.ToLower(job.ID), attemptNum)

	attempt := Attempt{
		Number:           attemptNum,
		SandboxClaimName: claimName,
		StartedAt:        time.Now().UTC(),
	}
	job.Attempts = append(job.Attempts, attempt)
	job.Status = JobRunning

	if err := c.store.Put(jobCtx, job); err != nil {
		logger.Error("failed to update job to running", "error", err)
		_ = msg.Nak()
		return
	}

	task := c.buildTaskPrompt(job, attemptNum)
	logger.Info("executing task", "attempt", attemptNum, "claim", claimName)

	cancelFn := func() bool {
		current, err := c.store.Get(jobCtx, jobID)
		if err != nil {
			return false
		}
		return current.Status == JobCancelled
	}

	outputBuf := newSyncBuffer(maxOutputBytes)

	// Render recipe for this agent.
	recipeYAML := ""
	if job.Profile != "" && c.recipes != nil {
		if recipe, ok := c.recipes[job.Profile]; ok {
			var err error
			recipeYAML, err = renderRecipeYAML(recipe, task)
			if err != nil {
				c.logger.Error("failed to render recipe", "agent", job.Profile, "error", err)
			}
		}
	}

	// Run sandbox in a goroutine so we can flush output periodically.
	type sandboxResult struct {
		result *ExecResult
		err    error
	}
	resultCh := make(chan sandboxResult, 1)
	go func() {
		r, err := c.sandbox.Run(jobCtx, claimName, task, recipeYAML, cancelFn, outputBuf)
		resultCh <- sandboxResult{r, err}
	}()

	// Periodic output flush and NATS ack deadline extension.
	// InProgress() resets the AckWait timer so NATS doesn't redeliver the
	// message while the job is still actively running.
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	var res sandboxResult
loop:
	for {
		select {
		case res = <-resultCh:
			break loop
		case <-ticker.C:
			_ = msg.InProgress()
			c.flushOutput(jobCtx, jobID, outputBuf)
		}
	}

	result, execErr := res.result, res.err

	// Re-read job to get latest state.
	job, err = c.store.Get(jobCtx, jobID)
	if err != nil {
		logger.Error("failed to re-read job after exec", "error", err)
		_ = msg.Nak()
		return
	}

	// Update the attempt record.
	now := time.Now().UTC()
	idx := len(job.Attempts) - 1
	job.Attempts[idx].FinishedAt = &now

	if result != nil {
		job.Attempts[idx].ExitCode = &result.ExitCode
		output := result.Output
		if len(output) > maxOutputBytes {
			output = output[len(output)-maxOutputBytes:]
			job.Attempts[idx].Truncated = true
		}
		job.Attempts[idx].Output = output
		job.Attempts[idx].Result = parseGooseResult(output)
	} else if execErr != nil {
		job.Attempts[idx].Output = execErr.Error()
	}

	// Check for cancellation after exec.
	if job.Status == JobCancelled {
		logger.Info("job was cancelled during execution")
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Error("failed to store cancelled job", "error", err)
		}
		_ = msg.Ack()
		return
	}

	failed := execErr != nil || (result != nil && result.ExitCode != 0)
	retriesRemaining := job.MaxRetries - len(job.Attempts)

	if failed && retriesRemaining > 0 {
		logger.Info("task failed, will retry", "attempt", attemptNum, "retriesRemaining", retriesRemaining, "error", execErr)
		// Set status back to PENDING for next attempt; store and Nak to redeliver.
		job.Status = JobPending
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Error("failed to store retry state", "error", err)
		}
		_ = msg.Nak()
		return
	}

	if failed {
		logger.Info("task failed, retries exhausted", "attempt", attemptNum, "error", execErr)
		job.Status = JobFailed
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Error("failed to store failed state", "error", err)
		}
		_ = msg.Ack()
		return
	}

	logger.Info("task succeeded", "attempt", attemptNum)
	job.Status = JobSucceeded
	if err := c.store.Put(jobCtx, job); err != nil {
		logger.Error("failed to store succeeded state", "error", err)
	}
	_ = msg.Ack()
}

func (c *Consumer) buildTaskPrompt(job *JobRecord, attemptNum int) string {
	if attemptNum <= 1 || len(job.Attempts) < 2 {
		return job.Task
	}

	// Get the previous attempt for context.
	prev := job.Attempts[len(job.Attempts)-2]
	prevOutput := prev.Output
	if len(prevOutput) > 2000 {
		prevOutput = prevOutput[len(prevOutput)-2000:]
	}

	exitCode := -1
	if prev.ExitCode != nil {
		exitCode = *prev.ExitCode
	}

	return fmt.Sprintf(`This is retry attempt %d. The previous attempt (attempt %d) failed with exit code %d.

Last 2000 characters of previous output:
---
%s
---

Original task:
%s`, attemptNum, prev.Number, exitCode, prevOutput, job.Task)
}

func (c *Consumer) flushOutput(ctx context.Context, jobID string, buf *syncBuffer) {
	// Re-read from KV to avoid overwriting status changes (e.g. cancellation).
	current, err := c.store.Get(ctx, jobID)
	if err != nil || len(current.Attempts) == 0 {
		return
	}
	output := buf.String()
	truncated := len(output) > maxOutputBytes
	if truncated {
		output = output[len(output)-maxOutputBytes:]
	}
	last := &current.Attempts[len(current.Attempts)-1]
	last.Output = output
	last.Truncated = truncated
	if err := c.store.Put(ctx, current); err != nil {
		c.logger.Warn("failed to flush output", "jobID", jobID, "error", err)
	}
}
