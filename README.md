# Homelab

A single-person production platform. Production-grade infrastructure — GitOps, mTLS, hermetic remote builds — paired with AI-native systems: on-cluster LLM inference, autonomous agents, and an LLM-powered knowledge graph. Built so I can take an idea to a running, observable, securely-deployed service in under an hour.

28 services · 64 deployments · ~30k vessel positions tracked live · 1,300+ knowledge-graph facts from on-cluster LLM inference · in production since January 2025

**If you're here to evaluate:** start with [`agent_platform/`](projects/agent_platform/) (distributed agent orchestration with sandboxing and RBAC-scoped tool access), [`monolith/knowledge/`](projects/monolith/knowledge/) (LLM-powered knowledge graph with on-cluster inference), [`operators/oci-model-cache/`](projects/operators/oci-model-cache/) (custom Kubernetes operator with compiler-enforced state machines), and [`ships/`](projects/ships/) (end-to-end: real-time data pipeline → WebSocket API → MapLibre frontend).

## Systems

### AI platform

On-cluster Gemma 4 for chat and voyage-4-nano for embeddings, both served via llama.cpp on a dedicated GPU node. These power three interconnected systems:

- **Knowledge pipeline** (`projects/monolith/knowledge/`) — Raw markdown is ingested, decomposed into structured facts by a Gemma-4 gardener (with self-critique for quality), embedded with voyage-4-nano, and stored in pgvector for semantic search. Includes a dead-letter queue for failed ingest, a reconciler for incremental re-embedding, and MCP tool exposure so AI agents can query the graph. Fronted by a SvelteKit app with a `Cmd+K` search overlay. _Demonstrates: ML data pipeline design with local inference, not just API calls to hosted models._

- **Agent platform** (`projects/agent_platform/`) — Claude and Goose agents run in isolated Kubernetes sandbox pods, dispatched by a Go orchestrator over NATS JetStream, with tool access governed by Context Forge (IBM's MCP gateway) and RBAC-scoped per team. External access is authenticated via Cloudflare Managed OAuth. Includes MCP servers for ArgoCD, Kubernetes, SigNoz, and BuildBuddy — so agents can investigate CI failures, query observability data, and manage deployments without direct cluster access. _Demonstrates: distributed systems design — sandboxing, job queues, auth, tool governance._ See [docs/agents.md](docs/agents.md).

- **Discord bot** (`projects/monolith/chat/`) — AI-powered responses with embeddings, vision, web search, channel summarisation, and history backfill. Queries the knowledge graph for context.

### OCI Model Cache operator

`projects/operators/oci-model-cache/` — Custom Kubernetes operator that syncs ML models from HuggingFace to OCI registries using a `ModelCache` CRD. Compiler-enforced state machine transitions with sealed interfaces and OpenTelemetry tracing baked into every phase change. _Demonstrates: CRD design, controller patterns, and the kind of state-machine rigour that eliminates categories of bugs._

### Build system

Custom Bazel rules for Helm (`bazel/helm/`), Semgrep (`bazel/semgrep/`), and Cloudflare Pages (`bazel/wrangler/`). Hermetic Semgrep SAST runs as native Bazel tests with semgrep-core vendored as OCI artifacts. All builds and tests run remotely via BuildBuddy RBE — no local Bazel needed. Container images use apko (not Dockerfiles), dual-arch (x86*64 + aarch64), non-root by default. \_Demonstrates: supply-chain-secure, hermetic, remotely executed builds.*

## Applications

Proof-of-platform — each ships on the infrastructure described above.

- **Marine tracking** (`projects/ships/`) — Real-time AIS vessel tracking. Streams position reports, stores in SQLite (7-day retention), serves REST + WebSocket API with moored-vessel deduplication. MapLibre GL frontend with live vessel positions, types, and courses.

- **Trip tracker** (`projects/trips/`) — Photo-based GPS trip logging. Upload travel photos, reconstruct the route from EXIF data, enrich with elevation from NRCan CDEM API. Timeline view with day-by-day maps and elevation profiles.

- **Stargazer** (`projects/stargazer/`) — Finds the best stargazing spots in Scotland for the next 72 hours. Multi-phase pipeline: light pollution atlas + OSM road data, dark zones near roads, weather forecast scoring.

- **Hiking routes** (`projects/hikes/`) — Scottish route finder. Scrapes WalkHighlands, enriches with weather forecasts, surfaces hikes with good conditions.

## Infrastructure patterns

See [docs/security.md](docs/security.md) for the defense-in-depth model and [docs/observability.md](docs/observability.md) for automatic instrumentation.

| Area          | Approach                                                                      |
| ------------- | ----------------------------------------------------------------------------- |
| Ingress       | Cloudflare Tunnel only — nothing exposed directly                             |
| Service mesh  | Linkerd — automatic mTLS and distributed tracing, no code changes             |
| Observability | SigNoz — unified metrics, logs, traces. Kyverno auto-injects OTEL env vars    |
| Policy        | Kyverno — enforces non-root (uid 65532), read-only filesystems                |
| Secrets       | 1Password Operator — OnePasswordItem CRDs, nothing in Git                     |
| Storage       | Longhorn for persistent volumes, SeaweedFS for S3-compatible object storage   |
| Messaging     | NATS JetStream — pub/sub backbone for AIS data, trip points, agent jobs       |
| GPU           | NVIDIA GPU Operator — Gemma 4 + voyage-4-nano on-cluster via llama.cpp        |
| Images        | apko + rules_apko — no Dockerfiles, dual-arch (x86_64 + aarch64), non-root    |
| CI            | BuildBuddy Workflows — remote build execution, `bazel test //...`, image push |
| GitOps        | ArgoCD — colocated `deploy/` dirs, `kubectl` is read-only                     |

## Repo layout

```
projects/             # All services, operators, websites — colocated with deploy configs
├── platform/         #   Cluster-critical infrastructure (ArgoCD, Linkerd, SigNoz, etc.)
├── agent_platform/   #   Agent services (Context Forge, MCP servers, orchestrator, etc.)
├── monolith/         #   Knowledge graph, Discord bot, task management, frontend
├── ships/            #   Marine vessel tracking
├── trips/            #   Trip tracker
├── stargazer/        #   Dark sky finder
├── hikes/            #   Scottish hiking routes
├── operators/        #   Custom Kubernetes operators
├── websites/         #   Static sites (VitePress, Astro)
└── home-cluster/     #   Auto-generated ArgoCD root kustomization
bazel/                # Build infrastructure (rules, tools, images, semgrep)
docs/                 # Design docs, ADRs, and plans
```

See [docs/contributing.md](docs/contributing.md) for the full structure. Architecture decisions are tracked in [docs/decisions/](docs/decisions/).

## What's next

- **Semgrep rule generation** — RL-finetuned local model for generating Semgrep rules from CVE descriptions. The build system already runs hermetic Semgrep; this closes the loop by generating the rules themselves.
- **Knowledge graph expansion** — Ingest D&D sourcebooks (via Marker parsing) and repo documentation into the knowledge pipeline, making ADRs and design docs semantically searchable alongside notes.

Full backlog and architecture decisions: [docs/decisions/](docs/decisions/)

---

Built by [Joe McGinley](https://github.com/jomcgi). [MPL-2.0](LICENSE).
