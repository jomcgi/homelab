# Nexus Monolith Design

## Problem

The homelab has accumulated many small services (trips, ships, stargazer, todo_app), each with its own Helm chart, image pipeline, ArgoCD application, and deploy config. This creates operational overhead disproportionate to the simplicity of the services — scope creep through infrastructure sprawl.

## Decision

Consolidate lightweight web apps into a single "Nexus" monolith: one FastAPI backend, one SvelteKit frontend, one Helm chart, one deploy pipeline. Services get logical isolation via Postgres schemas and route namespacing, not physical isolation via separate pods.

## Architecture

```
   Cloudflare Pages (resilient to cluster downtime):
   +----------------------------+
   | jomcgi.dev      (portfolio)|
   | docs.jomcgi.dev (docs)     |
   +----------------------------+

   Cloudflare (CDN + Access SSO + Cache)
        |
        +-- public.jomcgi.dev  → rate-limited, cached, no auth
        +-- private.jomcgi.dev → Cloudflare Access SSO (single policy)
        |
   Gateway API (Envoy)
   +--------------------+
   | 2 HTTPRoutes:      |
   |  public  (public.) |
   |  private (private.)|
   +--------------------+
        |
   +----+---------------------------+
   |       Nexus Pod (N replicas)   |
   |  +---------+  +-----------+   |
   |  | FastAPI  |  | Caddy     |  |
   |  | :8000    |  | :3000     |  |
   |  |          |  | (SvelteKit|  |
   |  |/api/todo |  |  static)  |  |
   |  |/api/trips|  |           |  |
   |  |/api/ships|  | /todo/    |  |
   |  |/api/star |  | /trips/   |  |
   |  +----+-----+  | /ships/   |  |
   |       |        +-----------+  |
   +-------+-----------------------+
           |
   +-------+--------+
   |  CloudNativePG  |    +----------+
   | (Postgres)      |    |   NATS   |
   | schema: todo    |    | (exists) |
   | schema: trips   |    +----------+
   | schema: ships   |
   | schema: stargazer|
   +-----------------+
```

API routes are internal only — Caddy reverse-proxies `/api/*` to FastAPI on localhost:8000 within the pod. No API endpoints are publicly exposed outside the cluster.

## Key Decisions

### Backend: FastAPI

- Trips and ships are already FastAPI; todo_app migrates from Go
- Single test harness (pytest), single dependency tree, single image
- Sub-routers per service: `/api/todo/*`, `/api/trips/*`, `/api/ships/*`, `/api/stargazer/*`

### Frontend: SvelteKit + mdsvex

- Replaces React 19 (trips, ships), vanilla JS (todo), and lightweight Python server (stargazer)
- SvelteKit with `adapter-static` builds to static files, served by Caddy sidecar
- mdsvex enables markdown content where needed
- Public static sites (jomcgi.dev, docs.jomcgi.dev) also migrate to SvelteKit but deploy to Cloudflare Pages via wrangler — same framework, different deploy target

### Database: CloudNativePG + Postgres

- New Postgres instance managed by CloudNativePG operator
- One database, separate schemas per service (`todo`, `trips`, `ships`, `stargazer`)
- Stateless app pods — enables `RollingUpdate` with multiple replicas, zero-downtime deploys
- Replaces: SQLite (trips, ships), JSON files (stargazer), git-backed files (todo)

### Schema Migrations: Atlas + SQLModel

- SQLModel classes are the single source of truth for database schema
- `atlas-provider-sqlalchemy` introspects models and generates DDL
- Versioned migrations generated via `atlas migrate diff --env nexus` during development
- Atlas Kubernetes Operator applies pending migrations on deploy via `AtlasMigration` CRD
- Bazel test enforces models and migrations stay in sync: runs `atlas migrate diff` and fails if new migration files are produced

### Gateway Routing: Two-Hostname Model

- **`public.jomcgi.dev`** — rate-limited via Envoy BackendTrafficPolicy, cached at Cloudflare edge, no auth
- **`private.jomcgi.dev`** — behind Cloudflare Access SSO (single policy covers all paths), no rate limiting
- Only **two HTTPRoutes** total (one per hostname), regardless of how many services the monolith contains
- Adding a new service to the monolith requires zero Cloudflare or gateway config — just add SvelteKit routes and FastAPI sub-routers
- Caddy is the pod entry point — reverse-proxies `/api/*` to FastAPI on localhost:8000
- API routes are internal to the pod; only the frontend is externally routable
- Portfolio (`jomcgi.dev`) and docs (`docs.jomcgi.dev`) remain on Cloudflare Pages, resilient to cluster downtime

### Deployment

- Single Helm chart at `projects/nexus/chart/`
- Single ArgoCD Application
- ArgoCD Image Updater for both backend and frontend images
- Rolling updates with zero downtime (stateless pods + Postgres)

## New Platform Infrastructure

Two upstream Helm charts, no custom charts:

| Component              | Purpose                       | Chart                           |
| ---------------------- | ----------------------------- | ------------------------------- |
| CloudNativePG Operator | Postgres lifecycle management | `cloudnative-pg/cloudnative-pg` |
| Atlas Operator         | Declarative schema migrations | `ariga/atlas-operator`          |

## Project Structure

```
projects/nexus/
├── backend/
│   ├── main.py                # FastAPI app, mounts sub-routers
│   ├── todo/
│   │   ├── router.py          # /api/todo/* routes
│   │   ├── models.py          # SQLModel table definitions
│   │   └── scheduler.py       # Daily/weekly reset logic
│   ├── trips/                 # (post-MVP)
│   ├── ships/                 # (post-MVP)
│   └── stargazer/             # (post-MVP)
├── frontend/
│   ├── svelte.config.js
│   ├── src/
│   │   ├── routes/
│   │   │   ├── todo/          # Todo SvelteKit pages
│   │   │   ├── trips/         # (post-MVP)
│   │   │   ├── ships/         # (post-MVP)
│   │   │   └── stargazer/     # (post-MVP)
│   │   └── lib/               # Shared components
│   └── static/
├── migrations/                # Atlas versioned migration files
│   └── atlas.sum              # Migration integrity file
├── atlas.hcl                  # Atlas config pointing to SQLModel models
├── chart/
│   ├── Chart.yaml
│   └── templates/
│       ├── deployment.yaml    # 2-container pod (FastAPI + Caddy)
│       ├── services.yaml
│       ├── cnpg-cluster.yaml  # CloudNativePG Cluster CRD
│       └── atlas-migration.yaml # AtlasMigration CRD
├── deploy/
│   ├── application.yaml       # ArgoCD Application
│   ├── kustomization.yaml
│   ├── values.yaml
│   └── imageupdater.yaml
└── BUILD
```

## Migration Schema: Atlas + SQLModel Flow

```
 Developer changes models.py
            |
            v
 atlas migrate diff --env nexus
            |
            v
 New .sql file in migrations/
            |
            v
 Bazel test: atlas migrate diff produces no new files (CI gate)
            |
            v
 PR merged -> ArgoCD syncs -> Atlas Operator applies migration
            |
            v
 New pod starts with updated schema
```

Atlas config:

```hcl
# atlas.hcl
data "external_schema" "sqlalchemy" {
  program = [
    "atlas-provider-sqlalchemy",
    "--path", "./backend",
    "--dialect", "postgresql",
  ]
}

env "nexus" {
  src = data.external_schema.sqlalchemy.url
  dev = "docker://postgres/16/dev"
  migration {
    dir = "file://migrations"
  }
}
```

## Gateway Routing Config

```yaml
# values.yaml
cfIngress:
  public:
    enabled: true
    tier: public
    hostname: public.jomcgi.dev
    servicePort: 3000
    rateLimit:
      requests: 100
      unit: Minute
  private:
    enabled: true
    tier: trusted
    hostname: private.jomcgi.dev
    servicePort: 3000
    team: jomcgi
```

| Hostname             | Tier    | Auth                  | Rate Limited | Cached                         |
| -------------------- | ------- | --------------------- | ------------ | ------------------------------ |
| `public.jomcgi.dev`  | public  | None                  | Yes          | Yes (stale-while-revalidate)   |
| `private.jomcgi.dev` | trusted | Cloudflare Access SSO | No           | No                             |
| `jomcgi.dev`         | —       | None                  | —            | Cloudflare Pages (not cluster) |
| `docs.jomcgi.dev`    | —       | None                  | —            | Cloudflare Pages (not cluster) |

## MVP Scope

**Goal:** todo_app fully migrated — proves the entire stack end-to-end.

### MVP Deliverables

1. **Platform:** CloudNativePG operator + Atlas operator (upstream charts)
2. **Nexus backend:** FastAPI with `todo` router, SQLModel models, daily/weekly scheduler
3. **Nexus frontend:** SvelteKit with todo pages (public read view + admin edit view)
4. **Nexus chart:** Helm chart with 2-container pod, CNPG Cluster, AtlasMigration, HTTPRoutes
5. **Nexus deploy:** ArgoCD application, values, image updater config
6. **CI:** Bazel test for migration drift, image build rules
7. **Retire:** `projects/todo_app/` removed after migration verified

### What Migrates (todo_app)

| Current (Go + files)     | MVP (FastAPI + Postgres)              |
| ------------------------ | ------------------------------------- |
| `data.json` on PVC       | `todo.tasks` table                    |
| `YYYY/MM/DD.md` archives | `todo.archives` table                 |
| Git commit on reset      | DB writes only                        |
| Go goroutine scheduler   | FastAPI BackgroundTask or APScheduler |
| Nginx sidecar (static)   | Caddy sidecar (SvelteKit build)       |
| Vanilla JS frontend      | SvelteKit + mdsvex                    |

### API Contract (preserved)

- `GET /api/todo/weekly` — current weekly task
- `GET /api/todo/daily` — current daily tasks
- `GET /api/todo` — full todo state
- `PUT /api/todo` — update todo state
- `POST /api/todo/reset/daily` — archive + clear daily
- `POST /api/todo/reset/weekly` — archive + clear all
- `GET /api/todo/dates` — available archive dates
- `GET /api/todo/archive/{date}` — rendered archive for date

### Deploy Downtime Strategy

- **Public routes (`public.jomcgi.dev`):** Cloudflare cache (`s-maxage`) serves stale during the ~5s rolling update window
- **Private routes (`private.jomcgi.dev`):** accept brief blip (only user is the operator)
- **Portfolio (`jomcgi.dev`):** unaffected — served from Cloudflare Pages, independent of cluster

## Post-MVP Roadmap

1. **Trips** — migrate FastAPI routes + React → SvelteKit, add `trips` schema
2. **Ships** — migrate FastAPI routes + React → SvelteKit, add `ships` schema
3. **Stargazer** — migrate Python server + web UI → SvelteKit, add `stargazer` schema
4. **Retire api_gateway** — once trips + stargazer are migrated, nothing routes through it; remove chart, deploy, image pipeline, SLO alerts, and `api.jomcgi.dev` DNS record
5. **Public sites** — migrate jomcgi.dev (Astro) and docs.jomcgi.dev (VitePress) to SvelteKit on Cloudflare Pages

### Services Retired by Consolidation

Once the monolith absorbs all planned services, the following are removed:

| Retired Service                        | What Goes Away                            |
| -------------------------------------- | ----------------------------------------- |
| `projects/todo_app/`                   | Chart, deploy, image pipeline (MVP)       |
| `projects/trips/`                      | Chart, deploy, image pipeline             |
| `projects/ships/`                      | Chart, deploy, image pipeline             |
| `projects/stargazer/`                  | Chart, deploy, image pipeline             |
| `projects/agent_platform/api_gateway/` | Chart, deploy, image pipeline, SLO alerts |
| `api.jomcgi.dev`                       | DNS record, Cloudflare config             |

Total: 5 Helm charts, 5 ArgoCD apps, 5 image pipelines, 1 public hostname eliminated.

## Services NOT Consolidated

| Service                            | Reason                                                                         |
| ---------------------------------- | ------------------------------------------------------------------------------ |
| agent_platform (excl. api_gateway) | GPU/AI workloads, different scaling profile, already consolidated as one chart |
| obsidian_vault                     | PVC-heavy, git-sidecar, different lifecycle                                    |
| context-forge-gateway              | Cloudflare OAuth flow requires dedicated process                               |
| grimoire                           | Go + Firestore, different language and DB — poor fit                           |
| hikes                              | Batch processing + Cloudflare Pages, no API server                             |
| sextant                            | Dev CLI tool, not a service                                                    |
| advent_of_code                     | Dev tool, not a service                                                        |
