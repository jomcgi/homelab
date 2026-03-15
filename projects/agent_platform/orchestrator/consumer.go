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
	Run(ctx context.Context, claimName, task, recipePath string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error)
}

// Consumer pulls jobs from a NATS JetStream consumer and executes them in sandboxes.
type Consumer struct {
	cons        jetstream.Consumer
	store       Store
	sandbox     Sandbox
	publish     func(jobID string) error
	maxDuration time.Duration
	recipePaths map[string]string
	logger      *slog.Logger
}

// NewConsumer creates a Consumer that processes jobs from the given JetStream consumer.
func NewConsumer(cons jetstream.Consumer, store Store, sandbox Sandbox, publish func(jobID string) error, maxDuration time.Duration, recipePaths map[string]string, logger *slog.Logger) *Consumer {
	return &Consumer{
		cons:        cons,
		store:       store,
		sandbox:     sandbox,
		publish:     publish,
		maxDuration: maxDuration,
		recipePaths: recipePaths,
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

	// Look up recipe path for this agent.
	recipePath := ""
	if job.Profile != "" && c.recipePaths != nil {
		recipePath = c.recipePaths[job.Profile]
	}

	// Run sandbox in a goroutine so we can flush output periodically.
	type sandboxResult struct {
		result *ExecResult
		err    error
	}
	resultCh := make(chan sandboxResult, 1)
	go func() {
		r, err := c.sandbox.Run(jobCtx, claimName, task, recipePath, cancelFn, outputBuf)
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
		c.advancePipeline(jobCtx, job)
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
		c.advancePipeline(jobCtx, job)
		_ = msg.Ack()
		return
	}

	logger.Info("task succeeded", "attempt", attemptNum)
	job.Status = JobSucceeded
	if err := c.store.Put(jobCtx, job); err != nil {
		logger.Error("failed to store succeeded state", "error", err)
	}
	c.advancePipeline(jobCtx, job)
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

// advancePipeline evaluates the next step in a pipeline and either unblocks it,
// skips it (and cascades), or does nothing if the pipeline is complete.
func (c *Consumer) advancePipeline(ctx context.Context, completed *JobRecord) {
	if completed.PipelineID == "" {
		return
	}

	logger := c.logger.With("pipelineID", completed.PipelineID, "completedStep", completed.StepIndex)

	pipelineJobs, err := c.store.ListByPipeline(ctx, completed.PipelineID)
	if err != nil {
		logger.Error("failed to list pipeline jobs", "error", err)
		return
	}

	// Find the next step.
	var next *JobRecord
	for i := range pipelineJobs {
		if pipelineJobs[i].StepIndex == completed.StepIndex+1 {
			next = &pipelineJobs[i]
			break
		}
	}
	if next == nil {
		logger.Info("pipeline complete, no more steps")
		return
	}

	if next.Status != JobBlocked {
		logger.Info("next step not blocked, skipping advance", "nextStatus", next.Status)
		return
	}

	// Evaluate condition.
	conditionMet := false
	switch next.StepCondition {
	case "always":
		conditionMet = true
	case "on success":
		conditionMet = completed.Status == JobSucceeded
	case "on failure":
		conditionMet = completed.Status == JobFailed
	default:
		conditionMet = true // Default to always.
	}

	if !conditionMet {
		logger.Info("condition not met, skipping step", "condition", next.StepCondition, "predecessorStatus", completed.Status)
		next.Status = JobSkipped
		if err := c.store.Put(ctx, next); err != nil {
			logger.Error("failed to skip step", "error", err)
		}
		// Cascade: skip all remaining BLOCKED steps.
		c.cascadeSkip(ctx, pipelineJobs, next.StepIndex)
		return
	}

	// Prepend predecessor context to next step's task.
	next.Task = c.buildStepContext(completed, next.Task)
	next.Status = JobPending
	if err := c.store.Put(ctx, next); err != nil {
		logger.Error("failed to unblock step", "error", err)
		return
	}

	// Publish to NATS for dispatch.
	if c.publish != nil {
		if err := c.publish(next.ID); err != nil {
			logger.Error("failed to publish next step", "error", err)
		}
	}

	logger.Info("advanced pipeline to next step", "nextStep", next.StepIndex, "nextAgent", next.Profile)
}

// cascadeSkip marks all BLOCKED steps after the given index as SKIPPED.
func (c *Consumer) cascadeSkip(ctx context.Context, jobs []JobRecord, afterIndex int) {
	for i := range jobs {
		if jobs[i].StepIndex > afterIndex && jobs[i].Status == JobBlocked {
			jobs[i].Status = JobSkipped
			if err := c.store.Put(ctx, &jobs[i]); err != nil {
				c.logger.Error("failed to cascade skip", "jobID", jobs[i].ID, "error", err)
			}
		}
	}
}

// buildStepContext prepends predecessor output to the next step's task.
func (c *Consumer) buildStepContext(pred *JobRecord, task string) string {
	if len(pred.Attempts) == 0 {
		return task
	}

	lastAttempt := pred.Attempts[len(pred.Attempts)-1]
	output := lastAttempt.Output
	if len(output) > 2000 {
		output = output[len(output)-2000:]
	}

	var resultCtx string
	if lastAttempt.Result != nil {
		resultCtx = fmt.Sprintf("\nResult: type=%s url=%s summary=%s", lastAttempt.Result.Type, lastAttempt.Result.URL, lastAttempt.Result.Summary)
	}

	return fmt.Sprintf("Previous step (agent: %s, status: %s) output:\n---\n%s%s\n---\n\nYour task:\n%s", pred.Profile, string(pred.Status), output, resultCtx, task)
}
