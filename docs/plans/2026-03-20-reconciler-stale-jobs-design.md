# Reconciler: Force-fail stale RUNNING jobs

**Date:** 2026-03-20
**Status:** Approved

## Problem

Jobs whose goose process is killed by the inactivity timeout (or any other
reason) can get stuck in RUNNING status permanently. The reconciler runs every
60s and checks runner health, but when the runner reports "running" (e.g. after
an orchestrator restart with a stale pod) or the consumer fails to persist the
final status update, the job stays RUNNING with no one watching it.

The UI shows these zombie jobs with a "Cancel" button and an amber dot, even
though the output already contains `--- killed: inactivity timeout ---`.

## Solution

Pass `maxDuration` (currently `JOB_MAX_DURATION`, default 168h) into the
reconciler. Before checking the runner, if the latest attempt started more than
`maxDuration` ago, force the job to `FAILED` immediately — skip runner checks,
clean up the sandbox claim, mark the attempt as finished.

## Changes

### `reconcile.go`

- Add `maxDuration time.Duration` parameter to `reconcileOrphanedJobs`.
- After the 2-minute grace period check, add a staleness check:
  if `time.Since(lastAttempt.StartedAt) > maxDuration`, force-fail the job,
  clean up the sandbox claim, and continue.

### `main.go`

- Thread `maxDuration` through to both `reconcileOrphanedJobs()` calls and
  `runPeriodicReconcile()`.

### `reconcile_test.go`

- Add test: RUNNING job with attempt older than maxDuration gets force-failed.
- Verify runner is NOT checked (skip unnecessary HTTP calls for expired jobs).

## Behavior matrix

| Scenario                                | Before                   | After  |
| --------------------------------------- | ------------------------ | ------ |
| Job running > maxDuration, runner alive | RUNNING forever          | FAILED |
| Job running > maxDuration, runner gone  | RUNNING forever          | FAILED |
| Job running < maxDuration, runner alive | RUNNING (correct)        | Same   |
| Job running < maxDuration, runner gone  | PENDING/FAILED (correct) | Same   |
