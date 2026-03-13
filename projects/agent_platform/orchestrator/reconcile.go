package main

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/dynamic"
)

// RunnerStatusFunc checks the status of a runner for the given sandbox claim name.
// Returns state ("idle", "running", "done", "failed") and exit code.
// Returns error if the runner is unreachable or the claim can't be resolved.
type RunnerStatusFunc func(ctx context.Context, sandboxClaimName string) (state string, exitCode int, err error)

// RunnerOutputFunc fetches the full output from a runner for the given sandbox claim name.
// Returns the raw output string. Used by the reconciler to capture output from
// runners that finished while the orchestrator was down.
type RunnerOutputFunc func(ctx context.Context, sandboxClaimName string) (output string, err error)

// reconcileOrphanedJobs scans the KV store for jobs stuck in RUNNING state
// and reconciles them. With the HTTP runner, goose may still be executing
// after an orchestrator restart, so we check the runner's status before
// blindly resetting jobs.
//
// For each RUNNING job:
//  1. If checkRunner is provided and the runner is still active:
//     - "running" → leave as RUNNING (consumer will re-attach)
//     - "done"    → mark SUCCEEDED, fetch output, clean up sandbox
//     - "failed"  → mark attempt failed, fetch output, fall through to retry logic
//  2. If checkRunner is nil, returns error, or returns "idle":
//     - Clean up stale SandboxClaim
//     - Reset to PENDING for retry (or FAILED if retries exhausted)
//     - NATS redelivers the message automatically after AckWait expires
func reconcileOrphanedJobs(ctx context.Context, store Store, dynClient dynamic.Interface, namespace string, checkRunner RunnerStatusFunc, fetchOutput RunnerOutputFunc, logger *slog.Logger) {
	jobs, _, err := store.List(ctx, []string{string(JobRunning)}, nil, 100, 0)
	if err != nil {
		logger.Error("reconcile: failed to list running jobs", "error", err)
		return
	}

	if len(jobs) == 0 {
		logger.Info("reconcile: no orphaned jobs found")
		return
	}

	logger.Info("reconcile: found orphaned running jobs", "count", len(jobs))

	for _, job := range jobs {
		jlog := logger.With("jobID", job.ID)

		// With HTTP runner, check if goose is still running before resetting.
		if checkRunner != nil && len(job.Attempts) > 0 {
			lastAttempt := job.Attempts[len(job.Attempts)-1]
			if lastAttempt.SandboxClaimName != "" {
				state, exitCode, err := checkRunner(ctx, lastAttempt.SandboxClaimName)
				if err == nil {
					switch state {
					case "running":
						jlog.Info("reconcile: goose still running, will re-attach")
						if err := store.Put(ctx, &job); err != nil {
							jlog.Error("reconcile: failed to update job", "error", err)
						}
						continue
					case "done":
						jlog.Info("reconcile: goose finished successfully", "exitCode", exitCode)
						now := time.Now().UTC()
						last := &job.Attempts[len(job.Attempts)-1]
						last.FinishedAt = &now
						last.ExitCode = &exitCode
						// Fetch output from the runner before it's cleaned up.
						if fetchOutput != nil {
							if output, err := fetchOutput(ctx, lastAttempt.SandboxClaimName); err == nil && output != "" {
								if len(output) > maxOutputBytes {
									output = output[len(output)-maxOutputBytes:]
									last.Truncated = true
								}
								output = cleanOutput(output)
								last.Output = output
								last.Result = parseGooseResult(output)
							} else if err != nil {
								jlog.Warn("reconcile: failed to fetch output from runner", "error", err)
							}
						}
						job.Status = JobSucceeded
						if err := store.Put(ctx, &job); err != nil {
							jlog.Error("reconcile: failed to update job", "error", err)
						}
						// Clean up the sandbox claim now that we have the output.
						cleanupSandboxClaim(ctx, dynClient, namespace, lastAttempt.SandboxClaimName, jlog)
						continue
					case "failed":
						jlog.Info("reconcile: goose failed", "exitCode", exitCode)
						now := time.Now().UTC()
						last := &job.Attempts[len(job.Attempts)-1]
						last.FinishedAt = &now
						last.ExitCode = &exitCode
						// Fetch output from the runner before cleanup.
						if fetchOutput != nil {
							if output, err := fetchOutput(ctx, lastAttempt.SandboxClaimName); err == nil && output != "" {
								if len(output) > maxOutputBytes {
									output = output[len(output)-maxOutputBytes:]
									last.Truncated = true
								}
								output = cleanOutput(output)
								last.Output = output
								last.Result = parseGooseResult(output)
							} else if err != nil {
								jlog.Warn("reconcile: failed to fetch output from runner", "error", err)
							}
						}
						// Fall through to existing retry logic below.
					default:
						// "idle" or unknown state: fall through to reset.
						jlog.Info("reconcile: runner idle or unknown state, will reset", "state", state)
					}
				} else {
					jlog.Info("reconcile: runner unreachable, will reset", "error", err)
				}
			}
		}

		// Clean up stale sandbox claim from the last attempt.
		if len(job.Attempts) > 0 {
			lastAttempt := job.Attempts[len(job.Attempts)-1]
			if lastAttempt.SandboxClaimName != "" {
				cleanupSandboxClaim(ctx, dynClient, namespace, lastAttempt.SandboxClaimName, jlog)
			}
		}

		// Mark the interrupted attempt as failed.
		if len(job.Attempts) > 0 {
			now := time.Now().UTC()
			last := &job.Attempts[len(job.Attempts)-1]
			if last.FinishedAt == nil {
				last.FinishedAt = &now
				exitCode := -1
				last.ExitCode = &exitCode
				last.Output = appendOutput(last.Output, "[orchestrator restarted - execution interrupted]")
			}
		}

		retriesRemaining := job.MaxRetries - len(job.Attempts)
		if retriesRemaining <= 0 {
			jlog.Info("reconcile: no retries remaining, marking failed")
			job.Status = JobFailed
			if err := store.Put(ctx, &job); err != nil {
				jlog.Error("reconcile: failed to update job to failed", "error", err)
			}
			continue
		}

		// Reset to PENDING so the consumer retries when NATS redelivers the
		// message after AckWait expires. No need to re-publish — NATS handles
		// redelivery natively, and re-publishing would create duplicates.
		jlog.Info("reconcile: resetting to pending for retry", "retriesRemaining", retriesRemaining)
		job.Status = JobPending
		if err := store.Put(ctx, &job); err != nil {
			jlog.Error("reconcile: failed to reset job", "error", err)
			continue
		}
	}
}

func cleanupSandboxClaim(ctx context.Context, dynClient dynamic.Interface, namespace, claimName string, logger *slog.Logger) {
	if dynClient == nil {
		return
	}
	err := dynClient.Resource(sandboxClaimGVR).Namespace(namespace).Delete(
		ctx, claimName, metav1.DeleteOptions{})
	if err != nil {
		if !apierrors.IsNotFound(err) {
			logger.Warn("reconcile: failed to delete sandbox claim", "claim", claimName, "error", err)
		}
		return
	}
	logger.Info("reconcile: deleted orphaned sandbox claim", "claim", claimName)
}

func appendOutput(existing, suffix string) string {
	if existing == "" {
		return suffix
	}
	return fmt.Sprintf("%s\n%s", existing, suffix)
}
