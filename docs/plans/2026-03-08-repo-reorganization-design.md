# Repo Reorganization Design

**Date:** 2026-03-08
**Status:** Draft
**Supersedes:** ADR 001 Phase 2 (directory reorganization)

---

## Problem

The homelab monorepo has grown organically with a layer-first structure (`services/`, `charts/`, `overlays/`, `websites/`). Related code is scattered — understanding how a service works requires jumping between 3-4 top-level directories. The overlay system adds indirection for environments that don't meaningfully differ.

## Design

### Organising principle: domain-first

Group everything by **what it does**, not what it is. Each domain contains its own source code, Helm chart, and ArgoCD deployment config. No more cross-referencing between `services/X`, `charts/X`, and `overlays/prod/X`.

### Top level

```
/
├── projects/
│   ├── agent-platform/     # AI/ML agent infrastructure
│   ├── websites/           # User-facing products (subdomain convention)
│   ├── platform/           # Kubernetes infrastructure
│   └── operators/          # Custom K8s operators
├── bazel/                  # Build infrastructure
├── docs/                   # Merged architecture/ + docs/
└── (root config files)
```

### `projects/agent-platform/`

All agent, MCP, and ML inference infrastructure.

```
agent-platform/
├── orchestrator/           # agent-orchestrator service + deploy
├── cluster-agents/         # cluster-agents service + deploy
├── context-forge/          # MCP aggregator (deploy only)
├── mcp-servers/            # MCP server deployments
├── mcp-oauth-proxy/        # OAuth proxy for MCP
├── sandboxes/              # goose-sandboxes + agent-sandbox
├── todo-mcp/               # todo MCP service + deploy
├── buildbuddy-mcp/         # buildbuddy MCP service + deploy
├── llama-cpp/              # LLM inference (deploy only)
├── knowledge-graph/        # knowledge graph service + deploy
└── vllm/                   # LLM inference (deploy only)
```

### `projects/websites/`

User-facing products. Directory name = subdomain (e.g. `trips/` → `trips.jomcgi.dev`).

```
websites/
├── home/                   # jomcgi.dev
├── trips/                  # trips.jomcgi.dev — backend, frontend, tools
├── ships/                  # ships.jomcgi.dev — backend, frontend, ingest
├── hikes/                  # hikes.jomcgi.dev — backend, frontend
├── grimoire/               # grimoire.jomcgi.dev — backend, frontend
├── stars/                  # stars.jomcgi.dev (renamed from stargazer)
└── docs/                   # docs.jomcgi.dev
```

### `projects/platform/`

Kubernetes cluster infrastructure. Deploy-only (upstream charts with values).

```
platform/
├── argocd/
├── argocd-image-updater/
├── cert-manager/
├── cloudflare/             # tunnel + ingress consolidated
├── coredns/
├── envoy-gateway/
├── kyverno/
├── linkerd/
├── longhorn/
├── nats/
├── nvidia-gpu-operator/
├── opentelemetry-operator/
├── seaweedfs/
└── signoz/                 # signoz + alerts + dashboard-sidecar + operator
```

### `projects/operators/`

Custom Kubernetes operators (Go, controller-runtime).

```
operators/
├── cloudflare/
├── oci-model-cache/
└── sextant/
```

### `bazel/`

All build infrastructure consolidated.

```
bazel/
├── semgrep/
│   ├── defs/               # Bazel .bzl rule definitions
│   ├── rules/              # Semgrep YAML scan policies
│   └── third_party/        # OCI image digests
├── helm/                   # rules_helm/
├── vitepress/              # rules_vitepress/
├── wrangler/               # rules_wrangler/
├── images/                 # Container image BUILD targets
└── tools/
    └── cdk8s/              # From poc/
```

### `docs/`

Merged from `architecture/` + `docs/`.

```
docs/
├── decisions/              # ADRs (currently architecture/decisions/)
├── plans/                  # Design docs and implementation plans
├── security.md
├── contributing.md
├── services.md
├── observability.md
└── ...
```

---

## Inner subproject convention

Every subproject uses a standardized set of subdirectories. Not every project needs all of them — use only what applies.

```
<subproject>/
├── backend/                # API / service source code (Go, Python)
├── frontend/               # Web UI (Vite, React, Astro)
├── ingest/                 # Data ingestion from third parties
├── deploy/                 # Helm chart + ArgoCD config (flat)
│   ├── application.yaml    # ArgoCD Application
│   ├── values.yaml         # Helm values (prod — single source of truth)
│   ├── imageupdater.yaml   # ArgoCD Image Updater (optional)
│   ├── Chart.yaml
│   └── templates/
├── tools/                  # Scripts, utilities specific to this project
└── BUILD
```

### Key conventions

- **Standardized subdirectories** — `backend/`, `frontend/`, `ingest/`, `deploy/`, `tools/`. Use only what applies.
- **No overlays** — `deploy/values.yaml` IS the prod config. No dev/prod distinction.
- **No separate `charts/`** — chart templates colocated in `deploy/` within each subproject.
- **Subdomain convention** — website directory name = subdomain prefix.
- **Flat deploy** — ArgoCD app, values, chart all in one `deploy/` directory.
- **Values merge** — when collapsing chart `values.yaml` + overlay `values.yaml`, the overlay values take precedence. The merged result becomes `deploy/values.yaml`. Also update `helm.valueFiles` in `application.yaml` to reference the colocated `values.yaml`.

---

## Migration mapping

| Current location                  | New location                                      |
| --------------------------------- | ------------------------------------------------- |
| `services/agent-orchestrator`     | `projects/agent-platform/orchestrator/backend/`   |
| `services/agent_orchestrator_mcp` | `projects/agent-platform/orchestrator/backend/`   |
| `services/cluster-agents`         | `projects/agent-platform/cluster-agents/backend/` |
| `services/todo_mcp`               | `projects/agent-platform/todo-mcp/backend/`       |
| `services/buildbuddy_mcp`         | `projects/agent-platform/buildbuddy-mcp/backend/` |
| `services/knowledge_graph`        | `projects/agent-platform/knowledge-graph/backend/`|
| `services/grimoire`               | `projects/websites/grimoire/backend/`             |
| `services/trips_api`              | `projects/websites/trips/backend/`                |
| `services/hikes`                  | `projects/websites/hikes/backend/`                |
| `services/ships_api`              | `projects/websites/ships/backend/`                |
| `services/ships_frontend`         | `projects/websites/ships/frontend/`               |
| `services/ais_ingest`             | `projects/websites/ships/ingest/`                 |
| `services/stargazer`              | `projects/websites/stars/backend/`                |
| `websites/jomcgi.dev`             | `projects/websites/home/frontend/`                |
| `websites/trips.jomcgi.dev`       | `projects/websites/trips/frontend/`               |
| `websites/ships.jomcgi.dev`       | `projects/websites/ships/frontend/`               |
| `websites/hikes.jomcgi.dev`       | `projects/websites/hikes/frontend/`               |
| `websites/docs.jomcgi.dev`        | `projects/websites/docs/frontend/`                |
| `charts/*`                        | `projects/**/deploy/` (colocated)                 |
| `overlays/prod/*`                 | `projects/**/deploy/` (values merged)             |
| `overlays/dev/*`                  | `projects/**/deploy/` (values merged)             |
| `overlays/cluster-critical/*`     | `projects/platform/*/deploy/`                     |
| `argo-cd/`                        | `projects/platform/argocd/`                       |
| `rules_semgrep/`                  | `bazel/semgrep/defs/`                             |
| `semgrep_rules/`                  | `bazel/semgrep/rules/`                            |
| `third_party/semgrep*`            | `bazel/semgrep/third_party/`                      |
| `rules_helm/`                     | `bazel/helm/`                                     |
| `rules_vitepress/`                | `bazel/vitepress/`                                |
| `rules_wrangler/`                 | `bazel/wrangler/`                                 |
| `tools/`                          | `bazel/tools/`                                    |
| `images/`                         | `bazel/images/`                                   |
| `poc/cdk8s`                       | `bazel/tools/cdk8s/`                              |
| `scripts/publish-trip-images`     | `projects/websites/trips/tools/`                  |
| `scripts/backfill-elevation`      | `projects/websites/trips/tools/`                  |
| `scripts/detect-wildlife`         | `projects/websites/trips/tools/`                  |
| `scripts/delete-trip-points`      | `projects/websites/trips/tools/`                  |
| `scripts/elevation`               | `projects/websites/trips/tools/`                  |
| `scripts/publish-gap-route`       | `projects/websites/trips/tools/`                  |
| `architecture/`                   | `docs/`                                           |
| `operators/cloudflare`            | `projects/operators/cloudflare/`                  |
| `operators/oci-model-cache`       | `projects/operators/oci-model-cache/`             |
| `sextant/`                        | `projects/operators/sextant/`                     |
| `seaweedfs/`                      | `projects/platform/seaweedfs/` (merge templates)  |

Note: `services/trips-api/` exists but only contains `__pycache__` — delete, don't migrate.

### Scripts not specific to a domain

| Script                                 | Disposition  |
| -------------------------------------- | ------------ |
| `scripts/setup-mcp-profiles.sh`        | `bazel/tools/` |
| `scripts/signoz-mcp-wrapper.sh`        | `bazel/tools/` |
| `scripts/test-charts.sh`               | `bazel/tools/` |
| `scripts/generate-*.sh`                | `bazel/tools/` |
| `scripts/validate-generate-scripts.sh` | `bazel/tools/` |

---

## ArgoCD discovery

`clusters/homelab/kustomization.yaml` currently references `overlays/`. After migration, it must reference the new `projects/**/deploy/application.yaml` paths. Two options:

1. **Keep `clusters/`** as a thin kustomization that lists all `application.yaml` paths
2. **ArgoCD ApplicationSet** with a git directory generator that discovers `deploy/application.yaml` files automatically

Option 2 is preferred long-term — it means adding a new service doesn't require updating a central manifest.

---

## Risks

| Risk                                                 | Likelihood | Impact | Mitigation                                                           |
| ---------------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------- |
| Bazel targets break (every `//services/X` reference) | High       | High   | `buildozer` automated refactor; full `bazel test //...` before merge |
| ArgoCD apps lose sync after path changes             | High       | High   | Update all Application source paths atomically                       |
| CI pipeline paths stale                              | High       | Medium | Update `buildbuddy.yaml` path filters                                |
| Stale references in docs/CLAUDE.md                   | Medium     | Low    | Grep for old paths post-migration                                    |
| Large PR difficult to review                         | Medium     | Medium | Break into incremental moves per domain                              |

---

## Open questions

1. Should the migration be one large PR or incremental per-domain moves?
2. Should `clusters/` be replaced with an ApplicationSet during or after the migration?
3. What happens to `overlays/dev/` services (grimoire, marine, stargazer, oci-model-cache) — are they promoted to prod or kept as-is?
