# Design: Public Stats Endpoint + Kubernetes Client

**Date:** 2026-04-18
**Status:** Approved

## Goal

Add a `/api/public/stats` endpoint to the monolith that exposes non-sensitive cluster and knowledge-graph metrics. Provides a live window into the platform for the repo README and external visitors.

Secondary goal: introduce a reusable async Kubernetes client to the monolith, positioned for future observability MCP tooling.

## Architecture

```
monolith/
├── shared/
│   └── kubernetes.py          # Async k8s client wrapper (reusable)
└── observability/
    ├── stats.py               # Stats collection + caching
    └── router.py              # Register /api/public/stats route
```

### Kubernetes Client (`shared/kubernetes.py`)

Thin wrapper around `kubernetes_asyncio`. In-cluster config, scoped to read-only list operations. Lives in `shared/` for reuse by future observability MCP.

Interface:

```python
class KubernetesClient:
    async def count_nodes() -> int
    async def count_deployments() -> int
    async def count_pods() -> int
    async def count_argocd_applications() -> int
```

### Stats Endpoint (`observability/stats.py`)

Gathers stats from two sources:

1. **Kubernetes API** — node, deployment, pod, ArgoCD application counts
2. **PostgreSQL** — knowledge.notes, knowledge.chunks, knowledge.raw_inputs counts

Response shape:

```json
{
  "cluster": {
    "nodes": 4,
    "deployments": 64,
    "services": 28,
    "pods": 135
  },
  "knowledge": {
    "facts": 1309,
    "chunks": 5948,
    "raw_inputs": 366
  },
  "platform": {
    "in_production_since": "2025-01"
  },
  "cached_at": "2026-04-18T14:30:00Z"
}
```

### Caching

24h TTL, same pattern as topology endpoint. Warm-loaded on startup via lifespan. No manual refresh endpoint — wait for TTL expiry.

### RBAC

ClusterRole for monolith ServiceAccount:

```yaml
rules:
  - apiGroups: [""]
    resources: ["nodes", "pods"]
    verbs: ["list"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["list"]
  - apiGroups: ["argoproj.io"]
    resources: ["applications"]
    verbs: ["list"]
```

### Dependencies

- `kubernetes-asyncio` added to monolith Python deps (pip + Bazel `@pip//kubernetes_asyncio`)

## Deferred

- Ships vessel count (needs HTTP client to ships backend — ships will eventually move into monolith)
- Agent job counts (needs NATS or orchestrator API — same)
- Observability MCP server (future work, k8s client is designed for it)

## Testing

- Unit tests for stats collection with mocked k8s client and DB session
- Integration test via `bb remote test`
