# ADR 008: Cluster Patrol Loop Resilience

**Author:** goose (automated investigation)
**Status:** Accepted
**Created:** 2026-03-09
**Relates to:** [007-agent-orchestrator](007-agent-orchestrator.md)

---

## Problem

### Incident Summary

The `cluster-agents` patrol loop stopped scheduling sweeps after approximately 3
successful hourly runs. The pod remained healthy (3/3 Running, HTTP health checks
passing) but no patrol activity occurred for several hours.

**Timeline:**

| Time (UTC) | Event                                                    |
| ---------- | -------------------------------------------------------- |
| 23:07      | Sweep 1 — completed successfully                         |
| 00:07      | Sweep 2 — completed successfully                         |
| 01:07:00   | Sweep 3 — started                                        |
| 01:07:40   | Sweep 3 — "sweep complete" logged (last log entry ever)  |
| 02:07+     | **No sweep scheduled. No logs. No errors. No restarts.** |

### Observed Symptoms

- No log entries after `01:07:40 UTC` (not even error logs)
- Pod `cluster-agents-66c7d5f67d-dkjqx`: status `3/3 Running`, 145m uptime, 0 restarts
- HTTP server responding on port 8080 (health checks passing)
- `kubectl top` showed the pod alive with normal resource usage

### Why the Symptoms Are Misleading

The goroutine did **not** exit — it cannot exit silently. The `runAgent` loop has
two exit paths, both of which produce log output:

```go
case <-ctx.Done():
    slog.Info("agent loop stopping", ...)  // always logged
    return
```

And a panic without `recover()` would have crashed the process, restarting the pod.

The actual state: the goroutine is **alive but permanently blocked** inside a
`sweep` call that started at ~02:07 UTC and has not returned.

---

## Root Cause

### Primary: No Per-Sweep Execution Deadline

`runner.sweep` passed the main program context (created by `signal.NotifyContext`)
directly to every agent method — `Collect`, `Analyze`, and `Execute`:

```go
// BEFORE (vulnerable)
func (r *Runner) sweep(ctx context.Context, agent Agent) {
    findings, err := agent.Collect(ctx)   // ctx has NO deadline
    ...
}
```

That main context has **no deadline**. It is only cancelled on SIGINT/SIGTERM.

`AlertCollector.Collect` makes an HTTP GET to SigNoz. The `http.Client` carries a
30-second `Timeout`, which protects against individual slow responses under normal
conditions. However, the 30-second timeout is reset on each new request. If the
underlying TCP connection entered a **half-open state** (established at the kernel
level, but the remote end stopped sending data — e.g. due to a firewall silently
dropping packets, a SigNoz pod rolling restart that killed the connection mid-stream,
or a network partition), `http.Client.Timeout` may not reliably fire because the
OS does not signal the broken connection immediately.

The result: `client.Do(req)` blocks indefinitely. The goroutine is stuck. The
`time.Ticker` fires the 02:07, 03:07, 04:07 ticks — but no goroutine is available
to read from `ticker.C`, so the ticks are dropped (the channel buffer holds only
one). Patrol coverage silently stops.

### Secondary: No Panic Recovery in Sweep

There is no `recover()` in the sweep call chain. Any nil-pointer dereference,
slice-out-of-bounds, or other runtime panic in an agent method would crash the
entire `cluster-agents` process. This is not the cause of the current incident
(the pod did not restart), but is a latent risk for future regressions.

### Secondary: No Loop Supervision

If `runAgent` were to return unexpectedly (e.g. due to a future code change
introducing an early-return path), the goroutine exits silently and patrol stops.
There is no watchdog to detect and restart it.

---

## Fix

Three changes to `services/cluster-agents/runner.go`:

### 1. Per-Sweep Timeout Context

```go
const defaultSweepTimeout = 5 * time.Minute

func (r *Runner) sweep(ctx context.Context, agent Agent) {
    sweepCtx, cancel := context.WithTimeout(ctx, r.sweepTimeout)
    defer cancel()

    findings, err := agent.Collect(sweepCtx)   // bounded
    ...
}
```

Each sweep now receives a fresh child context with a 5-minute deadline. If any
HTTP call stalls (half-open connection, SigNoz restart, etc.), the context times
out, `Collect` returns `context.DeadlineExceeded`, `sweep` logs "collect failed",
and **returns**. The goroutine is free to pick up the next ticker event.

The 5-minute timeout is chosen to be:

- Long enough for a sweep with dozens of firing alerts and many orchestrator
  HTTP round-trips to complete comfortably
- Short enough that the patrol loop misses at most one interval (1 hour) before
  recovering

### 2. Panic Recovery

```go
defer func() {
    if rec := recover(); rec != nil {
        slog.Error("sweep panicked — loop will continue",
            "agent", agent.Name(),
            "panic", fmt.Sprintf("%v", rec),
            "stack", string(debug.Stack()),
        )
    }
}()
```

A panic in any agent method is caught, logged with a full stack trace, and the
sweep returns. The loop continues running. The panic is **not silenced** — it is
fully logged so the root cause can be investigated.

### 3. Loop Supervision (Restart on Unexpected Exit)

```go
func (r *Runner) Run(ctx context.Context) {
    for _, agent := range r.agents {
        wg.Add(1)
        go func(a Agent) {
            defer wg.Done()
            for ctx.Err() == nil {
                r.runAgent(ctx, a)
                if ctx.Err() != nil {
                    return
                }
                slog.Warn("agent loop exited unexpectedly, restarting", ...)
                // 5-second back-off before restart
            }
        }(agent)
    }
}
```

If `runAgent` returns without `ctx` being cancelled, it is treated as an
unexpected exit and the loop is restarted after a 5-second back-off. This guards
against future code changes that might inadvertently add early returns to `runAgent`.

---

## Test Coverage

Two regression tests added to `runner_test.go`:

| Test                                   | What it verifies                                                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `TestRunnerContinuesAfterSweepPanic`   | A panic in `Collect` is recovered; subsequent sweeps continue                                                      |
| `TestRunnerContinuesAfterSweepTimeout` | A blocking `Collect` (simulating a hung HTTP call) is bounded by `sweepTimeout`; the loop resumes on the next tick |

The second test directly reproduces the production failure: the `blockingAgent`
blocks in `Collect` until its context is cancelled, simulating an HTTP call that
never times out.

---

## Prevention Strategy

**For this service specifically:**

- All HTTP calls in agent implementations must use the context passed to them
  (already done). Do not make new `http.Client` calls without a context.
- Agent `Collect`/`Execute` implementations should not block on channels, locks,
  or non-contextual I/O.

**For future agents added to `cluster-agents`:**

- The `Runner.sweep` timeout is the last line of defence — do not rely solely on
  it. Agent implementations should set appropriate deadlines on their own I/O
  operations.
- Test agent implementations with `TestRunnerContinuesAfterSweepTimeout` as a
  pattern: write a test that blocks the agent and verify the loop recovers.

**For any long-running goroutine loop:**

- Always wrap blocking operations with a bounded context.
- Always add panic recovery to goroutines that must stay alive.
- Consider a supervision/restart pattern for critical background loops.

---

## Alternatives Considered

| Alternative                                  | Why not chosen                                                                                         |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Increase `http.Client.Timeout`               | Does not help with half-open TCP connections; the OS may not surface the broken connection for minutes |
| Add TCP keepalive to HTTP transport          | Helps but adds complexity; does not protect against all network-layer hangs                            |
| Restart the pod on schedule (liveness probe) | Blunt instrument; loses in-flight state and adds unnecessary pod churn                                 |
| Per-agent configurable sweep timeout         | Over-engineering for now; `defaultSweepTimeout = 5m` suits all current and foreseeable agents          |
