# Homelab

Production Kubernetes cluster running on bare metal with GPU inference, autonomous AI agents, an LLM-powered knowledge graph, and custom operators — all deployed via GitOps with remote build execution. The goal is to make shipping a new service as low-friction as possible, so that I can bring my ideas into contact with reality.

## Systems

### Knowledge pipeline

`projects/monolith/knowledge/` - An LLM-powered knowledge graph that turns unstructured notes into a searchable, interconnected knowledge base. Raw markdown is ingested, decomposed into structured facts by a Gemma-4 gardener running on-cluster (with self-critique for quality), embedded with voyage-4-nano via llama.cpp, and stored in pgvector for semantic search. Includes a dead-letter queue for failed ingest, a reconciler for incremental re-embedding, and MCP tool exposure so AI agents can query the graph. Fronted by a SvelteKit app with a `Cmd+K` search overlay.

### Agent platform

`projects/agent_platform/` - Full autonomous agent infrastructure. Claude and Goose agents run in isolated Kubernetes sandbox pods, dispatched by a Go orchestrator over NATS JetStream, with tool access governed by Context Forge (IBM's MCP gateway) and RBAC-scoped per team. External access is authenticated via Cloudflare Managed OAuth. Includes MCP servers for ArgoCD, Kubernetes, SigNoz, and BuildBuddy — so agents can investigate CI failures, query observability data, and manage deployments without direct cluster access. See [docs/agents.md](docs/agents.md) for the full architecture.

### OCI Model Cache operator

`projects/operators/oci-model-cache/` - Custom Kubernetes operator that syncs ML models from HuggingFace to OCI registries using a `ModelCache` CRD. Uses compiler-enforced state machine transitions with sealed interfaces and OpenTelemetry tracing baked into every phase change.

### Build system

Custom Bazel rules for Helm (`bazel/helm/`), Semgrep (`bazel/semgrep/`), and Cloudflare Pages (`bazel/wrangler/`). Hermetic Semgrep SAST runs as native Bazel tests with semgrep-core vendored as OCI artifacts. All builds run remotely via BuildBuddy RBE — no local Bazel install needed. Container images use apko (not Dockerfiles), dual-arch (x86_64 + aarch64), non-root by default.

## Applications

### Marine tracking

Real-time AIS vessel tracking for the Pacific Northwest coast.

- `projects/ships/backend/` - Streams AIS position reports, stores in SQLite (7-day retention), serves REST + WebSocket API with moored-vessel deduplication
- `projects/ships/frontend/` - MapLibre GL map showing live vessel positions, types, and courses

### Trip tracker

Photo-based GPS trip logging - upload travel photos and it reconstructs the route from EXIF data.

- `projects/trips/backend/` - Extracts GPS from photo EXIF, enriches with elevation from NRCan CDEM API, broadcasts via WebSocket. Replays NATS stream on startup to rebuild state
- `projects/trips/frontend/` - Timeline view with day-by-day maps and elevation profiles

### Stargazer

Finds the best stargazing spots in Scotland for the next 72 hours.

- `projects/stargazer/backend/` - Multi-phase pipeline: downloads light pollution atlas + OSM road data, identifies dark zones near roads, scores by weather forecast clarity

### Grimoire

AI-assisted D&D campaign manager.

- `projects/grimoire/api/` - Go REST API with Firestore persistence, campaign/character/encounter management

### Hiking routes

Scottish route finder with weather-aware surfacing.

- `projects/hikes/` - Scrapes routes from WalkHighlands, enriches with weather forecasts
- `projects/hikes/frontend/` - Surfaces hikes with good conditions for the coming days (static, Cloudflare R2)

## Infrastructure patterns

See [docs/security.md](docs/security.md) for the defense-in-depth model and [docs/observability.md](docs/observability.md) for how automatic instrumentation works.

| Area          | Approach                                                                                     |
| ------------- | -------------------------------------------------------------------------------------------- |
| Ingress       | Cloudflare Tunnel only - nothing exposed directly                                            |
| Service mesh  | Linkerd - automatic mTLS and distributed tracing, no code changes                            |
| Observability | SigNoz - unified metrics, logs, traces. Kyverno auto-injects OTEL env vars                   |
| Policy        | Kyverno - enforces non-root (uid 65532), read-only filesystems                               |
| Secrets       | 1Password Operator - OnePasswordItem CRDs, nothing in Git                                    |
| Storage       | Longhorn for persistent volumes, SeaweedFS for S3-compatible object storage                  |
| Messaging     | NATS JetStream - pub/sub backbone for AIS data, trip points, agent jobs                      |
| GPU           | NVIDIA GPU Operator - Gemma 4 (chat) and voyage-4-nano (embeddings) on-cluster via llama.cpp |
| Images        | apko + rules_apko - no Dockerfiles, dual-arch (x86_64 + aarch64), non-root                   |
| CI            | BuildBuddy Workflows - remote build execution, format check, `bazel test //...`, image push  |
| GitOps        | ArgoCD syncs from `projects/home-cluster` - colocated `deploy/` dirs. `kubectl` is read-only |

## Repo layout

```
projects/             # All services, operators, websites — colocated with deploy configs
├── platform/         #   Cluster-critical infrastructure (ArgoCD, Linkerd, SigNoz, etc.)
├── agent_platform/   #   Agent services (Context Forge, MCP servers, orchestrator, etc.)
├── monolith/         #   Knowledge graph, Discord bot, task management, frontend
├── ships/            #   Marine vessel tracking
├── trips/            #   Trip tracker
├── grimoire/         #   D&D campaign manager
├── stargazer/        #   Dark sky finder
├── hikes/            #   Scottish hiking routes
├── operators/        #   Custom Kubernetes operators
├── websites/         #   Static sites (VitePress, Astro)
└── home-cluster/     #   Auto-generated ArgoCD root kustomization
bazel/                # Build infrastructure (rules, tools, images, semgrep)
docs/                 # Design docs, ADRs, and plans
```

See [docs/contributing.md](docs/contributing.md) for the full structure and how to add a new service.

Architecture decisions are tracked in [docs/decisions/](docs/decisions/).

## License

[MPL-2.0](LICENSE)
