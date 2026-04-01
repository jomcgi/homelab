# Nexus Monolith Design

## Problem

The homelab has accumulated many small services (trips, ships, stargazer, todo_app), each with its own Helm chart, image pipeline, ArgoCD application, and deploy config. This creates operational overhead disproportionate to the simplicity of the services — scope creep through infrastructure sprawl.

## Decision

Consolidate lightweight web apps into a single monolith: one SvelteKit frontend (SSR), one FastAPI backend (internal data layer), one Helm chart, one deploy pipeline. Services get logical isolation via Postgres schemas and colocated service directories, not physical isolation via separate pods.

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
   +-------------------------------+
   | 2 HTTPRoutes with URL Rewrite:|
   |  public.*  → /public/*       |
   |  private.* → /private/*      |
   +-------------------------------+
        |
   +----+------------------------------+
   |       Monolith Pod (N replicas)   |
   |                                   |
   |  +-----------------------------+  |
   |  | SvelteKit (adapter-node)    |  |
   |  | :3000 ← K8s Service        |  |
   |  |                             |  |
   |  | /public/ships/   (SSR)      |  |
   |  | /private/home/   (SSR)      |  |
   |  |                             |  |
   |  | +page.server.js calls:      |  |
   |  |   fetch("localhost:8000/…") |  |
   |  +-----------------------------+  |
   |                                   |
   |  +-----------------------------+  |
   |  | FastAPI                     |  |
   |  | :8000 ← no K8s Service     |  |
   |  |         (internal only)     |  |
   |  |                             |  |
   |  | /api/home/*                 |  |
   |  | /api/ships/*                |  |
   |  | /healthz                    |  |
   |  +-----------------------------+  |
   |              |                    |
   +--------------+--------------------+
                  |
   +--------------+--+
   |  CloudNativePG  |    +----------+
   | (Postgres)      |    |   NATS   |
   | schema: home    |    | (exists) |
   | schema: trips   |    +----------+
   | schema: ships   |
   | schema: stargazer|
   +-----------------+
```

## Key Decisions

### Two-Layer Architecture: SvelteKit + FastAPI

- **SvelteKit** is the only user-facing surface — all HTTP from users hits SvelteKit
- **FastAPI** is an internal data layer — no K8s Service, no gateway route, unreachable from outside the pod
- SvelteKit's `+page.server.js` loads data by calling FastAPI on `localhost:8000` — server-side only, never exposed to the browser
- Users never see JSON APIs — every URL returns a rendered webpage
- Public pages get SSR with data baked in server-side; the browser sees only HTML
- This eliminates API attack surface: there are no public or private API endpoints to probe

### Frontend: SvelteKit SSR with Colocated Service Routes

- Replaces React 19 (trips, ships), vanilla JS (todo), and lightweight Python server (stargazer)
- SvelteKit runs with `adapter-node` for SSR — required for public pages that need data without exposing APIs
- Each service's frontend code lives colocated with its backend (`{service}/frontend/`)
- Service frontend directories declare visibility via `private/` and `public/` subdirectories
- The `format` command generates symlinks from the SvelteKit `src/routes/` tree into each service's frontend directory — service directories are the single source of truth
- Shared components live in `shared/frontend/components/`, symlinked to `src/lib/`
- Public static sites (jomcgi.dev, docs.jomcgi.dev) deploy to Cloudflare Pages — same framework, different deploy target

### Backend: FastAPI (Internal Data Layer)

- Trips and ships are already FastAPI; todo_app migrates from Go
- Single test harness (pytest), single dependency tree, single image
- No visibility middleware — FastAPI is an internal data layer (like Postgres), not user-facing
- Simple routers per service: `/api/home/*`, `/api/ships/*`, `/api/trips/*`
- SvelteKit decides what data to expose on which pages — visibility is a frontend concern

### Database: CloudNativePG + Postgres

- New Postgres instance managed by CloudNativePG operator
- One database, separate schemas per service (`home`, `trips`, `ships`, `stargazer`)
- Stateless app pods — enables `RollingUpdate` with multiple replicas, zero-downtime deploys
- Replaces: SQLite (trips, ships), JSON files (stargazer), git-backed files (todo)

### Schema Migrations: Atlas + SQLModel

- SQLModel classes are the single source of truth for database schema
- `atlas-provider-sqlalchemy` introspects models and generates DDL
- Versioned migrations generated via `atlas migrate diff --env nexus` during development
- Atlas Kubernetes Operator applies pending migrations on deploy via `AtlasMigration` CRD
- Bazel test enforces models and migrations stay in sync: runs `atlas migrate diff` and fails if new migration files are produced

### Gateway Routing: Two-Hostname Model with URL Rewrite

- **`public.jomcgi.dev`** — rate-limited via Envoy BackendTrafficPolicy, cached at Cloudflare edge, no auth
- **`private.jomcgi.dev`** — behind Cloudflare Access SSO (single policy covers all paths), no rate limiting
- Only **two HTTPRoutes** total (one per hostname), regardless of how many services the monolith contains
- Each HTTPRoute uses Gateway API `URLRewrite` (`ReplacePrefixMatch`) to prepend `/public/` or `/private/` to the request path before it reaches SvelteKit
- SvelteKit filesystem routing handles the rest — `src/routes/public/` and `src/routes/private/` directories
- Adding a new service requires zero Cloudflare or gateway config — just add SvelteKit routes and FastAPI data endpoints
- Portfolio (`jomcgi.dev`) and docs (`docs.jomcgi.dev`) remain on Cloudflare Pages, resilient to cluster downtime

#### Path Convention

```
External:                          SvelteKit receives:
public.jomcgi.dev/ships/page   →   /public/ships/page    → src/routes/public/ships/
private.jomcgi.dev/home        →   /private/home         → src/routes/private/home/
private.jomcgi.dev/            →   /private/             → src/routes/private/
```

SvelteKit `+page.server.js` then calls FastAPI internally:

```
fetch("http://localhost:8000/api/home/tasks")   // never exposed to browser
fetch("http://localhost:8000/api/ships")         // never exposed to browser
```

#### Isolation Enforcement

| Layer                       | What it enforces                   | How                                            |
| --------------------------- | ---------------------------------- | ---------------------------------------------- |
| Gateway (Envoy)             | Hostname → path prefix mapping     | URL rewrite prepends `/public/` or `/private/` |
| SvelteKit filesystem        | Which pages exist per visibility   | `src/routes/public/` vs `src/routes/private/`  |
| SvelteKit `+page.server.js` | What data each page shows          | Developer chooses what to fetch from FastAPI   |
| Cloudflare Access           | Authentication on private hostname | SSO policy on `private.jomcgi.dev`             |
| FastAPI                     | Nothing about visibility           | Internal data layer — like Postgres            |

### Deployment

- Single Helm chart at `projects/monolith/chart/`
- Single ArgoCD Application
- ArgoCD Image Updater for both backend and frontend images
- Rolling updates with zero downtime (stateless pods + Postgres)
- Two containers in pod: SvelteKit (`adapter-node`) + FastAPI
- One K8s Service pointing at SvelteKit :3000 only

## New Platform Infrastructure

Two upstream Helm charts, no custom charts:

| Component              | Purpose                       | Chart                           |
| ---------------------- | ----------------------------- | ------------------------------- |
| CloudNativePG Operator | Postgres lifecycle management | `cloudnative-pg/cloudnative-pg` |
| Atlas Operator         | Declarative schema migrations | `ariga/atlas-operator`          |

## Project Structure

```
projects/monolith/
├── home/                         # Home/notes service (colocated backend + frontend)
│   ├── router.py                 # /api/home/* FastAPI routes
│   ├── models.py                 # SQLModel table definitions
│   ├── service.py                # Business logic
│   └── frontend/
│       └── private/              # Pages for private.jomcgi.dev/home
│           ├── +page.svelte
│           └── +page.server.js   # SSR: calls FastAPI on localhost:8000
├── ships/                        # (post-MVP, example of public + private)
│   ├── router.py
│   └── frontend/
│       ├── private/              # Pages for private.jomcgi.dev/ships
│       │   └── +page.svelte
│       └── public/               # Pages for public.jomcgi.dev/ships
│           ├── +page.svelte
│           └── +page.server.js   # SSR: fetches data server-side, no public API
├── shared/
│   ├── scheduler.py              # Reusable scheduling logic
│   └── frontend/
│       └── components/           # Shared Svelte components
│           └── NavBar.svelte
├── app/
│   ├── main.py                   # FastAPI app, mounts service routers
│   └── db.py                     # Database engine + session
├── frontend/                     # SvelteKit shell (routes are generated symlinks)
│   ├── svelte.config.js
│   ├── vite.config.js
│   ├── package.json
│   └── src/
│       ├── app.html
│       ├── routes/               # GENERATED by format — symlinks to service dirs
│       │   ├── private/
│       │   │   └── home/ → ../../../home/frontend/private/
│       │   └── public/
│       │       └── ships/ → ../../../ships/frontend/public/
│       └── lib/ → ../../shared/frontend/components/
├── migrations/                   # Atlas versioned migration files
│   └── atlas.sum                 # Migration integrity file
├── atlas.hcl                     # Atlas config pointing to SQLModel models
├── chart/
│   ├── Chart.yaml
│   └── templates/
│       ├── deployment.yaml       # 2-container pod (SvelteKit + FastAPI)
│       ├── service.yaml          # K8s Service → SvelteKit :3000 only
│       ├── httproute-public.yaml # public.jomcgi.dev → rewrite /public/*
│       ├── httproute-private.yaml# private.jomcgi.dev → rewrite /private/*
│       ├── cnpg-cluster.yaml     # CloudNativePG Cluster CRD
│       └── atlas-migration.yaml  # AtlasMigration CRD
├── deploy/
│   ├── application.yaml          # ArgoCD Application
│   ├── kustomization.yaml
│   ├── values.yaml
│   └── imageupdater.yaml
└── BUILD
```

### Route Symlink Generation

The `format` command generates symlinks from each service's `frontend/` directory into the SvelteKit `src/routes/` tree. This runs as part of the existing format pipeline (same pattern as gazelle BUILD file generation).

```bash
# Scans projects/monolith/*/frontend/{private,public}/ directories
# Creates symlinks: frontend/src/routes/{visibility}/{service}/ → {service}/frontend/{visibility}/
# Also links: frontend/src/lib/ → shared/frontend/components/
```

Adding a new service: create `{service}/frontend/private/+page.svelte`, run `format`, commit the symlink. Zero boilerplate elsewhere.

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

The gateway rewrites paths based on hostname — `public.jomcgi.dev/*` → `/public/*`, `private.jomcgi.dev/*` → `/private/*`. Both route to SvelteKit on port 3000:

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

**Goal:** Home service (notes/calendar) on private + empty public homepage — proves the full public/private stack end-to-end.

### MVP Deliverables

1. **Platform:** CloudNativePG operator + Atlas operator (upstream charts)
2. **Monolith backend:** FastAPI with `home` router, SQLModel models, scheduler (internal data layer)
3. **Monolith frontend:** SvelteKit SSR with home pages (private) + empty public homepage
4. **Monolith chart:** Helm chart with 2-container pod, CNPG Cluster, AtlasMigration, HTTPRoutes
5. **Monolith deploy:** ArgoCD application, values, image updater config
6. **CI:** Bazel test for migration drift, image build rules, route symlink generation in `format`
7. **Retire:** `projects/todo_app/` removed after migration verified

### What Migrates (todo_app → home)

| Current (Go + files)     | MVP (FastAPI + Postgres + SvelteKit)      |
| ------------------------ | ----------------------------------------- |
| `data.json` on PVC       | `home.tasks` table                        |
| `YYYY/MM/DD.md` archives | `home.archives` table                     |
| Git commit on reset      | DB writes only                            |
| Go goroutine scheduler   | Shared scheduler in `shared/`             |
| Nginx sidecar (static)   | SvelteKit SSR container (adapter-node)    |
| Vanilla JS frontend      | SvelteKit (colocated in `home/frontend/`) |

### Internal API Contract (FastAPI, not user-facing)

- `GET /api/home/weekly` — current weekly task
- `GET /api/home/daily` — current daily tasks
- `GET /api/home` — full todo state
- `PUT /api/home` — update todo state
- `POST /api/home/reset/daily` — archive + clear daily
- `POST /api/home/reset/weekly` — archive + clear all
- `GET /api/home/dates` — available archive dates
- `GET /api/home/archive/{date}` — rendered archive for date
- `GET /api/home/schedule/today` — today's calendar events

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
