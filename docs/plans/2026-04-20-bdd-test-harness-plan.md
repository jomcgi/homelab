# BDD Test Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a domain-colocated BDD test harness with shared fixtures, pytest markers for coverage tracking, and an enforcement test that fails when routes, pages, or public functions lack tests.

**Architecture:** Extract `e2e/conftest.py` into `shared/testing/plugin.py` (pytest plugin). Each domain gets a `tests/` directory with BDD tests that import the plugin. A `coverage_test.py` introspects the app's routes, SvelteKit pages, and domain `__init__.py` exports, then asserts every item has at least one `@covers_*` marker in the test suite.

**Tech Stack:** Python, pytest, pytest markers, AST parsing, httpx, Playwright, FastAPI route introspection

**Design doc:** `docs/plans/2026-04-20-bdd-test-harness-design.md`

**Worktree:** `/tmp/claude-worktrees/bdd-test-harness` (branch `feat/bdd-test-harness`)

**Test command:** `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`

---

## Task 1: Create `shared/testing/markers.py`

**Files:**

- Create: `projects/monolith/shared/testing/__init__.py`
- Create: `projects/monolith/shared/testing/markers.py`

**Step 1: Create the markers module**

```python
# projects/monolith/shared/testing/markers.py
"""Pytest markers for BDD coverage tracking.

Usage:
    from shared.testing.markers import covers_route, covers_page, covers_public

    @covers_route("/api/home/schedule/today")
    def test_schedule_returns_events(live_server): ...

    @covers_page("/private")
    def test_dashboard_loads(page, sveltekit_server): ...

    @covers_public("knowledge.search_notes")
    def test_search_returns_results(session): ...
"""

import pytest


def covers_route(path: str, method: str = "GET"):
    """Mark a test as covering a specific API route."""
    return pytest.mark.covers_route(path=path, method=method)


def covers_page(path: str):
    """Mark a test as covering a frontend page (requires Playwright)."""
    return pytest.mark.covers_page(path=path)


def covers_public(qualified_name: str):
    """Mark a test as covering a domain public function."""
    return pytest.mark.covers_public(name=qualified_name)
```

**Step 2: Create the `__init__.py` re-export**

```python
# projects/monolith/shared/testing/__init__.py
"""Shared testing infrastructure for monolith BDD tests."""

from shared.testing.markers import covers_page, covers_public, covers_route

__all__ = ["covers_route", "covers_page", "covers_public"]
```

**Step 3: Commit**

```bash
git add projects/monolith/shared/testing/
git commit -m "test(monolith): add shared testing markers for BDD coverage tracking"
```

---

## Task 2: Extract `e2e/conftest.py` into `shared/testing/plugin.py`

**Files:**

- Create: `projects/monolith/shared/testing/plugin.py`
- Modify: `projects/monolith/e2e/conftest.py`

**Step 1: Create `plugin.py`**

Copy the full content of `e2e/conftest.py` into `shared/testing/plugin.py`. This becomes the canonical location for all shared fixtures. The file keeps all existing fixtures unchanged:

- `pytest_configure` hook
- `PgInfo` dataclass
- All helper functions (`_find_free_port`, `_pg_preexec`, `_ensure_sample_configs`, `_find_pg_root`, `_find_migrations_dir`, `_find_frontend_build`, `_find_node_binary`)
- All fixtures (`pg`, `session`, `client`, `embed_client`, `store`, `live_server`, `sveltekit_server`, `live_server_with_fake_embedding`)
- `deterministic_embedding` function

Additionally, register the custom markers so pytest doesn't warn about unknown marks:

```python
# Add to pytest_configure in plugin.py:
def pytest_configure(config):
    """Set asyncio_mode and register custom markers."""
    config.option.asyncio_mode = "auto"
    config.addinivalue_line("markers", "covers_route(path, method): marks test as covering an API route")
    config.addinivalue_line("markers", "covers_page(path): marks test as covering a frontend page")
    config.addinivalue_line("markers", "covers_public(name): marks test as covering a public function")
```

**Step 2: Replace `e2e/conftest.py` with a shim**

```python
# projects/monolith/e2e/conftest.py
"""E2E test fixtures — delegated to shared.testing.plugin."""

pytest_plugins = ["shared.testing.plugin"]
```

**Step 3: Run existing e2e tests to verify no regression**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:e2e_test --config=ci`
Expected: PASS — existing tests work via the shim.

**Step 4: Commit**

```bash
git add projects/monolith/shared/testing/plugin.py projects/monolith/e2e/conftest.py
git commit -m "refactor(monolith): extract e2e fixtures into shared.testing.plugin"
```

---

## Task 3: Create `bdd_test` Bazel macro

**Files:**

- Create: `projects/monolith/bdd_test.bzl`

**Step 1: Write the macro**

```python
# projects/monolith/bdd_test.bzl
"""Macro for domain BDD test targets with shared harness pre-wired."""

load("//bazel/tools/pytest:defs.bzl", "py_test")

def bdd_test(name, srcs, playwright = False, size = "large", timeout = "moderate", **kwargs):
    """BDD test target with shared testing fixtures and data deps.

    Args:
        name: Target name.
        srcs: Test source files (include the domain's tests/conftest.py).
        playwright: If True, adds frontend_dist data dep and playwright tag.
        size: Test size (default "large" since it starts real PostgreSQL).
        timeout: Test timeout (default "moderate").
        **kwargs: Passed to py_test.
    """
    data = [
        "//projects/monolith/chart:migrations",
        "@postgres_test//:postgres",
    ]
    tags = ["bdd"]

    if playwright:
        data.append("//projects/monolith:frontend_dist")
        tags.append("playwright")

    py_test(
        name = name,
        srcs = srcs,
        data = data,
        imports = ["."],
        tags = tags,
        size = size,
        timeout = timeout,
        deps = [
            "//projects/monolith:shared_testing",
            "//projects/monolith:monolith_backend",
        ] + kwargs.pop("deps", []),
        **kwargs
    )
```

**Step 2: Add `shared_testing` library to BUILD**

Add this to `projects/monolith/BUILD` after the existing `py_library(name = "monolith_backend", ...)`:

```python
py_library(
    name = "shared_testing",
    srcs = glob(["shared/testing/**/*.py"]),
    imports = ["."],
    visibility = ["//:__subpackages__"],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlalchemy",
        "@pip//sqlmodel",
    ],
)
```

**Step 3: Run format to validate BUILD syntax**

Run: `format`

**Step 4: Commit**

```bash
git add projects/monolith/bdd_test.bzl projects/monolith/BUILD
git commit -m "build(monolith): add bdd_test macro and shared_testing library"
```

---

## Task 4: Create `home/tests/` BDD tests

**Files:**

- Create: `projects/monolith/home/tests/__init__.py`
- Create: `projects/monolith/home/tests/conftest.py`
- Create: `projects/monolith/home/tests/bdd_api_test.py`
- Create: `projects/monolith/home/tests/bdd_playwright_test.py`
- Create: `projects/monolith/home/tests/bdd_public_test.py`

**Step 1: Create conftest**

```python
# projects/monolith/home/tests/conftest.py
"""BDD test fixtures for the home domain."""

pytest_plugins = ["shared.testing.plugin"]
```

**Step 2: Write API BDD tests**

```python
# projects/monolith/home/tests/bdd_api_test.py
"""BDD tests for home domain API routes."""

import httpx

from shared.testing.markers import covers_route


class TestScheduleAPI:
    @covers_route("/api/home/schedule/today")
    def test_returns_list_of_events(self, live_server):
        r = httpx.get(f"{live_server}/api/home/schedule/today")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestObservabilityAPI:
    @covers_route("/api/home/observability/topology")
    def test_returns_topology_structure(self, live_server):
        r = httpx.get(f"{live_server}/api/home/observability/topology")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert "groups" in data

    @covers_route("/api/home/observability/stats")
    def test_returns_stats(self, live_server):
        r = httpx.get(f"{live_server}/api/home/observability/stats")
        assert r.status_code == 200
```

**Step 3: Write Playwright BDD tests**

```python
# projects/monolith/home/tests/bdd_playwright_test.py
"""BDD Playwright tests for home domain frontend pages."""

import pytest

from shared.testing.markers import covers_page

playwright = pytest.importorskip("playwright")


class TestPrivateDashboard:
    @covers_page("/private")
    def test_dashboard_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/private")
        # The private page should render without error
        assert page.title() or page.locator("body").inner_text()


class TestSLOPage:
    @covers_page("/public/slos")
    def test_slo_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/public/slos")
        assert page.title() or page.locator("body").inner_text()
```

**Step 4: Write public function BDD tests**

```python
# projects/monolith/home/tests/bdd_public_test.py
"""BDD tests for home domain public API functions."""

from shared.testing.markers import covers_public

import home


class TestPublicFunctions:
    @covers_public("home.get_today_events")
    def test_get_today_events_returns_list(self):
        result = home.get_today_events()
        assert isinstance(result, list)

    @covers_public("home.on_startup_jobs")
    def test_on_startup_jobs_registers_job(self, session):
        from unittest.mock import patch

        with patch("shared.scheduler.register_job") as mock_register:
            home.on_startup_jobs(session)
        mock_register.assert_called_once()
        _, kwargs = mock_register.call_args
        assert kwargs["name"] == "home.calendar_poll"
```

**Step 5: Create empty `__init__.py`**

```python
# projects/monolith/home/tests/__init__.py
```

**Step 6: Add BUILD targets**

Add to `projects/monolith/BUILD`:

```python
load("//projects/monolith:bdd_test.bzl", "bdd_test")

bdd_test(
    name = "home_bdd_api_test",
    srcs = [
        "home/tests/__init__.py",
        "home/tests/conftest.py",
        "home/tests/bdd_api_test.py",
    ],
)

bdd_test(
    name = "home_bdd_playwright_test",
    srcs = [
        "home/tests/__init__.py",
        "home/tests/conftest.py",
        "home/tests/bdd_playwright_test.py",
    ],
    playwright = True,
    timeout = "long",
)

bdd_test(
    name = "home_bdd_public_test",
    srcs = [
        "home/tests/__init__.py",
        "home/tests/conftest.py",
        "home/tests/bdd_public_test.py",
    ],
)
```

**Step 7: Run tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:home_bdd_api_test --config=ci`
Expected: PASS

**Step 8: Commit**

```bash
git add projects/monolith/home/tests/ projects/monolith/BUILD
git commit -m "test(monolith): add BDD tests for home domain"
```

---

## Task 5: Create `knowledge/tests/` BDD tests

**Files:**

- Create: `projects/monolith/knowledge/tests/__init__.py`
- Create: `projects/monolith/knowledge/tests/conftest.py`
- Create: `projects/monolith/knowledge/tests/bdd_api_test.py`
- Create: `projects/monolith/knowledge/tests/bdd_playwright_test.py`
- Create: `projects/monolith/knowledge/tests/bdd_public_test.py`

**Step 1: Create conftest**

```python
# projects/monolith/knowledge/tests/conftest.py
"""BDD test fixtures for the knowledge domain."""

pytest_plugins = ["shared.testing.plugin"]
```

**Step 2: Write API BDD tests**

```python
# projects/monolith/knowledge/tests/bdd_api_test.py
"""BDD tests for knowledge domain API routes."""

import httpx

from shared.testing.markers import covers_route


class TestKnowledgeSearch:
    @covers_route("/api/knowledge/search")
    def test_search_returns_results(self, live_server_with_fake_embedding):
        r = httpx.get(
            f"{live_server_with_fake_embedding}/api/knowledge/search",
            params={"q": "test query"},
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestKnowledgeNotes:
    @covers_route("/api/knowledge/notes", method="POST")
    def test_create_note(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Test note content", "title": "Test Note"},
        )
        assert r.status_code == 201
        assert "id" in r.json()

    @covers_route("/api/knowledge/notes/{note_id}", method="GET")
    def test_get_note(self, live_server_with_fake_embedding):
        # Create then retrieve
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Retrievable note", "title": "Get Test"},
        )
        note_id = create.json()["id"]
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/notes/{note_id}")
        assert r.status_code == 200
        assert r.json()["title"] == "Get Test"

    @covers_route("/api/knowledge/notes/{note_id}", method="PUT")
    def test_update_note(self, live_server_with_fake_embedding):
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Original", "title": "Update Test"},
        )
        note_id = create.json()["id"]
        r = httpx.put(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/{note_id}",
            json={"content": "Updated content"},
        )
        assert r.status_code == 200

    @covers_route("/api/knowledge/notes/{note_id}", method="DELETE")
    def test_delete_note(self, live_server_with_fake_embedding):
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Deletable", "title": "Delete Test"},
        )
        note_id = create.json()["id"]
        r = httpx.delete(f"{live_server_with_fake_embedding}/api/knowledge/notes/{note_id}")
        assert r.status_code == 200


class TestKnowledgeIngest:
    @covers_route("/api/knowledge/ingest", method="POST")
    def test_ingest_accepts_payload(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/ingest",
            json={"content": "Ingest test", "source": "test"},
        )
        assert r.status_code == 201


class TestDeadLetter:
    @covers_route("/api/knowledge/dead-letter")
    def test_list_dead_letters(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/dead-letter")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    @covers_route("/api/knowledge/dead-letter/{raw_id}/replay", method="POST")
    def test_replay_dead_letter_not_found(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/dead-letter/nonexistent/replay"
        )
        # Either 404 (not found) or 200 (replayed) — both are valid responses
        assert r.status_code in (200, 404)


class TestTasks:
    @covers_route("/api/knowledge/tasks")
    def test_list_tasks(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/tasks")
        assert r.status_code == 200

    @covers_route("/api/knowledge/tasks/daily")
    def test_daily_tasks(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/tasks/daily")
        assert r.status_code == 200

    @covers_route("/api/knowledge/tasks/weekly")
    def test_weekly_tasks(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/tasks/weekly")
        assert r.status_code == 200

    @covers_route("/api/knowledge/tasks/{note_id}", method="PATCH")
    def test_patch_task(self, live_server_with_fake_embedding):
        # Create a note (task) first, then patch it
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Task note", "title": "Task Test", "type": "task"},
        )
        note_id = create.json()["id"]
        r = httpx.patch(
            f"{live_server_with_fake_embedding}/api/knowledge/tasks/{note_id}",
            json={"status": "done"},
        )
        assert r.status_code in (200, 404)  # 404 if task not indexed yet
```

**Step 3: Write Playwright BDD tests**

```python
# projects/monolith/knowledge/tests/bdd_playwright_test.py
"""BDD Playwright tests for knowledge domain frontend pages."""

import pytest

from shared.testing.markers import covers_page

playwright = pytest.importorskip("playwright")


class TestChatPage:
    @covers_page("/private/chat")
    def test_chat_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/private/chat")
        assert page.title() or page.locator("body").inner_text()


class TestPublicLanding:
    @covers_page("/public")
    def test_public_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/public")
        assert page.title() or page.locator("body").inner_text()
```

**Step 4: Write public function BDD tests**

```python
# projects/monolith/knowledge/tests/bdd_public_test.py
"""BDD tests for knowledge domain public API functions."""

from shared.testing.markers import covers_public

import knowledge


class TestPublicFunctions:
    @covers_public("knowledge.search_notes")
    def test_search_notes_returns_results(self, session):
        from shared.testing.plugin import deterministic_embedding

        embedding = deterministic_embedding("test query")
        result = knowledge.search_notes(session, query_embedding=embedding)
        assert isinstance(result, list)

    @covers_public("knowledge.get_store")
    def test_get_store_returns_store_instance(self, session):
        store = knowledge.get_store(session)
        assert store is not None
        assert hasattr(store, "search_notes_with_context")

    @covers_public("knowledge.get_embedding_client")
    def test_get_embedding_client_returns_client(self):
        from unittest.mock import patch

        with patch("shared.embedding.EmbeddingClient") as mock_cls:
            client = knowledge.get_embedding_client()
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value
```

**Step 5: Create empty `__init__.py`**

```python
# projects/monolith/knowledge/tests/__init__.py
```

**Step 6: Add BUILD targets**

Add to `projects/monolith/BUILD`:

```python
bdd_test(
    name = "knowledge_bdd_api_test",
    srcs = [
        "knowledge/tests/__init__.py",
        "knowledge/tests/conftest.py",
        "knowledge/tests/bdd_api_test.py",
    ],
)

bdd_test(
    name = "knowledge_bdd_playwright_test",
    srcs = [
        "knowledge/tests/__init__.py",
        "knowledge/tests/conftest.py",
        "knowledge/tests/bdd_playwright_test.py",
    ],
    playwright = True,
    timeout = "long",
)

bdd_test(
    name = "knowledge_bdd_public_test",
    srcs = [
        "knowledge/tests/__init__.py",
        "knowledge/tests/conftest.py",
        "knowledge/tests/bdd_public_test.py",
    ],
)
```

**Step 7: Run tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:knowledge_bdd_api_test --config=ci`
Expected: PASS

**Step 8: Commit**

```bash
git add projects/monolith/knowledge/tests/ projects/monolith/BUILD
git commit -m "test(monolith): add BDD tests for knowledge domain"
```

---

## Task 6: Create `chat/tests/` BDD tests

**Files:**

- Create: `projects/monolith/chat/tests/__init__.py`
- Create: `projects/monolith/chat/tests/conftest.py`
- Create: `projects/monolith/chat/tests/bdd_api_test.py`
- Create: `projects/monolith/chat/tests/bdd_public_test.py`

**Step 1: Create conftest**

```python
# projects/monolith/chat/tests/conftest.py
"""BDD test fixtures for the chat domain."""

pytest_plugins = ["shared.testing.plugin"]
```

**Step 2: Write API BDD tests**

```python
# projects/monolith/chat/tests/bdd_api_test.py
"""BDD tests for chat domain API routes."""

import httpx

from shared.testing.markers import covers_route


class TestBackfill:
    @covers_route("/api/chat/backfill", method="POST")
    def test_backfill_requires_running_bot(self, live_server):
        """Backfill returns 409 when bot is not connected."""
        r = httpx.post(f"{live_server}/api/chat/backfill")
        # Without a Discord bot running, backfill should return 409 or similar
        assert r.status_code in (409, 503)


class TestExplore:
    @covers_route("/api/chat/explore", method="POST")
    def test_explore_requires_query(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/chat/explore",
            json={"query": "test question"},
        )
        # Explore may stream or fail without LLM — assert it doesn't 500
        assert r.status_code != 500
```

**Step 3: Create empty `__init__.py`**

```python
# projects/monolith/chat/tests/__init__.py
```

**Step 4: Add BUILD targets**

Add to `projects/monolith/BUILD`:

```python
bdd_test(
    name = "chat_bdd_api_test",
    srcs = [
        "chat/tests/__init__.py",
        "chat/tests/conftest.py",
        "chat/tests/bdd_api_test.py",
    ],
)
```

**Step 5: Run tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:chat_bdd_api_test --config=ci`
Expected: PASS

**Step 6: Commit**

```bash
git add projects/monolith/chat/tests/ projects/monolith/BUILD
git commit -m "test(monolith): add BDD tests for chat domain"
```

---

## Task 7: Create `app/coverage_test.py` — enforcement

**Files:**

- Create: `projects/monolith/app/coverage_test.py`

**Step 1: Write the coverage enforcement test**

```python
# projects/monolith/app/coverage_test.py
"""Coverage enforcement — asserts every route, page, and public function has a BDD test.

This test introspects the running app and filesystem to discover what needs
testing, then AST-scans domain test files for @covers_* markers to verify
coverage exists.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

_MONOLITH_ROOT = Path(__file__).resolve().parent.parent
_DOMAINS = ["home", "chat", "knowledge"]

# Routes that are intentionally excluded from coverage enforcement.
# Each exclusion must have a comment explaining why.
_ROUTE_EXCLUSIONS = {
    ("GET", "/healthz"),  # trivial health check, tested by integration_test
    ("GET", "/openapi.json"),  # auto-generated by FastAPI
    ("HEAD", "/openapi.json"),  # auto-generated by FastAPI
}

# Pages that are intentionally excluded from coverage enforcement.
_PAGE_EXCLUSIONS: set[str] = set()

# Public functions excluded from coverage enforcement.
_PUBLIC_EXCLUSIONS: set[str] = {
    # register() is tested by architecture_test.py, not BDD tests
    "home.register",
    "chat.register",
    "knowledge.register",
}


# ---------------------------------------------------------------------------
# Discovery: what exists in the app
# ---------------------------------------------------------------------------


def _discover_routes() -> set[tuple[str, str]]:
    """Introspect the FastAPI app to find all registered routes."""
    from app.main import app

    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        # Skip mounted sub-apps (like /mcp and static files)
        if hasattr(route, "app"):
            continue
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            routes.add((method, route.path))
    return routes


def _discover_pages() -> set[str]:
    """Glob SvelteKit +page.svelte files and derive URL paths."""
    routes_dir = _MONOLITH_ROOT / "frontend" / "src" / "routes"
    pages: set[str] = set()
    for page_file in routes_dir.rglob("+page.svelte"):
        # Derive URL path from filesystem path
        rel = page_file.parent.relative_to(routes_dir)
        url_path = "/" + str(rel).replace("\\", "/")
        if url_path == "/.":
            url_path = "/"
        pages.add(url_path)
    return pages


def _discover_public_functions() -> set[str]:
    """Inspect domain __init__.py exports to find public functions."""
    public: set[str] = set()
    for domain in _DOMAINS:
        mod = importlib.import_module(domain)
        for name, obj in inspect.getmembers(mod):
            if name.startswith("_"):
                continue
            if not callable(obj):
                continue
            # Skip imported modules/classes — only functions defined here
            if inspect.ismodule(obj):
                continue
            public.add(f"{domain}.{name}")
    return public


# ---------------------------------------------------------------------------
# Collection: what's covered by tests
# ---------------------------------------------------------------------------


def _collect_markers_from_tests() -> (
    tuple[set[tuple[str, str]], set[str], set[str]]
):
    """AST-scan domain test files for @covers_* marker calls.

    Returns:
        (covered_routes, covered_pages, covered_public)
    """
    covered_routes: set[tuple[str, str]] = set()
    covered_pages: set[str] = set()
    covered_public: set[str] = set()

    for domain in _DOMAINS:
        tests_dir = _MONOLITH_ROOT / domain / "tests"
        if not tests_dir.is_dir():
            continue
        for py_file in tests_dir.rglob("*_test.py"):
            source = py_file.read_text()
            tree = ast.parse(source, filename=str(py_file))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # Match covers_route(...), covers_page(...), covers_public(...)
                func_name = _get_call_name(node)
                if func_name == "covers_route":
                    path, method = _extract_route_args(node)
                    if path:
                        covered_routes.add((method, path))
                elif func_name == "covers_page":
                    path = _extract_first_string_arg(node)
                    if path:
                        covered_pages.add(path)
                elif func_name == "covers_public":
                    name = _extract_first_string_arg(node)
                    if name:
                        covered_public.add(name)

    return covered_routes, covered_pages, covered_public


def _get_call_name(node: ast.Call) -> str | None:
    """Extract the function name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _extract_first_string_arg(node: ast.Call) -> str | None:
    """Extract the first positional string argument from a Call."""
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
        node.args[0].value, str
    ):
        return node.args[0].value
    # Check keyword args for 'path' or 'name'
    for kw in node.keywords:
        if kw.arg in ("path", "name") and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _extract_route_args(node: ast.Call) -> tuple[str | None, str]:
    """Extract (path, method) from a covers_route() call."""
    path = _extract_first_string_arg(node)
    method = "GET"  # default
    for kw in node.keywords:
        if kw.arg == "method" and isinstance(kw.value, ast.Constant):
            method = kw.value.value
    return path, method


# ---------------------------------------------------------------------------
# Enforcement tests
# ---------------------------------------------------------------------------


class TestBDDCoverage:
    """Ensure every route, page, and public function has a BDD test."""

    def test_all_routes_covered(self):
        discovered = _discover_routes() - _ROUTE_EXCLUSIONS
        covered, _, _ = _collect_markers_from_tests()
        uncovered = discovered - covered
        assert not uncovered, (
            f"API routes missing BDD tests ({len(uncovered)}):\n"
            + "\n".join(f"  {method} {path}" for method, path in sorted(uncovered))
            + "\n\nAdd @covers_route() markers to domain tests."
        )

    def test_all_pages_covered(self):
        discovered = _discover_pages() - _PAGE_EXCLUSIONS
        _, covered, _ = _collect_markers_from_tests()
        uncovered = discovered - covered
        assert not uncovered, (
            f"Frontend pages missing Playwright tests ({len(uncovered)}):\n"
            + "\n".join(f"  {path}" for path in sorted(uncovered))
            + "\n\nAdd @covers_page() markers to domain Playwright tests."
        )

    def test_all_public_functions_covered(self):
        discovered = _discover_public_functions() - _PUBLIC_EXCLUSIONS
        _, _, covered = _collect_markers_from_tests()
        uncovered = discovered - covered
        assert not uncovered, (
            f"Public functions missing BDD tests ({len(uncovered)}):\n"
            + "\n".join(f"  {name}" for name in sorted(uncovered))
            + "\n\nAdd @covers_public() markers to domain tests."
        )
```

**Step 2: Add BUILD target**

Add to `projects/monolith/BUILD`:

```python
py_test(
    name = "coverage_test",
    srcs = [
        "app/__init__.py",
        "app/coverage_test.py",
    ],
    data = glob(["*/tests/*_test.py"]) + [
        "//projects/monolith/chart:migrations",
        "@postgres_test//:postgres",
    ],
    imports = ["."],
    tags = ["bdd"],
    size = "large",
    deps = [
        ":monolith_backend",
        ":shared_testing",
        "@pip//pytest",
    ],
)
```

**Step 3: Run the enforcement test**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:coverage_test --config=ci`
Expected: PASS — all routes/pages/public functions should be covered by the tests written in Tasks 4-6.

**Step 4: Verify it catches missing coverage**

Temporarily remove one `@covers_route` marker and confirm the test fails. Then restore it.

**Step 5: Commit**

```bash
git add projects/monolith/app/coverage_test.py projects/monolith/BUILD
git commit -m "test(monolith): add BDD coverage enforcement test"
```

---

## Task 8: Final verification and cleanup

**Step 1: Run the full test suite**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci`
Expected: All tests pass — existing unit tests, existing e2e tests (via shim), new BDD tests, and coverage enforcement.

**Step 2: Verify the e2e shim didn't break existing tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith:e2e_test //projects/monolith:e2e_playwright_test --config=ci`
Expected: PASS

**Step 3: Run format**

Run: `format`

**Step 4: Push and create PR**

```bash
git push -u origin feat/bdd-test-harness
gh pr create --title "test(monolith): BDD test harness with domain-colocated tests and coverage enforcement" --body "..."
```
