# Modular Monolith: Domain Registration & Boundary Enforcement

## Problem

`app/main.py` is a god module that knows intimate details of every domain — Discord bot setup, vault cloning, ClickHouse cache warming, lock sweeps. Domains are assembled at import time with no explicit interface. Cross-domain imports reach into sub-modules freely (`chat/router.py` imports `knowledge.store.KnowledgeStore`).

## Goals

1. Define the app centrally, not at import time.
2. Domains register themselves via a shared `register(app)` interface.
3. Clean module-level exports in `__init__.py` — the "public API" between domains.
4. Enforce conventions with pytest rules.

## Domain Layout

| Domain      | Prefix           | Responsibility                                                              |
| ----------- | ---------------- | --------------------------------------------------------------------------- |
| `home`      | `/api/home`      | Homepage data: schedule, observability topology, stats                      |
| `chat`      | `/api/chat`      | Discord bot, backfill, explore                                              |
| `knowledge` | `/api/knowledge` | Knowledge graph CRUD, search, tasks, dead-letter                            |
| `shared`    | —                | Pure utilities (scheduler, embedding, chunker). No routes, no `register()`. |

## Registration Interface

Each domain exposes `register(app: FastAPI)` in its `__init__.py`. This is the single entry point for wiring routers and lifecycle hooks.

```python
# knowledge/__init__.py
from fastapi import FastAPI

def register(app: FastAPI) -> None:
    from knowledge.router import router
    from knowledge.tasks_router import router as tasks_router
    app.include_router(router)
    app.include_router(tasks_router)
```

`app/main.py` becomes a thin shell:

```python
app = FastAPI(title="Monolith", lifespan=lifespan)

import home, chat, knowledge
home.register(app)
chat.register(app)
knowledge.register(app)
```

## Public Interfaces

Each domain's `__init__.py` exports functions that substitute for internal API calls. Other domains call these instead of reaching into sub-modules.

```python
# knowledge/__init__.py
async def search_notes(session, query_embedding, **kwargs):
    from knowledge.store import KnowledgeStore
    return KnowledgeStore(session).search_notes_with_context(
        query_embedding=query_embedding, **kwargs
    )
```

`chat/router.py` would call `from knowledge import search_notes` instead of `from knowledge.store import KnowledgeStore`.

## Route Prefix Convention

Every `APIRouter` in a domain must use `/api/{domain_name}` as its prefix. This is enforced by pytest.

### Migrations

- `shared/router.py` (`/api/schedule/today`) → `home/` (`/api/home/schedule/today`)
- `observability/router.py` (`/api/public/observability/*`) → `home/` (`/api/home/observability/*`)
- Drop the `public` segment — auth is handled at the Cloudflare layer.

## New `home` Domain

Created by merging:

- Calendar polling from `shared/service.py` → `home/schedule.py`
- Schedule route from `shared/router.py` → `home/router.py`
- Everything from `observability/` → `home/observability/` (or flattened)

`shared/` retains only pure utilities: `scheduler.py`, `embedding.py`, `chunker.py`.

## Pytest Enforcement Rules

Three architectural tests:

### 1. Domain route prefix

Every `APIRouter` in `{domain}/` must have `prefix="/api/{domain_name}..."`.

### 2. Import boundaries

Domain modules may only import from:

- Their own domain
- `shared`
- `app.db`
- Standard library / third-party packages
- Another domain's `__init__.py` exports (not sub-modules like `knowledge.store`)

### 3. Registration interface

Every domain directory (except `shared` and `app`) must define a `register` function in its `__init__.py`.

## Lifespan

The `lifespan()` function in `main.py` currently hardcodes domain startup logic. After this refactor, each domain's `register()` can attach startup/shutdown hooks, and `lifespan()` delegates to them. The exact mechanism (FastAPI events, a simple list of callables, etc.) will be determined during implementation.

## What Does NOT Change

- Bazel BUILD files (updated for new paths but same patterns)
- Helm chart, deploy configs
- Database models, migrations
- The scheduler system in `shared/`
- MCP app setup
