# Alert-Driven Patrol Agent Refactor

**Date:** 2026-03-08
**Status:** Approved
**Supersedes:** Patrol agent section of `2026-03-08-cluster-agents-design.md`

## Problem

The current patrol agent has three issues:

1. **Broken dedup** — fingerprints use colons (`patrol:pod:ns/name:OOMKilled`) which are invalid NATS KV key characters, so deduplication silently fails on every check
2. **Per-pod granularity** — fingerprints key on pod name (includes ReplicaSet hash + random suffix), so a 3-replica deployment OOMing generates 3 independent escalations for the same root cause
3. **Unnecessary LLM triage** — an in-cluster llama.cpp call classifies every finding into log/issue/job, but this triage adds cost and latency for a decision that SigNoz alerts already encode via severity thresholds

## Solution

Replace the collector + LLM triage pattern with an **alert-driven model**: poll SigNoz for firing alerts, dedup via GitHub PR labels, and submit one orchestrator job per alert.

## What Changes

| Component          | Current                                                         | New                                             |
| ------------------ | --------------------------------------------------------------- | ----------------------------------------------- |
| **Collectors**     | `K8sCollector`, `ArgoCDCollector` (custom K8s/ArgoCD API calls) | `AlertCollector` (SigNoz alerts API)            |
| **Analyze**        | LLM triage via llama.cpp                                        | Deterministic: firing alert → action            |
| **Dedup**          | NATS KV store (broken)                                          | GitHub PR label check + orchestrator job status |
| **Interval**       | 5 minutes                                                       | 1 hour                                          |
| **LLM dependency** | llama.cpp for triage                                            | None — removed from patrol entirely             |

## What Stays

- **`Agent` interface** — `Collect` → `Analyze` → `Execute` with `Name()` and `Interval()`
- **`Runner`** — manages concurrent agent loops, unchanged
- **Extensibility** — future agents (CI review, docs refresh, weekly tasks) plug into the same `Runner`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Loop Framework                   │
│                                                          │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐  │
│  │  Collect     │──▶│   Analyze    │──▶│   Execute    │  │
│  │  (per agent) │   │  (per agent) │   │  (per agent) │  │
│  └─────────────┘   └──────────────┘   └──────────────┘  │
│                                                          │
│  Agents: PatrolAgent, (future: CIReviewAgent, ...)       │
└─────────────────────────────────────────────────────────┘
```

### Patrol Agent — Alert-Driven

**Collect:** Poll SigNoz `/api/v1/rules` for alerts with state `firing`. For each firing alert, produce a `Finding` with:

- `Fingerprint`: `patrol.alert.<rule-id>` (dots, not colons — NATS-safe and human-readable)
- Alert name, severity, labels, firing duration, condition description

**Analyze:** Deterministic — every firing alert becomes an `ActionOrchestratorJob`. No LLM call needed. The severity classification already happened when the alert rule was authored.

**Execute (dedup flow):**

1. Open PR with label `alert:<rule-id>`? → skip
2. In-progress orchestrator job with source `patrol:<rule-id>`? → skip
3. Recently merged PR (< 1h) with label `alert:<rule-id>`? → skip (give the fix time to roll out)
4. None of the above → submit orchestrator job

**Job submission payload:**

```json
{
  "task": "SigNoz alert firing: <alert-name>\n\nRule ID: <id>\nSeverity: <severity>\nFiring since: <start-time>\nCondition: <condition-description>\nLabels: <labels>\n\nInvestigate using MCP tools. If a GitOps change can fix it, create a PR with label 'alert:<rule-id>'. If manual intervention is needed, create a GitHub issue.",
  "source": "patrol:<rule-id>",
  "profile": "code-fix"
}
```

The orchestrator runs Goose with Sonnet (`claude-sonnet-4-6`) — already configured globally in the sandbox template. Cost-appropriate for automated remediation.

### Edge Cases

| Scenario                          | Behavior                                                                                                                                 |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| PR merged but alert still firing  | Skip for 1h post-merge (rollout window). If still firing after, submit new job with context: "previous fix in PR #N didn't resolve this" |
| PR closed without merging         | No open PR → next cycle submits new job                                                                                                  |
| Job fails without creating PR     | No open PR, job status failed → next cycle submits new job                                                                               |
| Alert resolves then re-fires      | No open PR from previous cycle → new job                                                                                                 |
| No alerts configured for an issue | Not caught — but this is the right forcing function (if it matters, add an alert)                                                        |

## Files to Change

**Delete:**

- `collector_k8s.go`, `collector_k8s_test.go` — replaced by alert collector
- `collector_argocd.go`, `collector_argocd_test.go` — replaced by alert collector
- `llm.go`, `llm_test.go` — no more in-agent LLM calls
- `store_nats.go`, `store.go`, `store_test.go` — dedup moves to GitHub PR labels

**Modify:**

- `model.go` — keep `Agent`, `Finding`, `Action` interfaces; remove `FindingsStore` interface
- `escalator.go` — replace NATS dedup with GitHub PR label check + orchestrator job status check; remove `GitHubClient` issue creation (GitHub issues were a middle-ground action type we no longer need)
- `main.go` — remove NATS connection, LLM client, K8s client; add SigNoz client config
- `patrol.go` — simplify: alert collector → deterministic analyze → escalator

**Add:**

- `collector_alerts.go` — SigNoz alerts API poller
- `collector_alerts_test.go` — tests
- `github.go` — GitHub PR label querying (via REST API)
- `escalator_test.go` — update tests for new dedup logic

## Future Agents (Unchanged Pattern)

The refactored `Agent` interface supports all planned future agents:

| Agent            | Collect                     | Analyze            | Execute          | Interval |
| ---------------- | --------------------------- | ------------------ | ---------------- | -------- |
| **Patrol**       | SigNoz firing alerts        | Deterministic      | Orchestrator job | 1 hour   |
| **CI Review**    | GitHub PRs with CI failures | Deterministic      | Orchestrator job | 5 min    |
| **Docs Refresh** | Git diff of recent merges   | LLM (assess scope) | Orchestrator job | Weekly   |

Each agent decides independently whether its `Analyze` step needs an LLM or can be deterministic.

## Deployment Changes

- Remove NATS dependency from cluster-agents (no more KV bucket)
- Add SigNoz API URL + token to environment config
- Keep GitHub token (now used for PR label queries instead of issue creation)
- Update patrol interval to 1 hour
