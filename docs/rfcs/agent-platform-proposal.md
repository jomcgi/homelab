# Internal Agent Platform Proposal

**Status:** Proposal
**Date:** 2026-03-09
**Audience:** Engineering Leadership

---

## The Problem

Every team that wants to run an agent today faces the same cold-start problem: figure out where
to run it, how to give it access to the right tools, how to keep it isolated, and how to know
what it did. Most teams don't get past step one.

The result is predictable. Agents remain a personal productivity tool for the handful of
engineers who have already figured out the plumbing. Everyone else — AppSec, Data, Finance,
GTM, Product — either waits for Engineering to build them something or doesn't use agents at
all. Neither outcome is acceptable when the cost of not deploying agents is measured in
engineering cycles per week.

The missing piece isn't a model or a framework. It's **shared infrastructure**: a place any
team can submit an agentic task, trust it will run in an isolated environment with access to
the right tools, and get a traceable result back.

---

## The Proposal

Build an **internal agent platform** — a Kubernetes-native job queue backed by a pool of
sandboxed AI agent pods, exposed as an MCP server so any AI tool or human can submit and track
jobs without writing any integration code.

The platform handles:

- **Scheduling** — durable job queue with at-least-once delivery and configurable concurrency
- **Isolation** — each job runs in a fresh, resource-constrained pod, deleted on completion
- **Tool access** — agents connect to MCP servers (Snowflake, Kubernetes, ArgoCD, SigNoz,
  GitHub, CI) via a single authenticated gateway
- **Auditability** — every job has a full execution trace: prompt, output, exit code, retry
  history, and OpenTelemetry spans
- **Profiles** — scoped tool sets per task type, so a finance agent can't accidentally touch
  cluster infra

This isn't a greenfield project. A production-grade prototype is already running in the
homelab cluster. The delta to org-ready is well-defined.

---

## Why MCP as the Interface

The choice of interface matters. A REST API would work, but it would also require every team
to write a client, learn the schema, and build their own tooling around it. That's the
integration tax that keeps platforms underused.

MCP changes the equation. When the orchestrator exposes itself as an MCP server — with tools
like `submit_job`, `get_job_output`, and `list_jobs` — any MCP-compatible client can use it
immediately:

- Claude.ai web chat
- Claude Code
- Cursor
- Any custom agent that speaks MCP

A security engineer can ask Claude to "run a dependency audit across all services and file
issues for anything critical" and get back a job ID. A data analyst can trigger a Snowflake
pipeline reconciliation job conversationally. A product manager can schedule a weekly
changelog summarizer. No CLI, no API tokens, no custom tooling.

This is "make something agents want" applied to internal infrastructure. When the platform is
accessible as a first-class tool from any AI interface, adoption isn't a sales problem — it's
a discovery problem, and discovery is free.

---

## Architecture Overview

The prototype implementation validates the following architecture end-to-end:

```
AI Client (Claude.ai, Claude Code, Cursor, custom agent)
    │  MCP over HTTPS
    ▼
MCP OAuth Proxy            — OAuth 2.1 + Google OIDC, injects identity header
    │
    ▼
Context Forge (MCP Gateway) — aggregates tool servers, RBAC by team
    │
    ├── signoz-mcp         — logs, traces, metrics, alerts
    ├── buildbuddy-mcp     — CI invocations and build logs
    ├── kubernetes-mcp     — pod/resource reads
    ├── argocd-mcp         — app status and sync
    └── agent-orchestrator-mcp   ← the platform's MCP facade
            │  HTTP (ClusterIP)
            ▼
    Agent Orchestrator (Go)
    │  NATS JetStream WorkQueue
    │  ├── stream: agent-jobs    (durable, max 1000 msgs)
    │  └── KV: job-records       (state, TTL 7 days)
    │
    ▼
    Agent Sandbox Controller (kubernetes-sigs/agent-sandbox)
    │  SandboxClaim → allocate from warm pool
    ▼
    Goose Agent Pod  (Wolfi/apko, uid 65532, resource-capped)
        ├── developer tools   (fs, shell, editor — /workspace only)
        ├── context-forge MCP (all registered tool servers)
        └── github MCP        (clone, commit, PR)
```

**Key design properties:**

- **NATS JetStream WorkQueue** — durable, ordered, at-least-once delivery. At most 3 jobs run
  concurrently (configurable). No external database for job state.
- **SandboxClaim / SandboxWarmPool** — pre-warmed pods mean near-instant job start. Each job
  gets a fresh pod; the controller deletes it on completion. No shared state between jobs.
- **Retry with context inheritance** — on failure, the next attempt's prompt is enriched with
  the previous exit code and last 2,000 chars of output, so the agent can adapt rather than
  repeat.
- **Inactivity watchdog** — 10-minute output timeout cancels hung sessions, preventing queue
  starvation.
- **Job profiles** — scoped MCP tokens per profile (`ci-debug`, `code-fix`, or unrestricted).
  Profiles map to Goose recipe YAMLs baked into the agent image.
- **OpenTelemetry instrumentation** — every job emits spans to SigNoz. Job lifecycle events
  (submitted, started, retried, completed) are traceable without log scraping.

---

## Benefits by Persona

**Platform engineers**
Stop being the bottleneck for "can you write me a script that does X against the cluster."
Publish an MCP-connected job profile and let teams self-serve. Execution is sandboxed and
auditable — you can review what ran without being in the loop for every job.

**Application developers**
Submit "fix the flaky test in service X" or "cut a PR that bumps all dependencies" directly
from Claude Code. No context switching to a separate tool. The agent works from the latest
`main`, has access to CI logs via BuildBuddy MCP, and can push a PR for review without
leaving the conversation.

**AppSec**
Schedule nightly Semgrep sweeps across all repos, with results written to a dashboard. Run
targeted dependency audits on-demand from a chat interface. Audit logs are automatic — every
job records prompt, output, and exit code.

**Data teams**
Trigger Snowflake pipeline investigations or schema drift checks conversationally. A Snowflake
MCP server behind Context Forge gives agents read access to query metadata, usage stats, and
pipeline health — same interface as every other tool.

**Non-engineering teams**
The MCP interface means a non-engineer using Claude.ai can submit jobs as naturally as asking
a colleague for help. Finance can schedule recurring reconciliation checks. GTM can trigger
competitive research jobs. The platform handles the execution; they see the result.

**The compound effect**
Each new MCP server registered with Context Forge immediately becomes available to every agent
running on the platform. The cost of adding capability is additive, not multiplicative. A
Snowflake MCP server benefits every team's agents on day one.

---

## What Exists Today

The homelab cluster is running this architecture in production. The prototype has completed
real jobs including:

- CI failure investigation (BuildBuddy MCP → read logs → identify root cause → open PR)
- Code fix workflows (clone repo → edit → commit → PR)
- Cluster health checks (Kubernetes + ArgoCD MCP → summarize state)
- Long-running patrol agents that watch for open alerts and act autonomously

The implementation is not a sketch. It includes:

- `services/agent-orchestrator/` — ~800 lines of Go: HTTP API, NATS consumer, sandbox
  lifecycle, retry logic, watchdog, inactivity timeout
- `services/agent_orchestrator_mcp/` — Python FastMCP wrapper exposing 5 MCP tools
- `charts/agent-orchestrator/`, `charts/goose-sandboxes/`, `charts/goose-agent/` — Helm
  charts for all components
- `charts/agent-sandbox/` — Kubernetes controller + CRDs (upstream `kubernetes-sigs/agent-sandbox`)
- `charts/context-forge/`, `charts/mcp-servers/` — MCP gateway and registered tool servers
- Full OTel instrumentation with SigNoz dashboards

The architecture document lives at `architecture/agents.md`.

---

## Next Steps

The gap between homelab prototype and org-ready is operational, not architectural.

| Area | Work needed |
|---|---|
| **Multi-tenancy** | Context Forge RBAC already supports team-scoped tokens. Define team boundaries, provision credentials per team. |
| **Secret management** | Replace homelab 1Password operator secrets with org secret store (Vault, AWS Secrets Manager, or equivalent). |
| **Job quotas** | Add per-team concurrency limits and job TTL policies. The NATS consumer config supports this today. |
| **Snowflake MCP** | Register a Snowflake MCP server with Context Forge. Agents immediately gain data access. |
| **Audit export** | NATS KV stores job records with 7-day TTL. Wire a consumer that exports completed jobs to a durable audit log (S3, BigQuery). |
| **Observability handoff** | The homelab SigNoz instance has all the dashboards. Replicate to the org observability stack. |
| **Load testing** | The warm pool and consumer concurrency need tuning under realistic org job volume. |

None of this requires redesigning the core. The orchestrator, sandbox controller, and MCP
gateway are production-quality and extensible. The ask is infrastructure, not R&D.

---

## Summary

The next engineering force-multiplier isn't headcount — it's making agent deployment
low-friction enough that every team can participate. The platform described here exists,
works, and is running real jobs today. The path to org-wide deployment is a focused
operational lift, not a build. The cost of not moving is every team continuing to reinvent
the same plumbing, or more likely, not running agents at all.
