# Monolith E2E Testing Design

## Problem

The monolith has 62+ unit tests, all using in-memory SQLite with a schema-stripping hack. This can't validate:

- pgvector similarity search (HNSW index, `<=>` operator)
- PostgreSQL schema-qualified tables (`chat.messages`, `todo.tasks`)
- Migration correctness (5 DDL files never applied in tests)
- Real unique constraints and FK cascades
- Agent tool chains that flow through real database operations

## Decision

Add e2e integration tests that run against a real PostgreSQL 16 + pgvector instance, managed hermetically by Bazel. External services (Discord, LLMs, SearXNG, vault) stay mocked. PydanticAI's `TestModel` and `FunctionModel` replace the real LLM.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Bazel Test Targets (py_test)                   │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ API e2e tests │  │ Playwright UI e2e tests │  │
│  └──────┬───────┘  └──────────┬──────────────┘  │
│         │                     │                  │
│  ┌──────▼─────────────────────▼──────────────┐  │
│  │  conftest.py (shared fixtures)            │  │
│  │  - PostgreSQL process lifecycle           │  │
│  │  - Migration runner                       │  │
│  │  - FastAPI TestClient / live server       │  │
│  │  - Mock EmbeddingClient (deterministic)   │  │
│  │  - PydanticAI TestModel / FunctionModel   │  │
│  └──────┬────────────────────────────────────┘  │
│         │                                        │
│  ┌──────▼────────────────────────────────────┐  │
│  │  PostgreSQL 16 + pgvector (from OCI)      │  │
│  │  Extracted binaries as Bazel data deps    │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### What's Real

- PostgreSQL 16 + pgvector extension
- FastAPI application (all routers)
- SQLModel ORM + schema-qualified tables
- All 5 DDL migrations applied in order
- MessageStore (save, search, dedup, summaries)
- Agent tool execution chain (search_history → embed → pgvector → format)

### What's Mocked

- Discord gateway (no bot connection)
- LLM inference (PydanticAI TestModel/FunctionModel)
- Embedding model (deterministic hash-based vectors)
- Vision model (returns canned description)
- SearXNG web search (canned results)
- Obsidian vault API (httpx patched)
- iCal feed (env var unset)

## PostgreSQL Binary Extraction

Pull `pgvector/pgvector:pg16` via `oci.pull()` in MODULE.bazel (linux/amd64 only — CI is x86_64).

A custom Bazel repository rule (`bazel/tools/postgres/oci_postgres.bzl`) extracts:

- `postgres`, `initdb`, `pg_isready` binaries
- `vector.so` pgvector extension
- `vector--*.sql` and `vector.control` extension files
- Required shared libraries (libpq, libicu, etc.)

Exposed as a `filegroup` target: `//bazel/tools/postgres:postgres_binaries`

Modeled on the existing `bazel/semgrep/third_party/semgrep_pro/oci_archive.bzl` pattern.

## Test Fixture Design

### PostgreSQL Fixture (session-scoped)

Starts once per test session:

1. Find binaries via Bazel runfiles (`TEST_SRCDIR`)
2. `initdb` into a temp directory
3. Start `postgres` on a random free port
4. `CREATE DATABASE monolith` + `CREATE EXTENSION vector`
5. Apply all 5 migration SQL files in order
6. Yield `DATABASE_URL`
7. Stop postgres and clean up on teardown

### Session Fixture (function-scoped)

Each test gets a SQLModel `Session` inside a PostgreSQL SAVEPOINT. The savepoint rolls back after each test — tests don't pollute each other but see real PostgreSQL behavior.

### Deterministic Embeddings

```python
def deterministic_embedding(text: str) -> list[float]:
    """Hash text to produce a stable 1024-dim unit vector."""
    h = hashlib.sha256(text.encode()).digest()
    rng = random.Random(int.from_bytes(h[:8]))
    vec = [rng.gauss(0, 1) for _ in range(1024)]
    norm = sum(x*x for x in vec) ** 0.5
    return [x / norm for x in vec]
```

Identical text produces identical vectors. Sufficient for save → search → retrieve flows. Real embedding fixtures can be added later for ranked similarity tests.

### PydanticAI Test Models

- **TestModel** — returns canned responses, records tool calls. For asserting tool selection.
- **FunctionModel** — custom response function. For testing full tool execution chains where tools hit real Postgres.

## Test Cases

### HTTP API Tests

- `test_healthz` — 200 OK
- `test_home_crud_flow` — PUT → GET → reset daily → archive
- `test_home_weekly_reset` — reset clears weekly, preserves daily
- `test_home_archive_invalid_date` — 400
- `test_home_archive_not_found` — 404
- `test_notes_create` — POST → 201 (vault mocked)
- `test_notes_empty_content` — 400
- `test_schedule_today` — returns list (iCal mocked)

### MessageStore Tests (pgvector)

- `test_save_and_retrieve_message` — save → get_recent
- `test_duplicate_message_id_returns_none` — IntegrityError handling
- `test_search_similar_returns_matching_message` — pgvector `<=>` operator
- `test_search_similar_filters_by_channel` — channel isolation
- `test_search_similar_filters_by_user` — user_id filter
- `test_attachment_blob_dedup` — SHA256 PK dedup
- `test_get_attachments_joins_blobs` — join returns (Attachment, Blob)
- `test_upsert_summary_insert_and_update` — upsert behavior
- `test_upsert_summary_unique_constraint` — real PG constraint enforcement
- `test_cascade_delete_messages` — FK cascade

### Agent Tool Execution Tests

- `test_search_history_tool_uses_pgvector` — FunctionModel → search_history → real pgvector results
- `test_get_user_summary_tool` — FunctionModel → real summary from PG
- `test_agent_with_test_model_records_tool_calls` — TestModel records tool calls + args

### Playwright UI Tests

- `test_home_page_loads` — renders weekly + daily slots
- `test_edit_and_save_tasks` — fill → save → reload → persisted
- `test_daily_reset_flow` — reset → tasks clear → archive appears

## Bazel Targets

```python
py_test(
    name = "e2e_test",
    srcs = ["e2e/e2e_test.py"],
    data = [
        "//bazel/tools/postgres:postgres_binaries",
        "//projects/monolith/chart:migrations",
    ],
    deps = [":monolith_backend", "@pip//psycopg", ...],
    tags = ["e2e"],
    size = "large",
    timeout = "moderate",
)

py_test(
    name = "e2e_playwright_test",
    srcs = ["e2e/e2e_playwright_test.py"],
    data = [
        "//bazel/tools/postgres:postgres_binaries",
        "//projects/monolith/chart:migrations",
        "//projects/monolith/frontend:dist",
    ],
    deps = [":monolith_backend", "@pip//playwright", ...],
    tags = ["e2e", "playwright"],
    size = "large",
    timeout = "long",
)
```

Tags are `e2e` (not `external`), so they run in CI by default. Can be excluded later if needed.

## File Layout

```
projects/monolith/
├── e2e/
│   ├── conftest.py              # PostgreSQL + mock fixtures
│   ├── e2e_test.py              # API + store + agent tool tests
│   └── e2e_playwright_test.py   # UI flow tests
bazel/tools/postgres/
├── BUILD
└── oci_postgres.bzl             # OCI extraction rule
```

## What's NOT Covered (stays unit-tested)

- Discord gateway event handling
- LLM response quality
- iCal feed parsing
- Vision model image description
- Individual error handling paths in bot.py
