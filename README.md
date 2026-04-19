# Homelab

Personal monorepo. Dev tooling and deployment for my projects.

28 services · 64 deployments · ~30k vessel positions tracked live · 1,300+ knowledge-graph facts from on-cluster LLM inference · in production since January 2025

## Systems

### AI platform

On-cluster Gemma 4 for chat and voyage-4-nano for embeddings, both served via llama.cpp on a dedicated GPU node. These power three interconnected systems:

- [**Knowledge pipeline**](projects/monolith/knowledge/) — Markdown ingested, decomposed into structured facts by Gemma-4 (with self-critique), embedded with voyage-4-nano, stored in pgvector. Dead-letter queue, incremental re-embedding reconciler, MCP tool exposure for AI agents. SvelteKit frontend with `Cmd+K` search.

- [**Agent platform**](projects/agent_platform/) — Claude and Goose agents in isolated Kubernetes sandbox pods, dispatched by a Go orchestrator over NATS JetStream. Tool access governed by Context Forge (IBM's MCP gateway), RBAC-scoped per team. Cloudflare Managed OAuth for external access. MCP servers for ArgoCD, Kubernetes, SigNoz, and BuildBuddy. See [docs/agents.md](docs/agents.md).

- [**Discord bot**](projects/monolith/chat/) — AI-powered responses with embeddings, vision, web search, channel summarisation, and history backfill. Queries the knowledge graph for context.

### [OCI Model Cache operator](projects/operators/oci-model-cache/)

Custom Kubernetes operator that syncs ML models from HuggingFace to OCI registries using a `ModelCache` CRD. Compiler-enforced state machine transitions with sealed interfaces and OpenTelemetry tracing.

### Build system

Custom Bazel rules for [Helm](bazel/helm/), [Semgrep](bazel/semgrep/), and [Cloudflare Pages](bazel/wrangler/). Hermetic Semgrep SAST runs as native Bazel tests with semgrep-core vendored as OCI artifacts. All builds run remotely via BuildBuddy RBE. Container images use apko (not Dockerfiles), dual-arch (`x86_64` + `aarch64`), non-root by default.

## Applications

- [**Marine tracking**](projects/ships/) — Real-time AIS vessel tracking. Streams position reports, stores in SQLite, serves REST + WebSocket API. MapLibre GL frontend with live vessel positions.

- [**Trip tracker**](projects/trips/) — Photo-based GPS trip logging. Reconstructs routes from EXIF data, enriches with elevation from NRCan CDEM API. Timeline view with day-by-day maps.

- [**Stargazer**](projects/stargazer/) — Best stargazing spots in Scotland for the next 72 hours. Light pollution atlas + OSM road data, dark zones near roads, weather forecast scoring.

- [**Hiking routes**](projects/hikes/) — Scottish route finder. Scrapes WalkHighlands, enriches with weather forecasts, surfaces hikes with good conditions.

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
