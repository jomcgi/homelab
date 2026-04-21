# BDD Test Harness: Domain-Colocated Integration Tests with Coverage Enforcement

## Problem

The monolith has ~150 unit tests that mostly test implementation details via mocks and internal imports. The e2e infrastructure (`e2e/conftest.py`) provides production-like fixtures (real PostgreSQL, live uvicorn, Playwright), but it's monolithic — all e2e tests live in one directory with no domain ownership. There's no enforcement that new routes, pages, or public functions get tested.

## Goals

1. Tests execute against a running frontend + backend (not TestClient or mocks).
2. BDD-style: test public interfaces (API routes, frontend pages, domain public functions), never implementation details.
3. Domain-colocated: each domain owns its tests in `{domain}/tests/`.
4. Enforced coverage: an architecture test asserts every route, page, and public function has at least one test.

## Shared Test Harness — `shared/testing/`

```
shared/testing/
  __init__.py           # re-exports markers
  plugin.py             # pytest plugin — all fixtures extracted from e2e/conftest.py
  markers.py            # covers_route, covers_page, covers_public decorators
```

### `markers.py`

Three pytest marker factories that annotate what each test covers:

- `covers_route(path, method="GET")` — marks a test as covering a specific FastAPI/FastMCP route
- `covers_page(path)` — marks a test as covering a SvelteKit frontend page (requires Playwright)
- `covers_public(qualified_name)` — marks a test as covering a domain's public function (e.g. `"knowledge.search_notes"`)

### `plugin.py`

Extracted from the existing `e2e/conftest.py` (~670 lines). Same fixtures, now importable as a pytest plugin:

- `pg` (session) — real PostgreSQL 16 + pgvector from Bazel OCI runfiles
- `session` (function) — SAVEPOINT-isolated SQLAlchemy session
- `live_server` (session) — uvicorn on a random port backed by test PostgreSQL
- `sveltekit_server` (session) — SvelteKit Node.js server pointed at `live_server`
- `embed_client` (function) — deterministic hash-based mock embeddings
- `page` (function) — Playwright browser page (from pytest-playwright)

The existing `e2e/conftest.py` becomes a thin shim: `pytest_plugins = ["shared.testing.plugin"]`.

## Domain Test Layout

```
{domain}/tests/
  conftest.py              # pytest_plugins = ["shared.testing.plugin"]
  bdd_api_test.py          # @covers_route tests against live_server via httpx
  bdd_playwright_test.py   # @covers_page tests via Playwright
  bdd_public_test.py       # @covers_public tests calling __init__.py exports
```

Not every domain needs all three files — only what it exposes:

| Domain      | API tests | Playwright tests | Public function tests |
| ----------- | --------- | ---------------- | --------------------- |
| `home`      | yes       | yes              | yes                   |
| `chat`      | yes       | no               | yes                   |
| `knowledge` | yes       | yes              | yes                   |

### Test style

All imports at the top of the file, not inside test functions. Tests assert against public interfaces only:

```python
from shared.testing.markers import covers_route

class TestScheduleAPI:
    @covers_route("/api/home/schedule/today")
    def test_returns_todays_events(self, live_server):
        r = httpx.get(f"{live_server}/api/home/schedule/today")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
```

## Coverage Enforcement — `app/coverage_test.py`

Sits alongside `architecture_test.py` as a second architectural enforcement test.

### Discovery

1. **Routes** — Import the FastAPI `app`, walk `app.routes`, collect all `(method, path)` tuples. Also discover FastMCP tools via the MCP app's registered tool list.
2. **Frontend pages** — Glob `frontend/src/routes/**/+page.svelte`, derive URL paths from filesystem layout (SvelteKit convention).
3. **Public functions** — For each domain in `_DOMAINS`, import its `__init__.py`, collect all callables that don't start with `_` and aren't `register`.

### Collection

AST-scan all `*_test.py` files in `{domain}/tests/` directories. Parse decorator calls to collect marker arguments:

- `@covers_route(path, method)` → set of `(method, path)`
- `@covers_page(path)` → set of paths
- `@covers_public(name)` → set of qualified names

### Assertion

```python
class TestBDDCoverage:
    def test_all_routes_covered(self):
        uncovered = discovered_routes - covered_routes
        assert not uncovered, f"Routes missing BDD tests:\n" + ...

    def test_all_pages_covered(self):
        uncovered = discovered_pages - covered_pages
        assert not uncovered, f"Pages missing Playwright tests:\n" + ...

    def test_all_public_functions_covered(self):
        uncovered = discovered_public - covered_public
        assert not uncovered, f"Public functions missing tests:\n" + ...
```

### Exclusions

A `_ROUTE_EXCLUSIONS` set at the top of the file allows skipping intentionally untested routes. Each exclusion requires a comment explaining why.

```python
_ROUTE_EXCLUSIONS = {
    ("GET", "/healthz"),           # trivial, tested by integration_test
    ("POST", "/otel/v1/traces"),   # passthrough, not our logic
}
```

## Bazel Integration

### Shared testing library

```python
py_library(
    name = "shared_testing",
    srcs = glob(["shared/testing/**/*.py"]),
    imports = ["."],
    visibility = ["//:__subpackages__"],
    deps = [":monolith_backend", "@pip//pytest", "@pip//httpx", "@pip//playwright"],
)
```

### `bdd_test` macro

Reduces boilerplate for domain BDD test targets:

```python
def bdd_test(name, domain, srcs, playwright=False, **kwargs):
    data = [
        "//projects/monolith/chart:migrations",
        "@postgres_test//:postgres",
    ]
    if playwright:
        data.append("//projects/monolith:frontend_dist")

    py_test(
        name=name,
        srcs=srcs,
        data=data,
        imports=["."],
        tags=["bdd"] + (["playwright"] if playwright else []),
        size="large",
        deps=[
            "//projects/monolith:shared_testing",
            "//projects/monolith:monolith_backend",
        ],
        **kwargs
    )
```

### BUILD management

Manual — the monolith is already fully gazelle-excluded. The `bdd_test` macro doesn't collide with gazelle.

## What Doesn't Change

- Existing unit tests stay as-is (can be pruned later if BDD tests provide equivalent confidence)
- Existing `e2e_test.py` and `e2e_playwright_test.py` keep working (conftest becomes a shim)
- `bb remote test` workflow
- Architecture test for domain boundaries
