# Modular Monolith Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the monolith into isolated domains with a shared `register(app)` interface, public `__init__.py` exports, and pytest-enforced boundaries.

**Architecture:** Each domain (`home`, `chat`, `knowledge`) exposes `register(app: FastAPI)` in its `__init__.py`. `app/main.py` becomes a thin shell that creates the app and calls each domain's `register()`. Cross-domain calls go through public functions exported from `__init__.py`, not sub-module imports. Three pytest rules enforce the conventions.

**Tech Stack:** Python, FastAPI, pytest, AST analysis (for import boundary enforcement)

**Design doc:** `docs/plans/2026-04-19-modular-monolith-design.md`

**Worktree:** `/tmp/claude-worktrees/modular-monolith` (branch `feat/modular-monolith`)

**Test command:** `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`

---

## Task 1: Write the three pytest architectural enforcement tests

These tests define the rules. They will all fail initially (no domains have `register()` yet, imports violate boundaries, etc.). That's intentional — we fix them in subsequent tasks.

**Files:**

- Create: `projects/monolith/app/architecture_test.py`

**Step 1: Write the architectural tests**

```python
"""Architectural enforcement tests for the modular monolith.

These tests verify three conventions:
1. Every domain exposes a register(app) function in __init__.py.
2. Domain modules only import from allowed sources (not other domains' sub-modules).
3. Every APIRouter in a domain uses /api/{domain_name} as its prefix.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest
from fastapi import APIRouter

# Domain directories relative to the monolith root.
# 'shared' and 'app' are excluded — shared is a utility layer, app is the shell.
_MONOLITH_ROOT = Path(__file__).resolve().parent.parent
_DOMAINS = ["home", "chat", "knowledge"]
_ALLOWED_CROSS_IMPORTS = {"shared", "app"}


class TestDomainRegistration:
    """Every domain must expose a register(app) callable in __init__.py."""

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_domain_has_register_function(self, domain: str):
        mod = importlib.import_module(domain)
        assert hasattr(mod, "register"), (
            f"{domain}/__init__.py must export a 'register' function"
        )
        sig = inspect.signature(mod.register)
        params = list(sig.parameters)
        assert len(params) >= 1, (
            f"{domain}.register() must accept at least one argument (app)"
        )


class TestImportBoundaries:
    """Domain modules must not reach into other domains' sub-modules."""

    @staticmethod
    def _collect_imports(filepath: Path) -> list[str]:
        """Parse a Python file and return all imported module names."""
        source = filepath.read_text()
        tree = ast.parse(source, filename=str(filepath))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
        return modules

    @staticmethod
    def _is_domain_submodule_import(
        importing_domain: str, imported_module: str
    ) -> bool:
        """Return True if imported_module is a sub-module of another domain.

        Allowed:
        - Importing from your own domain (e.g. chat.models inside chat/)
        - Importing from shared or app
        - Importing another domain's top-level (e.g. 'knowledge' — the __init__.py)
        - Importing stdlib / third-party packages

        Forbidden:
        - Importing another domain's sub-module (e.g. 'knowledge.store' inside chat/)
        """
        top_level = imported_module.split(".")[0]

        # Own domain — always OK
        if top_level == importing_domain:
            return False

        # Allowed cross-imports (shared, app)
        if top_level in _ALLOWED_CROSS_IMPORTS:
            return False

        # Another domain's top-level import (just 'knowledge', not 'knowledge.store')
        if top_level in _DOMAINS and imported_module == top_level:
            return False

        # Another domain's sub-module — FORBIDDEN
        if top_level in _DOMAINS and "." in imported_module:
            return True

        # Everything else (stdlib, third-party) — OK
        return False

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_no_cross_domain_submodule_imports(self, domain: str):
        domain_dir = _MONOLITH_ROOT / domain
        if not domain_dir.is_dir():
            pytest.skip(f"{domain}/ directory does not exist yet")

        violations: list[str] = []
        for py_file in sorted(domain_dir.rglob("*.py")):
            # Skip test files — they can import whatever they need
            if py_file.name.endswith("_test.py"):
                continue
            rel = py_file.relative_to(_MONOLITH_ROOT)
            for mod in self._collect_imports(py_file):
                if self._is_domain_submodule_import(domain, mod):
                    violations.append(f"  {rel}: imports '{mod}'")

        assert not violations, (
            f"Domain '{domain}' has forbidden cross-domain sub-module imports:\n"
            + "\n".join(violations)
            + "\n\nUse the domain's __init__.py public API instead "
            + "(e.g. 'from knowledge import search_notes')"
        )


class TestRoutePrefixConvention:
    """Every APIRouter in a domain must use /api/{domain_name} as its prefix."""

    @staticmethod
    def _find_routers_in_module(module) -> list[tuple[str, APIRouter]]:
        """Find all APIRouter instances defined in a module."""
        routers = []
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, APIRouter):
                routers.append((name, obj))
        return routers

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_routers_use_domain_prefix(self, domain: str):
        domain_dir = _MONOLITH_ROOT / domain
        if not domain_dir.is_dir():
            pytest.skip(f"{domain}/ directory does not exist yet")

        violations: list[str] = []
        expected_prefix = f"/api/{domain}"

        for py_file in sorted(domain_dir.rglob("*.py")):
            if py_file.name.endswith("_test.py") or py_file.name == "__init__.py":
                continue
            rel = py_file.relative_to(_MONOLITH_ROOT)
            module_name = str(rel).replace("/", ".").removesuffix(".py")
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                continue
            for attr_name, router in self._find_routers_in_module(mod):
                if not router.prefix.startswith(expected_prefix):
                    violations.append(
                        f"  {rel}:{attr_name} has prefix '{router.prefix}' "
                        f"(expected '{expected_prefix}...')"
                    )

        assert not violations, (
            f"Domain '{domain}' has routers with wrong prefix:\n"
            + "\n".join(violations)
        )
```

**Step 2: Run tests to verify they fail**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:architecture_test --config=ci`
Expected: FAIL — `home` doesn't exist yet, `chat` has cross-domain imports, etc.

**Step 3: Commit the failing tests**

```bash
git add projects/monolith/app/architecture_test.py
git commit -m "test(monolith): add architectural enforcement tests for domain boundaries"
```

---

## Task 2: Create the `home` domain — move schedule + observability

This creates `projects/monolith/home/` by moving and re-prefixing the schedule and observability code.

**Files:**

- Create: `projects/monolith/home/__init__.py`
- Create: `projects/monolith/home/schedule.py` (from `shared/service.py` calendar bits)
- Create: `projects/monolith/home/schedule_router.py` (from `shared/router.py`)
- Move: `projects/monolith/observability/` → `projects/monolith/home/observability/`
- Delete: `projects/monolith/shared/router.py` (schedule route moved)
- Modify: `projects/monolith/shared/service.py` (remove calendar functions, keep `on_startup`)

**Step 1: Create `home/schedule.py`**

Move calendar logic from `shared/service.py`. This is the calendar polling service — event parsing, caching, and the scheduler handler.

```python
"""Calendar service for the home domain — polls an iCal feed and caches today's events."""

import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Vancouver")

_cached_events: list[dict] = []

ICAL_FEED_URL = os.environ.get("ICAL_FEED_URL", "")


def parse_events_for_date(ics_text: str, target_date: date, tz: ZoneInfo) -> list[dict]:
    cal = Calendar.from_ical(ics_text)
    all_day = []
    timed = []
    seen: set[tuple[str | None, str]] = set()

    for component in cal.walk("VEVENT"):
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        dt = dtstart.dt
        summary = str(component.get("SUMMARY", ""))

        if isinstance(dt, date) and not isinstance(dt, datetime):
            if dt == target_date:
                key = (None, summary)
                if key not in seen:
                    seen.add(key)
                    all_day.append({"time": None, "title": summary, "allDay": True})
            continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)

        if dt.date() == target_date:
            time_str = dt.strftime("%H:%M")
            key = (time_str, summary)
            if key not in seen:
                seen.add(key)
                dtend = component.get("DTEND")
                end_str = None
                if dtend is not None:
                    dte = dtend.dt
                    if isinstance(dte, datetime):
                        if dte.tzinfo is None:
                            dte = dte.replace(tzinfo=tz)
                        else:
                            dte = dte.astimezone(tz)
                        end_str = dte.strftime("%H:%M")
                timed.append(
                    {
                        "time": time_str,
                        "endTime": end_str,
                        "title": summary,
                        "allDay": False,
                    }
                )

    timed.sort(key=lambda e: e["time"])
    return all_day + timed


def get_today_events() -> list[dict]:
    return list(_cached_events)


async def poll_calendar() -> None:
    global _cached_events
    if not ICAL_FEED_URL:
        logger.warning("ICAL_FEED_URL not set, skipping calendar poll")
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(ICAL_FEED_URL, timeout=30)
            resp.raise_for_status()
        today = datetime.now(TZ).date()
        _cached_events = parse_events_for_date(resp.text, today, TZ)
        logger.info("Calendar refreshed: %d events for %s", len(_cached_events), today)
    except Exception:
        logger.exception("Failed to fetch calendar feed")


async def calendar_poll_handler() -> None:
    """Scheduler handler for calendar polling (stateless HTTP fetch)."""
    await poll_calendar()
    return None
```

**Step 2: Create `home/schedule_router.py`**

```python
from fastapi import APIRouter

from home.schedule import get_today_events

router = APIRouter(prefix="/api/home/schedule", tags=["home"])


@router.get("/today")
def schedule_today() -> list[dict]:
    return get_today_events()
```

**Step 3: Move `observability/` to `home/observability/`**

```bash
mkdir -p projects/monolith/home/observability
git mv projects/monolith/observability/*.py projects/monolith/home/observability/
rmdir projects/monolith/observability  # remove empty dir if git mv leaves it
```

**Step 4: Update imports in moved observability files**

In `home/observability/router.py`:

- Change `from observability.` → `from home.observability.` (all internal imports)
- Change the router prefix from `"/api/public/observability"` to `"/api/home/observability"`

In `home/observability/topology_config.py`:

- Change `from observability.config import` → `from home.observability.config import`

In `home/observability/stats.py`:

- Imports from `app.db` and `shared.kubernetes` stay the same (allowed)

**Step 5: Create `home/__init__.py` with `register()` and public exports**

```python
"""Home domain — powers the homepage dashboard (schedule, topology, stats)."""

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    """Register home domain routers with the app."""
    from home.schedule_router import router as schedule_router
    from home.observability.router import router as observability_router

    app.include_router(schedule_router)
    app.include_router(observability_router)


def on_startup_jobs(session) -> None:
    """Register home domain scheduled jobs."""
    from shared.scheduler import register_job
    from home.schedule import calendar_poll_handler

    register_job(
        session,
        name="home.calendar_poll",
        interval_secs=900,
        handler=lambda _: calendar_poll_handler(),
        ttl_secs=120,
    )


# Public API — other domains import these, not sub-modules
def get_today_events() -> list[dict]:
    from home.schedule import get_today_events as _get
    return _get()
```

**Step 6: Clean up `shared/service.py`**

Remove all calendar-related functions (`parse_events_for_date`, `get_today_events`, `poll_calendar`, `calendar_poll_handler`, `TZ`, `ICAL_FEED_URL`, `_cached_events`) and the `on_startup` function. The only remaining file after this should be empty or deleted if nothing else is in it.

Also delete `shared/router.py` (schedule route moved to `home/schedule_router.py`).

**Step 7: Update existing tests**

- Move `shared/router_test.py` → `home/schedule_router_test.py`, update paths from `/api/schedule/today` to `/api/home/schedule/today`
- Move `shared/service_test.py` and related test files → `home/schedule_test.py` (or keep as `home/schedule_*_test.py`), update imports from `shared.service` to `home.schedule`
- Move `observability/*_test.py` → `home/observability/*_test.py`, update imports from `observability.` to `home.observability.`
- Update `observability/router_test.py` paths from `/api/public/observability/` to `/api/home/observability/`
- Move `shared/startup_test.py` if it tests calendar startup registration

**Step 8: Run tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`
Expected: home domain tests pass, architecture test for `home` passes

**Step 9: Commit**

```bash
git add -A projects/monolith/home/ projects/monolith/observability/ projects/monolith/shared/
git commit -m "refactor(monolith): create home domain from schedule + observability"
```

---

## Task 3: Add `register()` to the `knowledge` domain

**Files:**

- Modify: `projects/monolith/knowledge/__init__.py`

**Step 1: Write `knowledge/__init__.py` with register and public exports**

```python
"""Knowledge domain — knowledge graph CRUD, search, tasks, and dead-letter management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from sqlmodel import Session


def register(app: FastAPI) -> None:
    """Register knowledge domain routers with the app."""
    from knowledge.router import router
    from knowledge.tasks_router import router as tasks_router

    app.include_router(router)
    app.include_router(tasks_router)


# Public API — other domains call these instead of importing sub-modules.

async def search_notes(session: "Session", query_embedding: list[float], **kwargs):
    """Search knowledge notes by embedding similarity."""
    from knowledge.store import KnowledgeStore
    return KnowledgeStore(session).search_notes_with_context(
        query_embedding=query_embedding, **kwargs
    )


def get_embedding_client():
    """Return an embedding client instance (DI seam for tests)."""
    from shared.embedding import EmbeddingClient
    return EmbeddingClient()
```

**Step 2: Run architecture tests for knowledge**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:architecture_test --config=ci -t "knowledge"`
Expected: registration test passes, import boundary test may still fail (chat imports knowledge sub-modules — fixed in Task 4)

**Step 3: Commit**

```bash
git add projects/monolith/knowledge/__init__.py
git commit -m "refactor(monolith): add register() and public API to knowledge domain"
```

---

## Task 4: Add `register()` to the `chat` domain and fix cross-domain imports

**Files:**

- Modify: `projects/monolith/chat/__init__.py`
- Modify: `projects/monolith/chat/router.py` — replace `from knowledge.store import KnowledgeStore` with `from knowledge import ...`

**Step 1: Write `chat/__init__.py`**

```python
"""Chat domain — Discord bot, backfill, and explore agent."""

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    """Register chat domain routers with the app."""
    from chat.router import router

    app.include_router(router)
```

**Step 2: Fix `chat/router.py` cross-domain imports**

Replace:

```python
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient
```

With:

```python
from knowledge import search_notes, get_embedding_client
```

Then update the `explore` endpoint to use the public API function instead of directly constructing a `KnowledgeStore`. Note: the `explore` endpoint creates a `KnowledgeStore` to pass to `ExplorerDeps` — this needs the store object, not just a search call. Add `get_store(session)` to knowledge's public API:

In `knowledge/__init__.py`, add:

```python
def get_store(session: "Session"):
    """Return a KnowledgeStore instance for the given session."""
    from knowledge.store import KnowledgeStore
    return KnowledgeStore(session)
```

Then `chat/router.py` becomes:

```python
from knowledge import get_store
from shared.embedding import EmbeddingClient
```

Note: `shared.embedding` imports are always allowed (shared is the utility layer).

**Step 3: Run architecture tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:architecture_test --config=ci`
Expected: All three domains pass registration, import boundary, and route prefix tests.

**Step 4: Commit**

```bash
git add projects/monolith/chat/__init__.py projects/monolith/chat/router.py projects/monolith/knowledge/__init__.py
git commit -m "refactor(monolith): add register() to chat domain and fix cross-domain imports"
```

---

## Task 5: Refactor `app/main.py` to use domain registration

**Files:**

- Modify: `projects/monolith/app/main.py`

**Step 1: Replace direct router imports with domain registration**

The new `app/main.py` should:

1. Remove all `from {domain}.router import router as ...` lines
2. Call `{domain}.register(app)` instead
3. Move domain-specific lifespan logic into the domains where possible
4. Keep the lifespan structure but call domain functions instead of hardcoding details

Key changes to the imports section:

```python
# BEFORE:
from knowledge.router import router as knowledge_router
from knowledge.tasks_router import router as tasks_router
from chat.router import router as chat_router
from shared.router import router as schedule_router
from observability.router import (
    router as observability_router,
    warm_cache,
    warm_stats_cache,
)

# AFTER:
import chat
import home
import knowledge
```

Key changes to router registration:

```python
# BEFORE:
app.include_router(schedule_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(tasks_router)
app.include_router(observability_router)

# AFTER:
home.register(app)
chat.register(app)
knowledge.register(app)
```

Key changes to lifespan — replace `from shared.service import on_startup as shared_startup` with `from home import on_startup_jobs as home_startup` and call it. Replace `from knowledge.service import on_startup as knowledge_startup` call pattern similarly. The `warm_cache` and `warm_stats_cache` calls move to use `from home.observability.router import warm_cache, warm_stats_cache` (this is within `app/` which is the shell — it orchestrates startup, so it can import domain internals for lifespan wiring). Alternatively, expose these as public functions in `home/__init__.py`.

**Step 2: Run all tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`
Expected: All tests pass including architecture enforcement.

**Step 3: Commit**

```bash
git add projects/monolith/app/main.py
git commit -m "refactor(monolith): use domain register() pattern in main.py"
```

---

## Task 6: Update frontend API paths

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/+page.server.js` — `/api/schedule/today` → `/api/home/schedule/today`
- Modify: `projects/monolith/frontend/src/routes/public/slos/+page.server.js` — `/api/public/observability/topology` → `/api/home/observability/topology`

**Step 1: Update frontend fetch URLs**

In `+page.server.js` (private):

```javascript
// BEFORE:
fetch(`${API_BASE}/api/schedule/today`, {
// AFTER:
fetch(`${API_BASE}/api/home/schedule/today`, {
```

In `+page.server.js` (slos):

```javascript
// BEFORE:
const resp = await fetch(`${API_BASE}/api/public/observability/topology`, {
// AFTER:
const resp = await fetch(`${API_BASE}/api/home/observability/topology`, {
```

**Step 2: Update integration and e2e tests**

Update all test files that reference the old paths:

- `app/integration_test.py`: `/api/schedule/today` → `/api/home/schedule/today`
- `app/main_test.py`: `/api/schedule` → `/api/home`
- `e2e/e2e_test.py`: `/api/schedule/today` → `/api/home/schedule/today`
- `e2e/e2e_playwright_test.py`: `/api/schedule/today` → `/api/home/schedule/today`
- `scripts/generate-red-dashboard.py`: Update route prefix map

**Step 3: Check for any other references to old paths**

```bash
grep -r "api/schedule\|api/public/observability" projects/monolith/ --include="*.py" --include="*.js" --include="*.ts" --include="*.svelte"
```

Ensure zero results.

**Step 4: Run all tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`

**Step 5: Commit**

```bash
git add projects/monolith/frontend/ projects/monolith/app/ projects/monolith/e2e/ projects/monolith/scripts/
git commit -m "refactor(monolith): update API paths to /api/home/* convention"
```

---

## Task 7: Update BUILD file for new directory structure

**Files:**

- Modify: `projects/monolith/BUILD`

**Step 1: Update glob patterns**

The BUILD file's `py_venv_binary` and `py_library` use glob patterns like `"observability/**/*.py"`. These need updating:

```python
# BEFORE:
"observability/**/*.py",

# AFTER:
"home/**/*.py",
```

Also add `home` to the `# gazelle:exclude` list if observability was excluded, and remove the observability exclude.

**Step 2: Run format to regenerate BUILD**

```bash
format
```

**Step 3: Run all tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`

**Step 4: Commit**

```bash
git add projects/monolith/BUILD
git commit -m "build(monolith): update BUILD file for home domain directory structure"
```

---

## Task 8: Final verification and cleanup

**Step 1: Run the full test suite**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`
Expected: All tests pass, including all three architecture enforcement tests.

**Step 2: Verify architecture tests are green**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:architecture_test --config=ci`
Expected: 3 parameterized tests × 3 domains = 9 tests, all passing.

**Step 3: Clean up any remaining dead files**

- Remove empty `projects/monolith/observability/` directory if still present
- Remove `projects/monolith/shared/router.py` if not already deleted
- Verify `shared/service.py` either has no calendar code or is deleted if empty

**Step 4: Commit any cleanup**

```bash
git commit -m "chore(monolith): remove dead files from pre-refactor structure"
```

**Step 5: Push and open PR**

```bash
git push -u origin feat/modular-monolith
gh pr create --title "refactor(monolith): modular domain registration with boundary enforcement" --body "..."
```
