# Homelab

Personal projects running on a K3s cluster in my office. Limited free time, so the infrastructure handles the boring parts — mTLS, observability, image builds, deploys — and I spend my time building things instead.

## Projects

See [`architecture/services.md`](architecture/services.md) for everything running in the cluster.

### Marine tracking

Real-time AIS vessel tracking for the Pacific Northwest coast.

- [`services/ais_ingest`](services/ais_ingest) — Streams AIS position reports from AISStream.io via WebSocket, filters to a coastal bounding box, publishes to NATS JetStream
- [`services/ships_api`](services/ships_api) — Consumes positions from NATS, stores in SQLite (7-day retention), serves REST + WebSocket API with moored-vessel deduplication
- [`websites/ships.jomcgi.dev`](websites/ships.jomcgi.dev) — MapLibre GL map showing live vessel positions, types, and courses

### Trip tracker

Photo-based GPS trip logging — upload travel photos and it reconstructs the route from EXIF data.

- [`services/trips_api`](services/trips_api) — Extracts GPS from photo EXIF, enriches with elevation from NRCan CDEM API, broadcasts via WebSocket. Replays NATS stream on startup to rebuild state
- [`websites/trips.jomcgi.dev`](websites/trips.jomcgi.dev) — Timeline view with day-by-day maps and elevation profiles

### Stargazer

Finds the best stargazing spots in Scotland for the next 72 hours.

- [`services/stargazer`](services/stargazer) — Multi-phase pipeline: downloads light pollution atlas + OSM road data, identifies dark zones near roads, scores by weather forecast clarity

### Grimoire

AI-assisted D&D campaign manager. Built for a Gemini Live integration experiment.

- [`services/grimoire/api`](services/grimoire/api) — Go REST API with Firestore persistence, campaign/character/encounter management
- [`services/grimoire/ws-gateway`](services/grimoire/ws-gateway) — WebSocket gateway for real-time session events

### Knowledge graph

RAG pipeline that scrapes, embeds, and searches content.

- [`services/knowledge_graph`](services/knowledge_graph) — Three components: RSS/HTML scraper with SSRF protection → text chunker + vector embedder (Ollama or Gemini) → MCP server for semantic search over Qdrant

### Hiking routes

- [`services/hikes`](services/hikes) — Scrapes Scottish hiking routes from WalkHighlands, enriches with weather forecasts
- [`websites/hikes.jomcgi.dev`](websites/hikes.jomcgi.dev) — Route finder that surfaces hikes with good weather conditions

## Custom tooling

### sextant

[`sextant/`](sextant) — Code generator for type-safe state machines in Kubernetes operators. Define states and transitions in YAML, get Go code with compiler-enforced transitions, sealed interfaces, and OpenTelemetry tracing. Used by both operators below.

### Operators

- [`operators/cloudflare`](operators/cloudflare) — Manages Cloudflare Tunnel routing, DNS records, and Zero Trust policies from Kubernetes annotations via Gateway API
- [`operators/oci-model-cache`](operators/oci-model-cache) — Syncs HuggingFace models to OCI registries using a `ModelCache` CRD

### hf2oci

[`tools/hf2oci`](tools/hf2oci) — CLI that converts HuggingFace model repos to multi-platform OCI images by streaming weight files directly into layers (no temp files).

### Bazel rules

- [`rules_helm/`](rules_helm) — Helm chart lint, template, package, and OCI push as Bazel targets. Includes ArgoCD application macro with live diff support
- [`rules_wrangler/`](rules_wrangler) — Cloudflare Pages deployment via Wrangler as Bazel targets

## Infrastructure patterns

The goal is to make shipping a new service as low-friction as possible — push code, get a secure, observable deployment without thinking about certificates, tracing, or image pipelines. See [`architecture/security.md`](architecture/security.md) for the defense-in-depth model and [`architecture/observability.md`](architecture/observability.md) for how automatic instrumentation works.

| Area | Approach |
|------|----------|
| **Ingress** | Cloudflare Tunnel only — nothing exposed directly |
| **Service mesh** | Linkerd — automatic mTLS and distributed tracing, no code changes |
| **Observability** | SigNoz — unified metrics, logs, traces. Kyverno auto-injects OTEL env vars |
| **Policy** | Kyverno — enforces non-root (uid 65532), read-only filesystems |
| **Secrets** | 1Password Operator — `OnePasswordItem` CRDs, nothing in Git |
| **Storage** | Longhorn for persistent volumes, SeaweedFS for S3-compatible object storage |
| **Messaging** | NATS JetStream — pub/sub backbone for AIS data, trip points, events |
| **Images** | apko + rules_apko — no Dockerfiles, dual-arch (x86_64 + aarch64), non-root |
| **CI** | BuildBuddy Workflows — format check + `bazel test //...` + image push on main |
| **GitOps** | ArgoCD syncs from `clusters/` → `overlays/` → `charts/`. kubectl is read-only |

## Repo layout

```
services/             # Go, Python backends
websites/             # Vite + React, Astro frontends
operators/            # Kubernetes controllers (Go, controller-runtime)
charts/               # Helm charts (custom + upstream wrappers)
overlays/             # Environment values (cluster-critical, dev, prod)
clusters/             # ArgoCD kustomization entry points
sextant/              # State machine code generator
tools/                # Build helpers (hf2oci, formatting, dev-deploy)
rules_helm/           # Custom Bazel rules for Helm
rules_wrangler/       # Custom Bazel rules for Cloudflare Pages
architecture/         # Design docs and ADRs
```

Service code lives inside its chart directory (colocation), not in separate `cmd/`/`pkg/` trees. See [`architecture/contributing.md`](architecture/contributing.md) for the full structure and how to add a new service. Architecture decisions are tracked in [`architecture/decisions/`](architecture/decisions).

## License

[MPL-2.0](LICENSE)
