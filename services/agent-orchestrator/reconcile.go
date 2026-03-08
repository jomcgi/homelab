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

// reconcileOrphanedJobs scans the KV store for jobs stuck in RUNNING state
// and resets them for retry. This handles the case where the orchestrator
// restarts while jobs are in-flight: the SPDY exec connection is lost,
// the sandbox claim is orphaned, and the NATS message sits unACKed until
// AckWait expires (168h by default).
//
// For each orphaned job, this function:
//  1. Cleans up the stale SandboxClaim (if it still exists)
//  2. Resets the job to PENDING
//  3. Re-publishes the job ID to the NATS stream for redelivery
func reconcileOrphanedJobs(ctx context.Context, store Store, publish func(string) error, dynClient dynamic.Interface, namespace string, logger *slog.Logger) {
	jobs, _, err := store.List(ctx, []string{string(JobRunning)}, 100, 0)
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

		jlog.Info("reconcile: resetting to pending for retry", "retriesRemaining", retriesRemaining)
		job.Status = JobPending
		if err := store.Put(ctx, &job); err != nil {
			jlog.Error("reconcile: failed to reset job", "error", err)
			continue
		}

		if err := publish(job.ID); err != nil {
			jlog.Error("reconcile: failed to re-publish job", "error", err)
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
