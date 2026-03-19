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

// planTracker is a thread-safe container for plan progress updates.
// The sandbox writes plan data during polling, and the consumer reads
// it during the periodic ticker loop to flush progress to the KV store.
type planTracker struct {
	mu   sync.RWMutex
	plan []PlanStep
	step int
}

func (p *planTracker) Update(plan []PlanStep, step int) {
	p.mu.Lock()
	p.plan = plan
	p.step = step
	p.mu.Unlock()
}

func (p *planTracker) Get() ([]PlanStep, int) {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.plan, p.step
}

// Sandbox is the interface for executing agent tasks in an isolated environment.
// SandboxExecutor satisfies this interface; tests inject a fake implementation.
type Sandbox interface {
	Run(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, outputBuf *syncBuffer, planBuf *planTracker) (*ExecResult, error)
}

// Consumer pulls jobs from a NATS JetStream consumer and executes them in sandboxes.
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	publish     func(jobID string) error
	summarizer  *Summarizer
	maxDuration time.Duration
	logger      *slog.Logger
}

// NewConsumer creates a Consumer that processes jobs from the given JetStream consumer.
func NewConsumer(cons jetstream.Consumer, store Store, sandbox Sandbox, publish func(jobID string) error, summarizer *Summarizer, maxDuration time.Duration, logger *slog.Logger) *Consumer {
	return &Consumer{
		cons:        cons,
		store:       store,
		sandbox:     sandbox,
		publish:     publish,
		summarizer:  summarizer,
		maxDuration: maxDuration,
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

	// Trigger 1: Generate clean title from raw task.
	if title, err := c.summarizer.SummarizeTask(jobCtx, job.Task); err != nil {
		logger.Warn("summarize task failed", "error", err)
	} else if title != "" {
		job.Title = title
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Warn("failed to store title", "error", err)
		}
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
	planBuf := &planTracker{}

	// The runner discovers recipes autonomously from disk — no recipe rendering needed.
	recipePath := ""

	// Run sandbox in a goroutine so we can flush output periodically.
	type sandboxResult struct {
		result *ExecResult
		err    error
	}
	resultCh := make(chan sandboxResult, 1)
	go func() {
		r, err := c.sandbox.Run(jobCtx, claimName, task, recipePath, cancelFn, outputBuf, planBuf)
		resultCh <- sandboxResult{r, err}
	}()

	// Periodic output flush and NATS ack deadline extension.
	// InProgress() resets the AckWait timer so NATS doesn't redeliver the
	// message while the job is still actively running.
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	planSummarized := false
	var lastSummarizedAt time.Time

	var res sandboxResult
loop:
	for {
		select {
		case res = <-resultCh:
			break loop
		case <-ticker.C:
			_ = msg.InProgress()
			c.flushProgress(jobCtx, jobID, outputBuf, planBuf)

			// Trigger 2: First plan summary (once).
			if plan, _ := planBuf.Get(); len(plan) > 0 && !planSummarized {
				planSummarized = true
				c.summarizeAndStore(jobCtx, jobID, job.Task, plan, logger)
				lastSummarizedAt = time.Now()
			}

			// Trigger 3: Periodic summary update (every 5m).
			if plan, _ := planBuf.Get(); len(plan) > 0 && planSummarized && time.Since(lastSummarizedAt) >= 5*time.Minute {
				c.summarizeAndStore(jobCtx, jobID, job.Task, plan, logger)
				lastSummarizedAt = time.Now()
			}
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
		output = cleanOutput(output)
		job.Attempts[idx].Output = output
		job.Attempts[idx].Result = parseGooseResult(output)
		if len(result.Plan) > 0 {
			job.Plan = result.Plan
			// Derive current step from plan statuses.
			for i, step := range result.Plan {
				if step.Status == "running" || step.Status == "pending" {
					job.CurrentStep = i
					break
				}
				job.CurrentStep = i
			}
		}
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
		if len(job.Plan) > 0 {
			c.summarizeAndStoreOnJob(jobCtx, job, logger)
		}
		if err := c.store.Put(jobCtx, job); err != nil {
			logger.Error("failed to store failed state", "error", err)
		}
		_ = msg.Ack()
		return
	}

	logger.Info("task succeeded", "attempt", attemptNum)
	job.Status = JobSucceeded
	if len(job.Plan) > 0 {
		c.summarizeAndStoreOnJob(jobCtx, job, logger)
	}
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

// summarizeAndStore reads the current job from the store, generates a summary, and writes it back.
func (c *Consumer) summarizeAndStore(ctx context.Context, jobID, task string, plan []PlanStep, logger *slog.Logger) {
	title, summary, err := c.summarizer.SummarizePlan(ctx, task, plan)
	if err != nil {
		logger.Warn("summarize plan failed", "error", err)
		return
	}
	if title == "" && summary == "" {
		return
	}
	current, err := c.store.Get(ctx, jobID)
	if err != nil {
		logger.Warn("failed to read job for summary update", "error", err)
		return
	}
	if title != "" {
		current.Title = title
	}
	if summary != "" {
		current.Summary = summary
	}
	if err := c.store.Put(ctx, current); err != nil {
		logger.Warn("failed to store summary", "error", err)
	}
}

// summarizeAndStoreOnJob generates a summary and writes it directly to the provided job record.
func (c *Consumer) summarizeAndStoreOnJob(ctx context.Context, job *JobRecord, logger *slog.Logger) {
	title, summary, err := c.summarizer.SummarizePlan(ctx, job.Task, job.Plan)
	if err != nil {
		logger.Warn("summarize plan (terminal) failed", "error", err)
		return
	}
	if title != "" {
		job.Title = title
	}
	if summary != "" {
		job.Summary = summary
	}
}

func (c *Consumer) flushProgress(ctx context.Context, jobID string, buf *syncBuffer, planBuf *planTracker) {
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

	// Flush plan progress if available.
	if plan, step := planBuf.Get(); len(plan) > 0 {
		current.Plan = plan
		current.CurrentStep = step
	}

	if err := c.store.Put(ctx, current); err != nil {
		c.logger.Warn("failed to flush progress", "jobID", jobID, "error", err)
	}
}
