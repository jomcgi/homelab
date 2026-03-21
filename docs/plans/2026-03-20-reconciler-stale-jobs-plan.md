# Reconciler Stale Jobs Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Force-fail RUNNING jobs that have exceeded `maxDuration`, preventing zombie jobs that are stuck forever.

**Architecture:** Add `maxDuration` parameter to `reconcileOrphanedJobs`. Before checking the runner, if the latest attempt exceeds `maxDuration`, force the job to FAILED — skip runner checks, clean up sandbox claim, done.

**Tech Stack:** Go, NATS JetStream KV, Kubernetes dynamic client

---

### Task 1: Write failing test for stale job force-fail

**Files:**

- Modify: `projects/agent_platform/orchestrator/reconcile_test.go`

**Step 1: Write the failing test**

Add at the end of `reconcile_test.go`:

```go
func TestReconcileOrphanedJobs_StaleJobForceFailed(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	maxDuration := 2 * time.Hour

	// Job whose attempt started 3 hours ago — exceeds maxDuration.
	store.Put(ctx, &JobRecord{
		ID:         "job-stale",
		Task:       "stale task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-3 * time.Hour),
		MaxRetries: 3, // retries remaining, but staleness overrides
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-stale-1",
			StartedAt:        time.Now().Add(-3 * time.Hour),
		}},
	})

	// Runner reports "running" — without the fix, the reconciler would
	// leave this job as RUNNING forever.
	runnerCalled := false
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		runnerCalled = true
		return "running", 0, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, maxDuration, slog.Default())

	job, err := store.Get(ctx, "job-stale")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobFailed {
		t.Errorf("status = %s, want FAILED (exceeded maxDuration)", job.Status)
	}
	last := job.Attempts[len(job.Attempts)-1]
	if last.FinishedAt == nil {
		t.Error("FinishedAt should be set for force-failed job")
	}
	if last.ExitCode == nil || *last.ExitCode != -1 {
		t.Errorf("exit code = %v, want -1", last.ExitCode)
	}
	if runnerCalled {
		t.Error("runner should NOT be checked for stale jobs (skip unnecessary HTTP calls)")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/reconciler-stale-jobs && go vet ./projects/agent_platform/orchestrator/...`
Expected: compilation error — `reconcileOrphanedJobs` has wrong number of arguments.

### Task 2: Write test for non-stale job still checks runner

**Files:**

- Modify: `projects/agent_platform/orchestrator/reconcile_test.go`

**Step 1: Write the test**

Add after the previous test:

```go
func TestReconcileOrphanedJobs_NonStaleJobStillChecksRunner(t *testing.T) {
	store := newMemStore()
	ctx := context.Background()

	maxDuration := 4 * time.Hour

	// Job running for 1 hour — well within maxDuration.
	store.Put(ctx, &JobRecord{
		ID:         "job-not-stale",
		Task:       "active task",
		Status:     JobRunning,
		CreatedAt:  time.Now().Add(-1 * time.Hour),
		MaxRetries: 2,
		Attempts: []Attempt{{
			Number:           1,
			SandboxClaimName: "orch-job-not-stale-1",
			StartedAt:        time.Now().Add(-1 * time.Hour),
		}},
	})

	// Runner reports "running" — job should stay RUNNING.
	checkRunner := func(_ context.Context, claimName string) (string, int, error) {
		return "running", 0, nil
	}

	reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", checkRunner, nil, maxDuration, slog.Default())

	job, err := store.Get(ctx, "job-not-stale")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if job.Status != JobRunning {
		t.Errorf("status = %s, want RUNNING (within maxDuration, runner alive)", job.Status)
	}
}
```

### Task 3: Update `reconcileOrphanedJobs` signature and add staleness check

**Files:**

- Modify: `projects/agent_platform/orchestrator/reconcile.go`

**Step 1: Update function signature**

Change line 38 from:

```go
func reconcileOrphanedJobs(ctx context.Context, store Store, dynClient dynamic.Interface, namespace string, checkRunner RunnerStatusFunc, fetchOutput RunnerOutputFunc, logger *slog.Logger) {
```

to:

```go
func reconcileOrphanedJobs(ctx context.Context, store Store, dynClient dynamic.Interface, namespace string, checkRunner RunnerStatusFunc, fetchOutput RunnerOutputFunc, maxDuration time.Duration, logger *slog.Logger) {
```

**Step 2: Add staleness check after the 2-minute grace period**

After the grace period block (line 66), add:

```go
		// Force-fail jobs that have exceeded the maximum allowed runtime.
		// This catches zombie jobs where the runner finished (or died) but
		// the status was never updated — regardless of what the runner
		// reports, a job past maxDuration is done.
		if maxDuration > 0 && len(job.Attempts) > 0 {
			lastAttempt := job.Attempts[len(job.Attempts)-1]
			if time.Since(lastAttempt.StartedAt) > maxDuration {
				jlog.Info("reconcile: job exceeded max duration, force-failing",
					"startedAt", lastAttempt.StartedAt,
					"maxDuration", maxDuration)
				now := time.Now().UTC()
				last := &job.Attempts[len(job.Attempts)-1]
				if last.FinishedAt == nil {
					last.FinishedAt = &now
					exitCode := -1
					last.ExitCode = &exitCode
					last.Output = appendOutput(last.Output, fmt.Sprintf("[exceeded max duration (%s)]", maxDuration))
				}
				if lastAttempt.SandboxClaimName != "" {
					cleanupSandboxClaim(ctx, dynClient, namespace, lastAttempt.SandboxClaimName, jlog)
				}
				job.Status = JobFailed
				if err := store.Put(ctx, &job); err != nil {
					jlog.Error("reconcile: failed to force-fail stale job", "error", err)
				}
				continue
			}
		}
```

### Task 4: Update all existing callers and tests

**Files:**

- Modify: `projects/agent_platform/orchestrator/main.go`
- Modify: `projects/agent_platform/orchestrator/reconcile_test.go`
- Modify: `projects/agent_platform/orchestrator/reconcile_helpers_test.go`

**Step 1: Update `main.go`**

Line 138 — startup reconciliation call, add `maxDuration` before `logger`:

```go
reconcileOrphanedJobs(ctx, store, sandbox.dynClient, sandboxNamespace, sandbox.CheckRunnerForClaim, sandbox.FetchOutputForClaim, maxDuration, logger)
```

Line 139 — pass `maxDuration` to `runPeriodicReconcile`:

```go
go runPeriodicReconcile(ctx, reconcileInterval, store, sandbox, sandboxNamespace, maxDuration, logger)
```

Update `runPeriodicReconcile` signature (around line 248) to accept `maxDuration time.Duration` and pass it through:

```go
func runPeriodicReconcile(ctx context.Context, interval time.Duration, store Store, sandbox *SandboxExecutor, namespace string, maxDuration time.Duration, logger *slog.Logger) {
```

And its internal call (around line 258):

```go
reconcileOrphanedJobs(ctx, store, sandbox.dynClient, namespace, sandbox.CheckRunnerForClaim, sandbox.FetchOutputForClaim, maxDuration, logger)
```

**Step 2: Update all existing test calls**

Every call to `reconcileOrphanedJobs` in the test files needs `maxDuration` added before `slog.Default()`. Use `0` (which disables the staleness check due to `maxDuration > 0` guard) to preserve existing test behavior without changing assertions.

In `reconcile_test.go`, replace all occurrences of the pattern:

```go
reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", ..., slog.Default())
```

with the same but inserting `0,` before `slog.Default()`. For example:

```go
reconcileOrphanedJobs(ctx, store, nil, "goose-sandboxes", nil, nil, 0, slog.Default())
```

Same for `reconcile_helpers_test.go`.

**Step 3: Run tests to verify everything passes**

Run: `cd /tmp/claude-worktrees/reconciler-stale-jobs && go test ./projects/agent_platform/orchestrator/... -run TestReconcile -v -count=1`
Expected: all tests PASS including the two new ones.

### Task 5: Run full test suite and commit

**Step 1: Run go vet**

Run: `cd /tmp/claude-worktrees/reconciler-stale-jobs && go vet ./projects/agent_platform/orchestrator/...`
Expected: clean

**Step 2: Run all orchestrator tests**

Run: `cd /tmp/claude-worktrees/reconciler-stale-jobs && go test ./projects/agent_platform/orchestrator/... -count=1`
Expected: all PASS

**Step 3: Commit**

```bash
cd /tmp/claude-worktrees/reconciler-stale-jobs
git add projects/agent_platform/orchestrator/reconcile.go projects/agent_platform/orchestrator/reconcile_test.go projects/agent_platform/orchestrator/reconcile_helpers_test.go projects/agent_platform/orchestrator/main.go
git commit -m "fix(orchestrator): force-fail jobs exceeding max duration in reconciler

Jobs that exceeded JOB_MAX_DURATION could stay stuck in RUNNING status
forever when the runner pod died or the orchestrator restarted. The
reconciler now checks attempt age against maxDuration and force-fails
stale jobs before checking the runner, preventing zombie jobs."
```

### Task 6: Push and create PR

**Step 1: Push branch**

```bash
cd /tmp/claude-worktrees/reconciler-stale-jobs
git push -u origin fix/reconciler-stale-jobs
```

**Step 2: Create PR**

```bash
gh pr create --title "fix(orchestrator): force-fail stale RUNNING jobs in reconciler" --body "$(cat <<'EOF'
## Summary

- Adds `maxDuration` parameter to the reconciler's `reconcileOrphanedJobs`
- Jobs whose latest attempt exceeds `maxDuration` are force-failed immediately, skipping runner HTTP checks
- Prevents zombie jobs that stay RUNNING forever after inactivity timeout kills goose

## Context

Jobs killed by the inactivity timeout (10m) could remain stuck as RUNNING
when the consumer failed to persist the final status update or the orchestrator
restarted. The periodic reconciler (60s interval) checks runner health but had
no concept of maximum job lifetime — if the runner reported "running" or was
unreachable at just the wrong time, the job stayed RUNNING indefinitely.

## Test plan

- [ ] New test: stale job (attempt > maxDuration) is force-failed even if runner reports "running"
- [ ] New test: non-stale job (attempt < maxDuration) still checks runner normally
- [ ] All existing reconciler tests pass with maxDuration=0 (disabled)
- [ ] CI passes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
