# Nexus Monolith Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate todo_app into a new "Nexus" monolith — FastAPI backend, SvelteKit frontend, CloudNativePG + Atlas for persistence — proving the full stack end-to-end.

**Architecture:** Single pod with two containers (FastAPI + Caddy/SvelteKit), backed by a CloudNativePG Postgres cluster. Atlas operator applies versioned migrations generated from SQLModel classes. Envoy Gateway HTTPRoutes handle public rate limiting and private SSO routing via cf-ingress-library.

**Tech Stack:** Python 3.13, FastAPI, SQLModel, SvelteKit, mdsvex, CloudNativePG, Atlas, Caddy, Helm, Bazel, ArgoCD

**Design doc:** `docs/plans/2026-03-28-nexus-monolith-design.md`

---

## Task 1: Deploy CloudNativePG Operator

Install the CNPG operator as a platform service. This manages Postgres cluster lifecycle.

**Files:**

- Create: `projects/platform/cloudnative-pg/deploy/application.yaml`
- Create: `projects/platform/cloudnative-pg/deploy/kustomization.yaml`
- Create: `projects/platform/cloudnative-pg/deploy/values.yaml`

**Step 1: Create ArgoCD Application for CNPG operator**

Follow the pattern from existing platform services. CNPG publishes a Helm chart.

```yaml
# projects/platform/cloudnative-pg/deploy/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cloudnative-pg
  namespace: argocd
spec:
  project: default
  sources:
    - repoURL: https://cloudnative-pg.github.io/charts
      chart: cloudnative-pg
      targetRevision: 0.23.0
      helm:
        releaseName: cnpg
        valueFiles:
          - $values/projects/platform/cloudnative-pg/deploy/values.yaml
    - repoURL: https://github.com/jomcgi/homelab.git
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: cnpg-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

> **Note:** Check the latest CNPG chart version before using `0.23.0`. Use the Helm repo or their GitHub releases.

**Step 2: Create values.yaml**

```yaml
# projects/platform/cloudnative-pg/deploy/values.yaml
# CloudNativePG operator values
# Defaults are generally fine — override only what's needed
```

**Step 3: Create kustomization.yaml**

```yaml
# projects/platform/cloudnative-pg/deploy/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 4: Run format to regenerate home-cluster kustomization**

```bash
format
```

This runs `bazel/images/generate-home-cluster.sh` which picks up the new kustomization.

**Step 5: Commit**

```bash
git add projects/platform/cloudnative-pg/
git add projects/home-cluster/kustomization.yaml
git commit -m "feat(platform): add CloudNativePG operator"
```

---

## Task 2: Deploy Atlas Operator

Install the Atlas Kubernetes operator as a platform service.

**Files:**

- Create: `projects/platform/atlas-operator/deploy/application.yaml`
- Create: `projects/platform/atlas-operator/deploy/kustomization.yaml`
- Create: `projects/platform/atlas-operator/deploy/values.yaml`

**Step 1: Create ArgoCD Application for Atlas operator**

```yaml
# projects/platform/atlas-operator/deploy/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: atlas-operator
  namespace: argocd
spec:
  project: default
  sources:
    - repoURL: https://atlasgo.io/charts
      chart: atlas-operator
      targetRevision: 0.9.0
      helm:
        releaseName: atlas-operator
        valueFiles:
          - $values/projects/platform/atlas-operator/deploy/values.yaml
    - repoURL: https://github.com/jomcgi/homelab.git
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: atlas-operator-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

> **Note:** Check the latest Atlas operator chart version before using `0.9.0`.

**Step 2: Create values.yaml**

```yaml
# projects/platform/atlas-operator/deploy/values.yaml
# Atlas operator values
# Defaults are generally fine
```

**Step 3: Create kustomization.yaml**

```yaml
# projects/platform/atlas-operator/deploy/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 4: Run format and commit**

```bash
format
git add projects/platform/atlas-operator/
git add projects/home-cluster/kustomization.yaml
git commit -m "feat(platform): add Atlas schema operator"
```

---

## Task 3: Nexus Backend — FastAPI Skeleton + Todo Models

Create the FastAPI app structure with SQLModel models for the todo service.

**Files:**

- Create: `projects/nexus/backend/main.py`
- Create: `projects/nexus/backend/todo/__init__.py`
- Create: `projects/nexus/backend/todo/models.py`
- Create: `projects/nexus/backend/todo/router.py`
- Create: `projects/nexus/backend/todo/scheduler.py`
- Create: `projects/nexus/backend/db.py`

**Reference:**

- Current todo API contract: `projects/todo_app/cmd/main.go` (lines 43-63)
- FastAPI patterns: `projects/trips/backend/main.py`, `projects/ships/backend/main.py`
- OTEL instrumentation: try/except import pattern from trips/ships

**Step 1: Create database connection module**

```python
# projects/nexus/backend/db.py
import os
from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://app:app@localhost:5432/nexus"
)

engine = create_engine(DATABASE_URL)


def get_session():
    with Session(engine) as session:
        yield session
```

**Step 2: Create todo SQLModel models**

```python
# projects/nexus/backend/todo/models.py
from datetime import date
from sqlmodel import SQLModel, Field


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    __table_args__ = {"schema": "todo"}

    id: int | None = Field(default=None, primary_key=True)
    task: str = ""
    done: bool = False
    kind: str = "daily"  # "daily" or "weekly"
    position: int = 0  # ordering within kind


class Archive(SQLModel, table=True):
    __tablename__ = "archives"
    __table_args__ = {"schema": "todo"}

    id: int | None = Field(default=None, primary_key=True)
    date: date
    content: str  # rendered markdown
```

**Step 3: Create todo router**

Preserve the existing API contract from the Go app. Routes are namespaced under `/api/todo`.

```python
# projects/nexus/backend/todo/router.py
import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from .models import Task, Archive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/todo", tags=["todo"])

ROLLING_WINDOW_DAYS = 14


class TaskResponse(BaseModel):
    task: str
    done: bool


class TodoData(BaseModel):
    weekly: TaskResponse
    daily: list[TaskResponse]


@router.get("/weekly")
def get_weekly(session: Session = Depends(get_session)) -> TaskResponse:
    task = session.exec(
        select(Task).where(Task.kind == "weekly")
    ).first()
    if not task:
        return TaskResponse(task="", done=False)
    return TaskResponse(task=task.task, done=task.done)


@router.get("/daily")
def get_daily(session: Session = Depends(get_session)) -> list[TaskResponse]:
    tasks = session.exec(
        select(Task).where(Task.kind == "daily").order_by(Task.position)
    ).all()
    if not tasks:
        return [TaskResponse(task="", done=False) for _ in range(3)]
    return [TaskResponse(task=t.task, done=t.done) for t in tasks]


@router.get("")
def get_todo(session: Session = Depends(get_session)) -> TodoData:
    weekly = session.exec(
        select(Task).where(Task.kind == "weekly")
    ).first()
    daily = session.exec(
        select(Task).where(Task.kind == "daily").order_by(Task.position)
    ).all()
    return TodoData(
        weekly=TaskResponse(
            task=weekly.task if weekly else "",
            done=weekly.done if weekly else False,
        ),
        daily=[TaskResponse(task=t.task, done=t.done) for t in daily]
        or [TaskResponse(task="", done=False) for _ in range(3)],
    )


@router.put("")
def update_todo(
    data: TodoData, session: Session = Depends(get_session)
) -> None:
    # Clear existing tasks
    existing = session.exec(select(Task)).all()
    for t in existing:
        session.delete(t)

    # Write weekly
    session.add(Task(task=data.weekly.task, done=data.weekly.done, kind="weekly", position=0))

    # Write daily
    for i, d in enumerate(data.daily):
        session.add(Task(task=d.task, done=d.done, kind="daily", position=i))

    session.commit()


@router.get("/dates")
def get_dates(session: Session = Depends(get_session)) -> list[str]:
    cutoff = date.today() - timedelta(days=ROLLING_WINDOW_DAYS)
    archives = session.exec(
        select(Archive.date)
        .where(Archive.date >= cutoff)
        .order_by(Archive.date)
    ).all()
    dates = [d.isoformat() for d in archives]
    today = date.today().isoformat()
    if not dates or dates[-1] != today:
        dates.append(today)
    return dates


@router.get("/archive/{archive_date}")
def get_archive(
    archive_date: str, session: Session = Depends(get_session)
) -> dict:
    try:
        d = date.fromisoformat(archive_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format") from exc
    archive = session.exec(
        select(Archive).where(Archive.date == d)
    ).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    return {"date": archive.date.isoformat(), "content": archive.content}


@router.post("/reset/daily")
def reset_daily(session: Session = Depends(get_session)) -> None:
    _archive_and_reset(session, weekly_reset=False)


@router.post("/reset/weekly")
def reset_weekly(session: Session = Depends(get_session)) -> None:
    _archive_and_reset(session, weekly_reset=True)


def _archive_and_reset(session: Session, weekly_reset: bool) -> None:
    """Archive current state to markdown, then reset tasks."""
    weekly = session.exec(select(Task).where(Task.kind == "weekly")).first()
    daily = session.exec(
        select(Task).where(Task.kind == "daily").order_by(Task.position)
    ).all()

    # Build markdown archive
    today = date.today()
    lines = [f"# {today.strftime('%A, %B %-d')}\n"]
    lines.append("## Weekly")
    lines.append(weekly.task if weekly and weekly.task else "(none)")
    lines.append("")
    lines.append("## Daily")
    for t in daily:
        if t.task:
            check = "x" if t.done else " "
            lines.append(f"- [{check}] {t.task}")

    session.add(Archive(date=today, content="\n".join(lines)))

    # Clear tasks
    existing = session.exec(select(Task)).all()
    for t in existing:
        session.delete(t)

    if not weekly_reset and weekly:
        # Keep weekly task on daily reset
        session.add(Task(task=weekly.task, done=weekly.done, kind="weekly", position=0))

    # Add empty daily slots
    for i in range(3):
        session.add(Task(task="", done=False, kind="daily", position=i))

    session.commit()
    logger.info("Reset completed (weekly=%s)", weekly_reset)
```

**Step 4: Create scheduler**

```python
# projects/nexus/backend/todo/scheduler.py
import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session

from ..db import engine
from .router import _archive_and_reset

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Los_Angeles")


async def run_scheduler() -> None:
    """Run daily/weekly reset at midnight Pacific."""
    while True:
        now = datetime.now(TZ)
        next_midnight = datetime.combine(
            now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
        )
        sleep_seconds = (next_midnight - now).total_seconds()
        logger.info(
            "Scheduler: next reset at %s (sleeping %.0fs)",
            next_midnight.isoformat(),
            sleep_seconds,
        )
        await asyncio.sleep(sleep_seconds)

        reset_time = datetime.now(TZ)
        weekly = reset_time.weekday() == 5  # Saturday = end of Friday
        logger.info("Scheduler: triggering %s reset", "weekly" if weekly else "daily")

        with Session(engine) as session:
            _archive_and_reset(session, weekly_reset=weekly)
```

**Step 5: Create empty **init**.py**

```python
# projects/nexus/backend/todo/__init__.py
```

**Step 6: Create FastAPI main app**

```python
# projects/nexus/backend/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .todo.router import router as todo_router
from .todo.scheduler import run_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    scheduler_task = asyncio.create_task(run_scheduler())
    logger.info("Nexus started")
    yield
    scheduler_task.cancel()
    logger.info("Nexus shutting down")


app = FastAPI(title="Nexus", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(todo_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# OTEL instrumentation (optional — enabled by auto-instrumentation annotation)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry instrumentation enabled")
except ImportError:
    logger.info("OpenTelemetry not available, skipping instrumentation")
```

**Step 7: Commit**

```bash
git add projects/nexus/backend/
git commit -m "feat(nexus): add FastAPI backend with todo routes and SQLModel models"
```

---

## Task 4: Nexus Backend — Tests

Write tests for the todo router. Tests run in CI via Bazel, not locally.

**Files:**

- Create: `projects/nexus/backend/todo/router_test.py`
- Create: `projects/nexus/backend/todo/scheduler_test.py`

**Reference:**

- Test patterns: `projects/todo_app/cmd/main_test.go`, `projects/trips/backend/main_test.py`
- Bazel test rule: `//bazel/tools/pytest:defs.bzl` (`py_test`)

**Step 1: Write router tests**

Use an in-memory SQLite for test speed. SQLModel supports this.

```python
# projects/nexus/backend/todo/router_test.py
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from ..db import get_session
from ..main import app
from .models import Archive, Task


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create the todo schema tables — SQLite ignores schema prefixes
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_weekly_empty(client):
    response = client.get("/api/todo/weekly")
    assert response.status_code == 200
    assert response.json() == {"task": "", "done": False}


def test_get_daily_empty(client):
    response = client.get("/api/todo/daily")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(d["task"] == "" for d in data)


def test_put_and_get_todo(client):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [
            {"task": "Write tests", "done": True},
            {"task": "Review PR", "done": False},
        ],
    }
    response = client.put("/api/todo", json=todo)
    assert response.status_code == 200

    response = client.get("/api/todo")
    assert response.status_code == 200
    data = response.json()
    assert data["weekly"]["task"] == "Ship feature"
    assert len(data["daily"]) == 2
    assert data["daily"][0]["done"] is True


def test_reset_daily_preserves_weekly(client, session):
    # Set up tasks
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [{"task": "Write tests", "done": True}],
    }
    client.put("/api/todo", json=todo)

    # Reset daily
    response = client.post("/api/todo/reset/daily")
    assert response.status_code == 200

    # Weekly should be preserved
    data = client.get("/api/todo").json()
    assert data["weekly"]["task"] == "Ship feature"
    # Daily should be cleared
    assert all(d["task"] == "" for d in data["daily"])


def test_reset_weekly_clears_all(client, session):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [{"task": "Write tests", "done": True}],
    }
    client.put("/api/todo", json=todo)

    response = client.post("/api/todo/reset/weekly")
    assert response.status_code == 200

    data = client.get("/api/todo").json()
    assert data["weekly"]["task"] == ""
    assert all(d["task"] == "" for d in data["daily"])


def test_reset_creates_archive(client, session):
    todo = {
        "weekly": {"task": "Ship feature", "done": False},
        "daily": [{"task": "Write tests", "done": True}],
    }
    client.put("/api/todo", json=todo)
    client.post("/api/todo/reset/daily")

    today = date.today().isoformat()
    response = client.get(f"/api/todo/archive/{today}")
    assert response.status_code == 200
    assert "Ship feature" in response.json()["content"]
    assert "[x] Write tests" in response.json()["content"]


def test_get_dates_includes_today(client):
    response = client.get("/api/todo/dates")
    assert response.status_code == 200
    dates = response.json()
    assert date.today().isoformat() in dates


def test_get_archive_not_found(client):
    response = client.get("/api/todo/archive/2020-01-01")
    assert response.status_code == 404


def test_get_archive_invalid_date(client):
    response = client.get("/api/todo/archive/not-a-date")
    assert response.status_code == 400
```

**Step 2: Write scheduler tests**

```python
# projects/nexus/backend/todo/scheduler_test.py
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from .scheduler import TZ


@pytest.mark.asyncio
async def test_scheduler_calculates_next_midnight():
    """Verify scheduler sleeps until next midnight Pacific."""
    from .scheduler import run_scheduler

    mock_now = datetime(2026, 3, 28, 22, 0, 0, tzinfo=TZ)

    with (
        patch("projects.nexus.backend.todo.scheduler.datetime") as mock_dt,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("projects.nexus.backend.todo.scheduler._archive_and_reset"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        # Let it run once then break
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await run_scheduler()

        # Should sleep ~2 hours (22:00 to 00:00)
        sleep_seconds = mock_sleep.call_args_list[0][0][0]
        assert 7100 < sleep_seconds < 7300  # ~2 hours
```

**Step 3: Commit**

```bash
git add projects/nexus/backend/todo/router_test.py
git add projects/nexus/backend/todo/scheduler_test.py
git commit -m "test(nexus): add todo router and scheduler tests"
```

---

## Task 5: Atlas Migrations Setup

Configure Atlas with SQLModel provider and generate initial migration.

**Files:**

- Create: `projects/nexus/atlas.hcl`
- Create: `projects/nexus/migrations/` (generated by atlas)

**Step 1: Add atlas-provider-sqlalchemy to Python requirements**

Add to `bazel/requirements/requirements.in`:

```
atlas-provider-sqlalchemy
```

Then regenerate the lock file.

**Step 2: Create atlas.hcl**

```hcl
# projects/nexus/atlas.hcl
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

**Step 3: Generate initial migration**

```bash
cd projects/nexus
atlas migrate diff initial --env nexus
```

This creates `migrations/YYYYMMDDHHMMSS_initial.sql` and `migrations/atlas.sum`.

**Step 4: Verify migration content**

The generated SQL should contain:

```sql
CREATE SCHEMA IF NOT EXISTS todo;
CREATE TABLE todo.tasks (...);
CREATE TABLE todo.archives (...);
```

**Step 5: Commit**

```bash
git add projects/nexus/atlas.hcl
git add projects/nexus/migrations/
git commit -m "feat(nexus): add Atlas migration config and initial schema"
```

---

## Task 6: SvelteKit Frontend Skeleton

Create the SvelteKit app with todo pages. Uses `adapter-static` for Caddy serving.

**Files:**

- Create: `projects/nexus/frontend/package.json`
- Create: `projects/nexus/frontend/svelte.config.js`
- Create: `projects/nexus/frontend/vite.config.js`
- Create: `projects/nexus/frontend/src/app.html`
- Create: `projects/nexus/frontend/src/routes/+layout.svelte`
- Create: `projects/nexus/frontend/src/routes/todo/+page.svelte`
- Create: `projects/nexus/frontend/src/routes/todo/+page.js`
- Create: `projects/nexus/frontend/src/routes/todo/admin/+page.svelte`
- Create: `projects/nexus/frontend/src/routes/todo/admin/+page.js`
- Create: `projects/nexus/frontend/static/favicon.svg`

**Step 1: Create package.json**

```json
{
  "name": "nexus-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.0.0",
    "svelte": "^5.0.0",
    "mdsvex": "^0.12.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "@sveltejs/vite-plugin-svelte": "^4.0.0"
  }
}
```

**Step 2: Create svelte.config.js**

```javascript
// projects/nexus/frontend/svelte.config.js
import adapter from "@sveltejs/adapter-static";
import { mdsvex } from "mdsvex";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  extensions: [".svelte", ".svx"],
  preprocess: [mdsvex()],
  kit: {
    adapter: adapter({
      fallback: "index.html",
    }),
    paths: {
      base: "",
    },
  },
};

export default config;
```

**Step 3: Create vite.config.js**

```javascript
// projects/nexus/frontend/vite.config.js
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

**Step 4: Create app.html shell**

```html
<!-- projects/nexus/frontend/src/app.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" href="%sveltekit.assets%/favicon.svg" />
    %sveltekit.head%
  </head>
  <body>
    %sveltekit.body%
  </body>
</html>
```

**Step 5: Create layout**

```svelte
<!-- projects/nexus/frontend/src/routes/+layout.svelte -->
<script>
  let { children } = $props();
</script>

<nav>
  <a href="/todo">Todo</a>
</nav>

<main>
  {@render children()}
</main>

<style>
  nav {
    padding: 1rem;
    border-bottom: 1px solid #e0e0e0;
  }
  nav a {
    margin-right: 1rem;
    text-decoration: none;
    color: #333;
  }
  main {
    padding: 1rem;
    max-width: 800px;
    margin: 0 auto;
  }
</style>
```

**Step 6: Create todo public page (read-only view)**

```javascript
// projects/nexus/frontend/src/routes/todo/+page.js
export async function load({ fetch }) {
  const [todoRes, datesRes] = await Promise.all([
    fetch("/api/todo"),
    fetch("/api/todo/dates"),
  ]);
  return {
    todo: await todoRes.json(),
    dates: await datesRes.json(),
  };
}
```

```svelte
<!-- projects/nexus/frontend/src/routes/todo/+page.svelte -->
<script>
  let { data } = $props();
</script>

<h1>Todo</h1>

<section>
  <h2>Weekly</h2>
  <p>{data.todo.weekly.task || "(none)"}</p>
</section>

<section>
  <h2>Daily</h2>
  <ul>
    {#each data.todo.daily as task}
      <li class:done={task.done}>
        <input type="checkbox" checked={task.done} disabled />
        {task.task || "(empty)"}
      </li>
    {/each}
  </ul>
</section>

<section>
  <h2>History</h2>
  <ul>
    {#each data.dates as d}
      <li><a href="/todo/archive/{d}">{d}</a></li>
    {/each}
  </ul>
</section>

<style>
  .done { text-decoration: line-through; opacity: 0.6; }
  ul { list-style: none; padding: 0; }
  li { padding: 0.25rem 0; }
</style>
```

**Step 7: Create todo admin page (edit view)**

```javascript
// projects/nexus/frontend/src/routes/todo/admin/+page.js
export async function load({ fetch }) {
  const res = await fetch("/api/todo");
  return { todo: await res.json() };
}
```

```svelte
<!-- projects/nexus/frontend/src/routes/todo/admin/+page.svelte -->
<script>
  let { data } = $props();
  let todo = $state(structuredClone(data.todo));
  let saving = $state(false);

  async function save() {
    saving = true;
    await fetch("/api/todo", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(todo),
    });
    saving = false;
  }

  async function resetDaily() {
    if (!confirm("Reset daily tasks?")) return;
    await fetch("/api/todo/reset/daily", { method: "POST" });
    const res = await fetch("/api/todo");
    todo = await res.json();
  }

  async function resetWeekly() {
    if (!confirm("Reset ALL tasks?")) return;
    await fetch("/api/todo/reset/weekly", { method: "POST" });
    const res = await fetch("/api/todo");
    todo = await res.json();
  }
</script>

<h1>Todo Admin</h1>

<section>
  <h2>Weekly</h2>
  <label>
    <input type="checkbox" bind:checked={todo.weekly.done} />
    <input type="text" bind:value={todo.weekly.task} placeholder="Weekly goal..." />
  </label>
</section>

<section>
  <h2>Daily</h2>
  {#each todo.daily as task, i}
    <label>
      <input type="checkbox" bind:checked={task.done} />
      <input type="text" bind:value={task.task} placeholder="Task {i + 1}..." />
    </label>
  {/each}
</section>

<div class="actions">
  <button onclick={save} disabled={saving}>
    {saving ? "Saving..." : "Save"}
  </button>
  <button onclick={resetDaily}>Reset Daily</button>
  <button onclick={resetWeekly}>Reset Weekly</button>
</div>

<style>
  label { display: flex; align-items: center; gap: 0.5rem; margin: 0.5rem 0; }
  input[type="text"] { flex: 1; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
  .actions { margin-top: 1rem; display: flex; gap: 0.5rem; }
  button { padding: 0.5rem 1rem; border-radius: 4px; border: 1px solid #ccc; cursor: pointer; }
</style>
```

**Step 8: Install dependencies and commit**

```bash
cd projects/nexus/frontend && pnpm install
git add projects/nexus/frontend/
git commit -m "feat(nexus): add SvelteKit frontend with todo pages"
```

---

## Task 7: Caddy Configuration

Configure Caddy as the frontend sidecar — serves SvelteKit static build and proxies `/api/*` to FastAPI.

**Files:**

- Create: `projects/nexus/caddy/Caddyfile`

**Step 1: Create Caddyfile**

```
# projects/nexus/caddy/Caddyfile
:3000 {
    # Proxy API requests to FastAPI sidecar
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Proxy healthz to FastAPI
    handle /healthz {
        reverse_proxy localhost:8000
    }

    # Serve SvelteKit static build
    handle {
        root * /srv
        try_files {path} {path}/ /index.html
        file_server
    }
}
```

**Step 2: Commit**

```bash
git add projects/nexus/caddy/
git commit -m "feat(nexus): add Caddy config for frontend serving and API proxying"
```

---

## Task 8: Nexus Helm Chart

Create the Helm chart with deployment, services, CNPG Cluster, AtlasMigration, and HTTPRoutes.

**Files:**

- Create: `projects/nexus/chart/Chart.yaml`
- Create: `projects/nexus/chart/values.yaml`
- Create: `projects/nexus/chart/templates/_helpers.tpl`
- Create: `projects/nexus/chart/templates/deployment.yaml`
- Create: `projects/nexus/chart/templates/service.yaml`
- Create: `projects/nexus/chart/templates/cnpg-cluster.yaml`
- Create: `projects/nexus/chart/templates/atlas-migration.yaml`
- Create: `projects/nexus/chart/templates/migrations-configmap.yaml`
- Create: `projects/nexus/chart/templates/httproute-todo-public.yaml`
- Create: `projects/nexus/chart/templates/httproute-todo-admin.yaml`

**Reference:**

- Chart pattern: `projects/trips/chart/`, `projects/ships/chart/`
- HTTPRoute pattern: `projects/todo_app/deploy/templates/httproute-*.yaml`
- cf-ingress-library: `projects/platform/cf-ingress-library/`
- homelab-library: `projects/shared/helm/homelab-library/chart/`

**Step 1: Create Chart.yaml**

```yaml
# projects/nexus/chart/Chart.yaml
apiVersion: v2
name: nexus
description: Consolidated homelab web services
version: 0.1.0
type: application
dependencies:
  - name: cf-ingress-library
    version: 0.1.0
    repository: "file://../../platform/cf-ingress-library"
```

**Step 2: Create values.yaml**

```yaml
# projects/nexus/chart/values.yaml
backend:
  replicas: 1
  image:
    repository: ghcr.io/jomcgi/homelab/projects/nexus/backend
    tag: main
    pullPolicy: IfNotPresent
  resources:
    requests:
      memory: "64Mi"
      cpu: "10m"
    limits:
      memory: "128Mi"

frontend:
  image:
    repository: ghcr.io/jomcgi/homelab/projects/nexus/frontend
    tag: main
    pullPolicy: IfNotPresent
  resources:
    requests:
      memory: "32Mi"
      cpu: "5m"
    limits:
      memory: "64Mi"

postgres:
  instances: 1
  storage:
    size: 2Gi
    storageClass: ""

service:
  port: 3000

podSecurityContext:
  seccompProfile:
    type: RuntimeDefault

securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL

cfIngress:
  todo:
    public:
      enabled: true
      tier: public
      hostname: todo.jomcgi.dev
      servicePort: 3000
      gateway:
        name: cloudflare-ingress
        namespace: envoy-gateway-system
      rateLimit:
        requests: 100
        unit: Minute
    admin:
      enabled: true
      tier: trusted
      hostname: todo-admin.jomcgi.dev
      servicePort: 3000
      gateway:
        name: cloudflare-ingress
        namespace: envoy-gateway-system
      team: jomcgi
```

**Step 3: Create \_helpers.tpl**

```yaml
# projects/nexus/chart/templates/_helpers.tpl
{{- define "nexus.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nexus.labels" -}}
app.kubernetes.io/name: nexus
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "nexus.selectorLabels" -}}
app.kubernetes.io/name: nexus
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
```

**Step 4: Create deployment.yaml (2-container pod)**

```yaml
# projects/nexus/chart/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "nexus.fullname" . }}
  labels:
    {{- include "nexus.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.backend.replicas }}
  selector:
    matchLabels:
      {{- include "nexus.selectorLabels" . | nindent 6 }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        {{- include "nexus.selectorLabels" . | nindent 8 }}
      annotations:
        instrumentation.opentelemetry.io/inject-python: "python"
    spec:
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: backend
          image: "{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}"
          imagePullPolicy: {{ .Values.backend.image.pullPolicy }}
          ports:
            - name: api
              containerPort: 8000
              protocol: TCP
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "nexus.fullname" . }}-pg-app
                  key: uri
          command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
          livenessProbe:
            httpGet:
              path: /healthz
              port: api
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /healthz
              port: api
            initialDelaySeconds: 3
            periodSeconds: 5
          resources:
            {{- toYaml .Values.backend.resources | nindent 12 }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
        - name: frontend
          image: "{{ .Values.frontend.image.repository }}:{{ .Values.frontend.image.tag }}"
          imagePullPolicy: {{ .Values.frontend.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 3000
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 3
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
          resources:
            {{- toYaml .Values.frontend.resources | nindent 12 }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
```

**Step 5: Create service.yaml**

```yaml
# projects/nexus/chart/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: { { include "nexus.fullname" . } }
  labels: { { - include "nexus.labels" . | nindent 4 } }
spec:
  type: ClusterIP
  ports:
    - name: http
      port: { { .Values.service.port } }
      targetPort: http
      protocol: TCP
  selector: { { - include "nexus.selectorLabels" . | nindent 4 } }
```

**Step 6: Create cnpg-cluster.yaml**

```yaml
# projects/nexus/chart/templates/cnpg-cluster.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: {{ include "nexus.fullname" . }}-pg
  labels:
    {{- include "nexus.labels" . | nindent 4 }}
spec:
  instances: {{ .Values.postgres.instances }}
  storage:
    size: {{ .Values.postgres.storage.size }}
    {{- if .Values.postgres.storage.storageClass }}
    storageClassName: {{ .Values.postgres.storage.storageClass }}
    {{- end }}
  postgresql:
    parameters:
      shared_buffers: "64MB"
      effective_cache_size: "128MB"
  bootstrap:
    initdb:
      database: nexus
      owner: app
```

**Step 7: Create migrations ConfigMap and AtlasMigration**

The migrations are packaged into the chart via Helm's `.Files.Glob`. Copy the migrations directory into the chart at build time.

```yaml
# projects/nexus/chart/templates/migrations-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "nexus.fullname" . }}-migrations
  labels:
    {{- include "nexus.labels" . | nindent 4 }}
data:
  {{- range $path, $_ := .Files.Glob "migrations/*.sql" }}
  {{ base $path }}: |
    {{- $.Files.Get $path | nindent 4 }}
  {{- end }}
  atlas.sum: |
    {{- .Files.Get "migrations/atlas.sum" | nindent 4 }}
```

```yaml
# projects/nexus/chart/templates/atlas-migration.yaml
apiVersion: db.atlasgo.io/v1alpha1
kind: AtlasMigration
metadata:
  name: {{ include "nexus.fullname" . }}
  labels:
    {{- include "nexus.labels" . | nindent 4 }}
spec:
  url:
    secretKeyRef:
      name: {{ include "nexus.fullname" . }}-pg-app
      key: uri
  dir:
    configMapRef:
      name: {{ include "nexus.fullname" . }}-migrations
```

**Step 8: Create HTTPRoute templates**

```yaml
# projects/nexus/chart/templates/httproute-todo-public.yaml
{{- if .Values.cfIngress.todo.public.enabled }}
{{- $params := dict
  "name" (printf "%s-todo-public" (include "nexus.fullname" .))
  "tier" .Values.cfIngress.todo.public.tier
  "hostname" .Values.cfIngress.todo.public.hostname
  "serviceName" (include "nexus.fullname" .)
  "servicePort" (.Values.cfIngress.todo.public.servicePort | int)
  "gateway" .Values.cfIngress.todo.public.gateway
}}
{{- include "cf-ingress.httproute" $params }}
---
{{- $rlParams := dict
  "name" (printf "%s-todo-public" (include "nexus.fullname" .))
  "rateLimit" .Values.cfIngress.todo.public.rateLimit
}}
{{- include "cf-ingress.rate-limit" $rlParams }}
{{- end }}
```

```yaml
# projects/nexus/chart/templates/httproute-todo-admin.yaml
{{- if .Values.cfIngress.todo.admin.enabled }}
{{- $params := dict
  "name" (printf "%s-todo-admin" (include "nexus.fullname" .))
  "tier" .Values.cfIngress.todo.admin.tier
  "hostname" .Values.cfIngress.todo.admin.hostname
  "serviceName" (include "nexus.fullname" .)
  "servicePort" (.Values.cfIngress.todo.admin.servicePort | int)
  "gateway" .Values.cfIngress.todo.admin.gateway
}}
{{- include "cf-ingress.httproute" $params }}
---
{{- $spParams := dict
  "name" (printf "%s-todo-admin" (include "nexus.fullname" .))
  "team" .Values.cfIngress.todo.admin.team
}}
{{- include "cf-ingress.security-policy" $spParams }}
{{- end }}
```

**Step 9: Build Helm dependencies and validate**

```bash
cd projects/nexus/chart && helm dependency build
helm template nexus . -f values.yaml --debug
```

Verify output contains: Deployment (2 containers), Service, CNPG Cluster, AtlasMigration, ConfigMap, HTTPRoutes, BackendTrafficPolicy, SecurityPolicy.

**Step 10: Commit**

```bash
git add projects/nexus/chart/
git commit -m "feat(nexus): add Helm chart with CNPG, Atlas, and HTTPRoutes"
```

---

## Task 9: Bazel Build Rules

Create BUILD files for the backend image, frontend image, and chart packaging.

**Files:**

- Create: `projects/nexus/backend/BUILD`
- Create: `projects/nexus/frontend/BUILD`
- Create: `projects/nexus/deploy/BUILD`

**Reference:**

- Python image: `projects/trips/backend/BUILD`
- JS build: `projects/websites/jomcgi.dev/BUILD`, `projects/trips/frontend/BUILD`
- Chart packaging: `projects/todo_app/deploy/BUILD`
- py3_image macro: `bazel/tools/oci/py3_image.bzl`

**Step 1: Create backend BUILD**

```starlark
# projects/nexus/backend/BUILD
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_venv_binary(
    name = "main",
    srcs = glob(["**/*.py"], exclude = ["**/*_test.py"]),
    main = "main.py",
    deps = [
        "@pip//fastapi",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//pydantic",
        "@pip//sqlmodel",
        "@pip//uvicorn",
    ],
)

py3_image(
    name = "image",
    binary = "//projects/nexus/backend:main",
    repository = "ghcr.io/jomcgi/homelab/projects/nexus/backend",
)

py_test(
    name = "todo_router_test",
    srcs = ["todo/router_test.py"],
    deps = [
        ":main",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "todo_scheduler_test",
    srcs = ["todo/scheduler_test.py"],
    deps = [
        ":main",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

**Step 2: Create frontend BUILD**

> **Note:** Exact BUILD structure depends on pnpm workspace config. Follow `projects/websites/jomcgi.dev/BUILD` and `projects/trips/frontend/BUILD`. Key targets: `vite_build` for static output, OCI image bundling build + Caddyfile.

```starlark
# projects/nexus/frontend/BUILD
load("//bazel/tools/js:vite_build.bzl", "vite_build")

vite_build(
    name = "build",
    srcs = glob(["src/**/*", "static/**/*"]),
    config = "vite.config.js",
    deps = [
        # SvelteKit deps — exact labels depend on pnpm workspace
    ],
)
```

> **Implementation note:** The frontend OCI image (Caddy + static files) may need a new Bazel macro. Check `bazel/tools/oci/` for existing patterns. If none exists for Caddy-based static serving, create one based on the existing `py3_image` pattern using an apko Caddy base image.

**Step 3: Create deploy BUILD**

```starlark
# projects/nexus/deploy/BUILD
load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    chart = "//projects/nexus/chart",
    images = {
        "backend.image": "//projects/nexus/backend:image.info",
        "frontend.image": "//projects/nexus/frontend:image.info",
    },
    publish = True,
)

argocd_app(
    name = "nexus",
    chart = "projects/nexus/deploy",
    chart_files = ":chart",
    namespace = "nexus",
    release_name = "nexus",
    values_files = [
        "values.yaml",
    ],
)
```

**Step 4: Run format to generate/fix BUILD files**

```bash
format
```

Gazelle will update BUILD files as needed.

**Step 5: Commit**

```bash
git add projects/nexus/backend/BUILD
git add projects/nexus/frontend/BUILD
git add projects/nexus/deploy/BUILD
git commit -m "build(nexus): add Bazel rules for backend, frontend, and chart"
```

---

## Task 10: ArgoCD Deploy Configuration

Create the ArgoCD Application and deploy values.

**Files:**

- Create: `projects/nexus/deploy/application.yaml`
- Create: `projects/nexus/deploy/kustomization.yaml`
- Create: `projects/nexus/deploy/values.yaml`
- Create: `projects/nexus/deploy/imageupdater.yaml`

**Reference:**

- ArgoCD pattern: `projects/todo_app/deploy/application.yaml`
- Image updater: `projects/ships/deploy/imageupdater.yaml`

**Step 1: Create application.yaml**

```yaml
# projects/nexus/deploy/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: nexus
  namespace: argocd
spec:
  project: default
  sources:
    - repoURL: ghcr.io/jomcgi/homelab/charts
      chart: nexus
      targetRevision: 0.1.0
      helm:
        releaseName: nexus
        valueFiles:
          - $values/projects/nexus/deploy/values.yaml
    - repoURL: https://github.com/jomcgi/homelab.git
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: nexus
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

**Step 2: Create kustomization.yaml**

```yaml
# projects/nexus/deploy/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 3: Create deploy values.yaml**

```yaml
# projects/nexus/deploy/values.yaml
backend:
  replicas: 1

postgres:
  instances: 1
  storage:
    size: 2Gi

cfIngress:
  todo:
    public:
      enabled: true
      tier: public
      hostname: todo.jomcgi.dev
      servicePort: 3000
      gateway:
        name: cloudflare-ingress
        namespace: envoy-gateway-system
      rateLimit:
        requests: 100
        unit: Minute
    admin:
      enabled: true
      tier: trusted
      hostname: todo-admin.jomcgi.dev
      servicePort: 3000
      gateway:
        name: cloudflare-ingress
        namespace: envoy-gateway-system
      team: jomcgi
```

**Step 4: Create imageupdater.yaml**

> **Note:** Check `projects/ships/deploy/imageupdater.yaml` for the exact annotation pattern. The image updater annotations may need to go on the Application resource directly rather than a separate file.

```yaml
# projects/nexus/deploy/imageupdater.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: nexus
  namespace: argocd
  annotations:
    argocd-image-updater.argoproj.io/image-list: >-
      backend=ghcr.io/jomcgi/homelab/projects/nexus/backend,
      frontend=ghcr.io/jomcgi/homelab/projects/nexus/frontend
    argocd-image-updater.argoproj.io/backend.update-strategy: digest
    argocd-image-updater.argoproj.io/frontend.update-strategy: digest
    argocd-image-updater.argoproj.io/backend.helm.image-name: backend.image.repository
    argocd-image-updater.argoproj.io/backend.helm.image-tag: backend.image.tag
    argocd-image-updater.argoproj.io/frontend.helm.image-name: frontend.image.repository
    argocd-image-updater.argoproj.io/frontend.helm.image-tag: frontend.image.tag
```

**Step 5: Run format and commit**

```bash
format
git add projects/nexus/deploy/
git add projects/home-cluster/kustomization.yaml
git commit -m "feat(nexus): add ArgoCD application and deploy config"
```

---

## Task 11: Migration Drift Bazel Test

Create a Bazel test that fails if SQLModel models are out of sync with the migrations directory.

**Files:**

- Create: `projects/nexus/migration_drift_test.py`
- Modify: `projects/nexus/backend/BUILD` (add test target)

**Step 1: Create drift detection test**

> **Note:** The exact approach depends on whether `atlas` CLI is available in the Bazel sandbox. If not, use a Python-based approach that compares the current SQLModel metadata against the last migration. Determine the best approach during implementation.

A Python-based approach that doesn't require atlas CLI in CI:

```python
# projects/nexus/migration_drift_test.py
"""Verify SQLModel models match the migrations directory.

Runs atlas-provider-sqlalchemy to get current DDL from models,
then checks that no new migration would be generated.
"""
import subprocess
import sys


def test_no_migration_drift():
    """atlas migrate diff should produce no new files."""
    result = subprocess.run(
        ["atlas", "migrate", "diff", "--env", "nexus", "--dry-run"],
        capture_output=True,
        text=True,
        cwd="projects/nexus",
    )
    assert result.returncode == 0, f"atlas migrate diff failed: {result.stderr}"
    assert not result.stdout.strip(), (
        f"Migration drift detected! Run: cd projects/nexus && atlas migrate diff --env nexus\n"
        f"Output: {result.stdout}"
    )
```

**Step 2: Add test target to BUILD**

```starlark
# Add to projects/nexus/backend/BUILD or a top-level projects/nexus/BUILD
sh_test(
    name = "migration_drift_test",
    srcs = ["migration_drift_test.py"],
    data = [
        "atlas.hcl",
        "//projects/nexus/backend:main",
    ] + glob(["migrations/**"]),
    tags = ["requires-atlas"],
)
```

> **Implementation note:** The exact Bazel integration depends on whether atlas is available as a toolchain. May need to vendor the atlas binary or use a container-based test. Adapt during implementation.

**Step 3: Commit**

```bash
git add projects/nexus/migration_drift_test.py
git commit -m "test(nexus): add migration drift detection test"
```

---

## Task 12: Validate and Push

Final validation before creating the PR.

**Step 1: Render Helm templates and verify**

```bash
cd projects/nexus/chart
helm dependency build
helm template nexus . -f values.yaml -f ../deploy/values.yaml
```

Verify output contains: Deployment (2 containers), Service, CNPG Cluster, AtlasMigration, ConfigMap, HTTPRoutes, BackendTrafficPolicy, SecurityPolicy.

**Step 2: Push and create PR**

```bash
git push -u origin feat/nexus-mvp
gh pr create --title "feat: nexus monolith MVP with todo migration" --body "..."
```

**Step 3: Monitor CI**

Watch CI and fix any build/test/lint failures.

---

## Task 13: Deploy and Verify

After CI passes and PR merges, verify the deployment.

**Step 1: Verify operators are running**

Use MCP tools:

- `kubernetes-mcp-pods-list` in `cnpg-system` namespace
- `kubernetes-mcp-pods-list` in `atlas-operator-system` namespace

**Step 2: Verify nexus deployment**

- `argocd-mcp-get-application` for `nexus`
- `kubernetes-mcp-pods-list` in `nexus` namespace
- Check CNPG cluster status via `kubernetes-mcp-resources-get`

**Step 3: Verify routes**

- Test public endpoint at `todo.jomcgi.dev`
- Test admin endpoint at `todo-admin.jomcgi.dev` (requires SSO)

**Step 4: Retire old todo_app**

Once verified working:

```bash
git rm -r projects/todo_app/deploy/
format
git add projects/home-cluster/kustomization.yaml
git commit -m "chore: retire todo_app in favor of nexus monolith"
```

> Keep `projects/todo_app/cmd/` temporarily for reference. Remove in a follow-up cleanup PR.
