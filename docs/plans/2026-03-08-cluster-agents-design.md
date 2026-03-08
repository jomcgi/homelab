# Cluster Agents: Autonomous Monitoring & Action Platform

**Date:** 2026-03-08
**Status:** Approved

## Problem

The homelab has excess compute (4090 GPU running llama.cpp, general cluster capacity) sitting idle. Meanwhile, cluster monitoring is purely reactive — SigNoz alerts fire on thresholds, but nobody is continuously exploring for anomalies, validating health, or correlating signals across systems.

## Goals

1. Use cheap local LLM compute for continuous cluster exploration and validation
2. Escalate actionable findings to Claude (via agent-orchestrator) for remediation
3. Build a reusable agent framework so new agents (e.g., PR reviewer) are trivial to add

## Non-Goals

- Replacing existing SigNoz alerting — this complements it
- Running Claude for routine checks — local models handle detection, Claude handles remediation
- Adaptive scheduling — fixed intervals to start

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Loop Framework                   │
│                                                          │
│  ┌────────────┐   ┌────────────┐   ┌─────────────────┐  │
│  │ Collector  │──▶│  Analyzer  │──▶│    Escalator    │  │
│  │ Interface  │   │ Interface  │   │    Interface    │  │
│  └────────────┘   └────────────┘   └─────────────────┘  │
│        │                │                   │            │
│  ┌─────┴──────┐   ┌─────┴──────┐   ┌───────┴────────┐  │
│  │ Data       │   │ LLM        │   │ Action         │  │
│  │ Sources    │   │ Backends   │   │ Handlers       │  │
│  │ (pluggable)│   │ (pluggable)│   │ (pluggable)    │  │
│  └────────────┘   └────────────┘   └────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Findings Store (NATS KV)             │   │
│  │  dedup · locking · TTL · fingerprinting           │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Core Abstractions

```go
type Agent interface {
    Name() string
    Collect(ctx context.Context) ([]Finding, error)
    Analyze(ctx context.Context, findings []Finding) ([]Action, error)
    Execute(ctx context.Context, actions []Action) error
    Interval() time.Duration
}

type Finding struct {
    Fingerprint string            // dedup key
    Source      string            // which collector
    Severity    Severity          // info | warning | critical
    Title       string
    Detail      string
    Data        map[string]any    // structured context for LLM
    Timestamp   time.Time
}

type Action struct {
    Type        ActionType        // log | github_issue | orchestrator_job | pr_review | pr_merge
    Finding     Finding
    Payload     map[string]any    // action-specific data
}
```

### Components

**Collectors** — pluggable data gatherers, each implementing a simple interface:

- `KubernetesCollector` — pod status, restart counts, resource usage, pending pods, node conditions, events
- `ArgoCDCollector` — app sync/health status, recent sync failures
- `SigNozCollector` — currently firing alerts, error rate spikes, log anomalies
- `CertificateCollector` — TLS secret expiry dates
- `GitHubCollector` — open PRs, CI status (for PR reviewer agent)

**Analyzer** — abstracted LLM client with backend routing:

- `llama.cpp` backend for local/cheap analysis (patrol, routine reviews)
- `Claude API` backend for complex remediation planning
- Structured output via JSON schema enforcement
- Each agent provides its own system prompt and output schema

**Escalator** — routes actions based on type:

- `LogHandler` — structured OTel log to SigNoz (info findings)
- `GitHubIssueHandler` — creates issue with dedup check (warning findings)
- `OrchestratorJobHandler` — submits Goose job with context (critical findings)
- `PRReviewHandler` — posts review comments, approves/requests changes
- `PRMergeHandler` — merges approved PRs

**Findings Store** — NATS KV bucket (`cluster-agents-findings`):

- Fingerprint-based deduplication via `ShouldEscalate`/`MarkEscalated`/`MarkResolved`
- TTL-based auto-expiry after resolution window (prevents stale dedup entries)

### Agent 1: Cluster Patrol

| Component      | Implementation                                                              |
| -------------- | --------------------------------------------------------------------------- |
| **Collectors** | KubernetesCollector, ArgoCDCollector, SigNozCollector, CertificateCollector |
| **Analyzer**   | llama.cpp — classifies findings, spots correlations across data sources     |
| **Escalation** | Info → log, Warning → GitHub Issue, Critical → Agent Orchestrator job       |
| **Interval**   | Every 5 minutes                                                             |

**Scripted checks (Collector layer):**

- Pods not Ready for > 5 minutes
- Containers with restart count > 3 in last hour
- Nodes with pressure conditions
- ArgoCD apps not Synced or not Healthy
- SigNoz alerts currently firing
- TLS certificates expiring within 14 days
- Pods without resource limits
- Resource usage > 80% of limits

**LLM analysis (Analyzer layer):**

- Correlate findings (restarts + memory pressure + recent deploy = likely OOM)
- Classify severity based on blast radius and urgency
- Generate actionable remediation context for Claude

### Agent 2: PR Reviewer (Future)

| Component      | Implementation                                           |
| -------------- | -------------------------------------------------------- |
| **Collectors** | GitHubCollector — open PRs matching criteria             |
| **Analyzer**   | llama.cpp (convention checks) or Claude (complex review) |
| **Escalation** | Approve + merge if passing, Request changes if not       |
| **Schedule**   | Every 2-3 minutes                                        |

### Deduplication & Locking

Each finding gets a fingerprint derived from its source + key attributes (e.g., `patrol:pod:namespace/name:CrashLoopBackOff`). Before escalation:

1. Check NATS KV for existing finding with same fingerprint
2. If exists and status is `escalated`, skip (already being handled)
3. If not exists, acquire lock (NATS KV create with revision check)
4. Execute escalation action
5. Update finding status to `escalated`
6. On resolution (agent-orchestrator job completes, issue closed), mark `resolved`

Findings auto-expire via NATS KV TTL (default: 24 hours) to prevent stale locks.

### Deployment

- Single binary: `services/cluster-agents/`
- Helm chart: `charts/cluster-agents/`
- Overlay: `overlays/prod/cluster-agents/`
- ServiceAccount with read-only ClusterRole for K8s API
- Network access: llama.cpp, ArgoCD API, SigNoz API, agent-orchestrator, GitHub API
- Credentials: 1Password items for GitHub token, SigNoz API key
- OTel auto-instrumented for observability of the agent itself

### Observability

Each agent emits OTel metrics:

- `cluster_agents.sweep.duration` — time per collection cycle
- `cluster_agents.findings.total` — findings per sweep by severity
- `cluster_agents.escalations.total` — escalations by type
- `cluster_agents.llm.duration` — LLM analysis latency
- `cluster_agents.llm.tokens` — token usage per analysis

Structured logs for each finding and escalation decision, queryable in SigNoz.

## Adding a New Agent

1. Implement the `Agent` interface
2. Register collectors from the shared pool (or write new ones)
3. Define analyzer prompt + output schema
4. Configure escalation rules
5. Register in main.go with a schedule
6. Deploy — same binary, no new infrastructure needed
