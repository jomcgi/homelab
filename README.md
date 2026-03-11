# Homelab

Personal monorepo. The goal is to make shipping a new service as low-friction as possible, so that I can bring my ideas into contact with reality.

## Tooling

### sextant

`projects/sextant/` - Every operator I wrote had the same category of bugs: invalid state transitions, missing observability, hand-rolled switch statements. So I built a generator to eliminate the category. Define states and transitions in YAML, get Go code with compiler-enforced transitions, sealed interfaces, and OpenTelemetry tracing. Used by both operators below.

### Operators

- `projects/operators/cloudflare` - Manages Cloudflare Tunnel routing, DNS records, and Zero Trust policies from Kubernetes annotations via Gateway API
- `projects/operators/oci-model-cache` - Syncs HuggingFace models to OCI registries using a `ModelCache` CRD

### Bazel rules

- `bazel/helm/` - Helm chart lint, template, package, and OCI push as Bazel targets. Includes an ArgoCD application macro with live diff support
- `bazel/semgrep/` - Hermetic Semgrep scanning as native Bazel tests. Vendors semgrep-core as OCI artifacts, supports Pro rules, auto-generates scan targets via Gazelle
- `bazel/wrangler/` - Cloudflare Pages deployment via Wrangler as Bazel targets

## Projects

See [docs/services.md](docs/services.md) for everything running in the cluster.

### Agent platform

`projects/agent_platform/` - Full autonomous agent infrastructure. Claude and Goose agents run in isolated Kubernetes sandbox pods, dispatched by an orchestrator over NATS JetStream, with tool access governed by Context Forge (IBM's MCP gateway) and RBAC-scoped per team. Includes MCP servers for ArgoCD, Kubernetes, SigNoz, and BuildBuddy — so agents can investigate CI failures, query observability data, and manage deployments without direct cluster access. See [docs/agents.md](docs/agents.md) for the full architecture.

### Marine tracking

Real-time AIS vessel tracking for the Pacific Northwest coast.

- `projects/ships/backend/` - Streams AIS position reports, stores in SQLite (7-day retention), serves REST + WebSocket API with moored-vessel deduplication
- `projects/ships/frontend/` - MapLibre GL map showing live vessel positions, types, and courses

### Trip tracker

Photo-based GPS trip logging - upload travel photos and it reconstructs the route from EXIF data.

- `projects/trips/backend/` - Extracts GPS from photo EXIF, enriches with elevation from NRCan CDEM API, broadcasts via WebSocket. Replays NATS stream on startup to rebuild state
- `projects/websites/trips.jomcgi.dev/` - Timeline view with day-by-day maps and elevation profiles

### Stargazer

Finds the best stargazing spots in Scotland for the next 72 hours.

- `projects/stargazer/backend/` - Multi-phase pipeline: downloads light pollution atlas + OSM road data, identifies dark zones near roads, scores by weather forecast clarity

### Grimoire

AI-assisted D&D campaign manager.

- `projects/grimoire/api/` - Go REST API with Firestore persistence, campaign/character/encounter management

### Knowledge graph

RAG pipeline that scrapes, embeds, and searches content.

- `projects/blog_knowledge_graph/` - Three components: RSS/HTML scraper with SSRF protection → text chunker + vector embedder (Ollama or Gemini) → MCP server for semantic search over Qdrant

### Hiking routes

Scottish route finder with weather-aware surfacing.

- `projects/hikes/` - Scrapes routes from WalkHighlands, enriches with weather forecasts
- `projects/websites/hikes.jomcgi.dev/` - Surfaces hikes with good conditions for the coming days (static, Cloudflare R2)

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
| Messaging     | NATS JetStream - pub/sub backbone for AIS data, trip points, events                          |
| Images        | apko + rules_apko - no Dockerfiles, dual-arch (x86_64 + aarch64), non-root                   |
| CI            | BuildBuddy Workflows - format check + `bazel test //...` + image push on main                |
| GitOps        | ArgoCD syncs from `projects/home-cluster` → colocated `deploy/` dirs. `kubectl` is read-only |

## Repo layout

```
projects/             # All services, operators, websites — colocated with deploy configs
├── platform/         #   Cluster-critical infrastructure (ArgoCD, Linkerd, SigNoz, etc.)
├── agent_platform/   #   Agent services (Context Forge, MCP servers, orchestrator, etc.)
├── ships/            #   Marine vessel tracking
├── trips/            #   Trip tracker
├── grimoire/         #   D&D campaign manager
├── stargazer/        #   Dark sky finder
├── hikes/            #   Scottish hiking routes
├── operators/        #   Custom Kubernetes operators
├── websites/         #   Static sites (VitePress, Astro)
├── sextant/          #   State machine code generator
└── home-cluster/     #   Auto-generated ArgoCD root kustomization
bazel/                # Build infrastructure (rules, tools, images, semgrep)
docs/                 # Design docs, ADRs, and plans
```

See [docs/contributing.md](docs/contributing.md) for the full structure and how to add a new service.

Architecture decisions are tracked in [docs/decisions/](docs/decisions/).

## License

[MPL-2.0](LICENSE)
