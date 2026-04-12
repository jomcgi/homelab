# Observability Demo DAG Redesign

## Goal

Replace the hardcoded 9-node topology in the observability demo with a config-driven, auto-laid-out DAG that reflects the actual homelab architecture. Add a brutalist visual style inspired by MotherDuck.

## Topology

### Ingress

- **Cloudflare** — tunnel + gateway, sole entry point to the cluster
  - Connects to: monolith, context-forge, agent-platform (all ingress-exposed services)

### Critical Path

- **Monolith** (+ sub-services & postgres with distinct SLOs)
- **llama-cpp** — gemma-4 inference
- **voyage-embedder** — embedding model
- **agent-platform** — agent orchestration
- **context-forge** — MCP gateway
- **NATS** — JetStream message bus
- **postgres** — CNPG + pgvector

### Critical Path Edges

```
monolith ──sql──→ postgres
monolith ──nats──→ NATS
monolith ──grpc──→ context-forge
monolith ──http──→ llama-cpp
monolith ──http──→ voyage-embedder
NATS ──nats──→ agent-platform
agent-platform ──grpc──→ context-forge
context-forge ──mcp──→ k8s-mcp (virtual)
context-forge ──mcp──→ argocd-mcp (virtual)
context-forge ──mcp──→ signoz-mcp (virtual)
```

### Infrastructure (separate SLOs, no inter-relationships drawn)

ArgoCD, SigNoz, Envoy Gateway, Longhorn, SeaweedFS, OTel Operator, Linkerd

## Config Format

Single JSON file (`topology.json`) importable by Vite at build time. Each node has:

- `id`, `label`, `tier` (ingress | critical | infra)
- `ingress: true` flag for nodes exposed via Cloudflare
- Service metadata: `description`, `brief`, `status`, `slo`, `metrics`, `spark`

Edges: `{ from, to, protocol }`

## Layout Engine

**dagre** computes node positions from the graph structure.

- `rankdir: LR` (landscape) / `TB` (portrait)
- Tier → rank constraints: ingress=0, critical=auto, infra=separate band
- Infra nodes pinned to bottom/right via hidden anchor edges
- Node width computed from label length
- Re-run dagre on orientation change (replaces two hand-tuned coordinate sets)

## Visual Style (MotherDuck Brutalist)

- Background: warm cream `#f5f0e8` (light) / deep charcoal `#1a1a1a` (dark)
- Node boxes: thick black Rough.js rectangles, filled with tier color
- Critical tier: pale yellow `#fff3c4` / `#3d3520`
- Infra tier: light grey `#e8e8e8` / `#2a2a2a`
- Ingress: light blue `#dbeafe` / `#1e3a5f`
- Typography: monospace, uppercase labels, bold
- Edges: Rough.js lines with protocol labels

## What Stays

All animation infrastructure: BFS draw sequencing, dual-pass pencil→ink, scribble highlight, paper-flip transition, detail drawer, dark mode, staggered pen cursors.
