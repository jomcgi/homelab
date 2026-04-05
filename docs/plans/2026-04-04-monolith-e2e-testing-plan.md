# Monolith E2E Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add e2e integration tests for the monolith that run against real PostgreSQL 16 + pgvector, replacing SQLite-based behavioral tests with ones that validate real database semantics.

**Architecture:** Extract PostgreSQL binaries from a Docker Hub OCI image via a custom Bazel repository rule. A session-scoped pytest fixture starts Postgres, runs migrations, and provides a `DATABASE_URL`. Tests use FastAPI TestClient for HTTP tests, real MessageStore for pgvector tests, and PydanticAI TestModel/FunctionModel for agent tests. Playwright drives UI tests against a live server.

**Tech Stack:** Bazel (rules_oci), PostgreSQL 16, pgvector, pytest, FastAPI TestClient, PydanticAI TestModel/FunctionModel, Playwright

**Design doc:** `docs/plans/2026-04-04-monolith-e2e-testing-design.md`

---

### Task 1: OCI PostgreSQL Extraction Rule

Create a Bazel repository rule that pulls the `pgvector/pgvector:pg16` image from Docker Hub and extracts the PostgreSQL binaries + pgvector extension.

**Files:**

- Create: `bazel/tools/postgres/BUILD`
- Create: `bazel/tools/postgres/oci_postgres.bzl`
- Create: `bazel/tools/postgres/extensions.bzl`
- Modify: `MODULE.bazel` (add oci.pull + use_repo + extension)

**Step 1: Create the BUILD file**

Create `bazel/tools/postgres/BUILD` — initially just a package marker. The actual filegroup comes from the repository rule's generated BUILD.

**Step 2: Write the OCI extraction rule**

Create `bazel/tools/postgres/oci_postgres.bzl`. This is a repository rule that:

1. Uses `crane` (available via rules_oci toolchain) to export the OCI image filesystem
2. Extracts the needed PostgreSQL binaries and pgvector extension files
3. Generates a BUILD file with a `filegroup`

The rule uses `rctx.execute` to run `crane export` which flattens all layers into a single tarball, then extracts only the files we need:

```
usr/lib/postgresql/16/bin/postgres
usr/lib/postgresql/16/bin/initdb
usr/lib/postgresql/16/bin/pg_isready
usr/lib/postgresql/16/bin/pg_ctl
usr/lib/postgresql/16/lib/vector.so
usr/share/postgresql/16/extension/vector.control
usr/share/postgresql/16/extension/vector--*.sql
```

Plus shared library dependencies under `usr/lib/` that PostgreSQL needs at runtime.

The generated BUILD file:

```python
filegroup(
    name = "postgres",
    srcs = glob(["**/*"]),
    visibility = ["//visibility:public"],
)
```

**Step 3: Create the module extension**

Create `bazel/tools/postgres/extensions.bzl` that registers the repository rule.

**Step 4: Add OCI pull to MODULE.bazel**

Add after the existing `oci.pull` blocks (around line 255):

```python
# PostgreSQL 16 + pgvector for e2e integration tests
oci.pull(
    name = "pgvector_pg16",
    image = "docker.io/pgvector/pgvector",
    platforms = ["linux/amd64"],
    tag = "pg16",
    # Pin digest after first successful pull
)
use_repo(oci, "pgvector_pg16", "pgvector_pg16_linux_amd64")
```

Register the extension:

```python
postgres = use_extension("//bazel/tools/postgres:extensions.bzl", "postgres")
use_repo(postgres, "postgres_test")
```

**Step 5: Verify the rule works**

Run: `bb remote build @postgres_test//:postgres --config=ci`

Expected: Build succeeds, filegroup contains the PostgreSQL binaries.

**Step 6: Commit**

```
git add bazel/tools/postgres/ MODULE.bazel
git commit -m "build: add Bazel rule to extract PostgreSQL + pgvector from OCI"
```

---

### Task 2: Migration Files as Bazel Data

Expose the migration SQL files so e2e tests can reference them as data dependencies.

**Files:**

- Create: `projects/monolith/chart/migrations/BUILD`

**Step 1: Create the BUILD file**

Create `projects/monolith/chart/migrations/BUILD`:

```python
filegroup(
    name = "migrations",
    srcs = glob(["*.sql"]),
    visibility = ["//projects/monolith:__subpackages__"],
)
```

Note: Exclude `atlas.sum` -- only SQL files are needed.

**Step 2: Verify**

Run: `bb remote build //projects/monolith/chart/migrations:migrations --config=ci`

Expected: Build succeeds.

**Step 3: Commit**

```
git add projects/monolith/chart/migrations/BUILD
git commit -m "build(monolith): expose migration SQL files as Bazel filegroup"
```

---

### Task 3: PostgreSQL Pytest Fixture (conftest.py)

Create the shared conftest.py that manages the PostgreSQL lifecycle for all e2e tests.

**Files:**

- Create: `projects/monolith/e2e/__init__.py` (empty)
- Create: `projects/monolith/e2e/conftest.py`

**Step 1: Write the PostgreSQL fixture**

Create `projects/monolith/e2e/conftest.py` with these fixtures:

**`pg` (session-scoped):**

- Find PostgreSQL binaries via `TEST_SRCDIR` Bazel runfiles
- Find migration SQL files via runfiles
- `initdb` into a temp directory
- Start `postgres` on a random free port with correct `LD_LIBRARY_PATH`, `dynamic_library_path`, and `extension_dir`
- Wait for ready via `pg_isready` (max 6 seconds, polling every 200ms)
- Create database `monolith` + `CREATE EXTENSION vector`
- Apply all 5 migration SQL files in sorted order
- Yield a `PgInfo` object with `.url` and `.port`
- On teardown: terminate postgres process, remove temp directory

**`session` (function-scoped with SAVEPOINT rollback):**

- Create engine from `pg.url`
- Open connection, begin transaction
- Begin nested transaction (SAVEPOINT)
- Yield SQLModel Session bound to the connection
- On teardown: rollback nested, rollback outer, close connection

**`client` (function-scoped FastAPI TestClient):**

- Override `get_session` dependency to use the SAVEPOINT session
- Mock vault API (httpx.AsyncClient patched)
- Patch `asyncio.create_task` to prevent real background tasks
- Yield TestClient with `raise_server_exceptions=False`

**`embed_client` (function-scoped deterministic mock):**

- `embed()` returns deterministic 1024-dim unit vectors via SHA256 hash of input text
- Identical text always produces identical vectors

**`store` (function-scoped MessageStore):**

- `MessageStore(session=session, embed_client=embed_client)`
- Backed by real PostgreSQL

**Step 2: Write a smoke test**

Add to `projects/monolith/e2e/e2e_test.py`:

```python
def test_postgres_is_running(pg):
    from sqlmodel import create_engine, text
    engine = create_engine(pg.url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1
    engine.dispose()
```

**Step 3: Commit**

```
git add projects/monolith/e2e/
git commit -m "test(monolith): add e2e conftest with real PostgreSQL fixture"
```

---

### Task 4: HTTP API E2E Tests

Test all HTTP endpoints against real PostgreSQL. These replace the behavioral coverage from `app/integration_test.py`.

**Files:**

- Modify: `projects/monolith/e2e/e2e_test.py`

**Step 1: Write the HTTP API tests**

Add test classes to `e2e_test.py`:

- `TestHealthz` -- GET /healthz returns 200 OK
- `TestHomeAPI`:
  - `test_get_returns_empty_initial_state` -- GET /api/home returns weekly + daily
  - `test_put_then_get_persists_tasks` -- PUT tasks then GET verifies persistence
  - `test_reset_daily_clears_tasks_and_creates_archive` -- PUT, reset daily, verify archive
  - `test_reset_weekly_clears_weekly_task` -- PUT, reset weekly, verify cleared
  - `test_archive_invalid_date_returns_400` -- bad date format
  - `test_archive_not_found_returns_404` -- no archive for date
- `TestNotesAPI`:
  - `test_create_note` -- POST returns 201 (vault mocked)
  - `test_empty_content_returns_400`
  - `test_whitespace_content_returns_400`
- `TestScheduleAPI`:
  - `test_today_returns_list` -- returns list (iCal mocked)

**Step 2: Add Bazel test target to BUILD**

Add `py_test` target `e2e_test` with:

- `size = "large"`, `timeout = "moderate"`, `tags = ["e2e"]`
- `data` deps: `@postgres_test//:postgres`, `//projects/monolith/chart/migrations:migrations`
- `deps`: `:monolith_backend` plus pytest, fastapi, httpx, sqlmodel, psycopg, pydantic_ai_slim, pytest_asyncio, tzdata

**Step 3: Run tests**

Run: `bb remote test //projects/monolith:e2e_test --config=ci`

Expected: All HTTP API tests pass against real PostgreSQL.

**Step 4: Commit**

```
git add projects/monolith/e2e/ projects/monolith/BUILD
git commit -m "test(monolith): add HTTP API e2e tests against real PostgreSQL"
```

---

### Task 5: MessageStore E2E Tests (pgvector)

Test the data layer that SQLite can't validate -- pgvector similarity search, schema-qualified tables, blob dedup, and constraint enforcement.

**Files:**

- Modify: `projects/monolith/e2e/e2e_test.py`

**Step 1: Write the MessageStore tests**

Add `TestMessageStore` class with:

- `test_save_and_get_recent` -- save message, get_recent returns it with correct fields
- `test_duplicate_message_id_returns_none` -- IntegrityError on duplicate discord_message_id
- `test_search_similar_finds_matching_message` -- save with embedding, search with same text, pgvector `<=>` returns it
- `test_search_similar_filters_by_channel` -- messages in other channels excluded
- `test_search_similar_filters_by_user` -- user_id filter works
- `test_attachment_blob_dedup` -- two messages with same image data share one blob row (SHA256 PK)
- `test_get_attachments_joins_blobs` -- returns (Attachment, Blob) tuples correctly
- `test_upsert_summary_insert_and_update` -- insert then update same (channel, user) pair
- `test_upsert_summary_unique_constraint` -- (channel_id, user_id) enforced by real PG, exactly one row

All store tests that touch embeddings use `@pytest.mark.asyncio` since `save_message` and `embed_client.embed` are async.

**Step 2: Run tests**

Run: `bb remote test //projects/monolith:e2e_test --config=ci`

Expected: All MessageStore tests pass -- particularly `test_search_similar_*` which use pgvector's `<=>` operator.

**Step 3: Commit**

```
git add projects/monolith/e2e/e2e_test.py
git commit -m "test(monolith): add MessageStore e2e tests with real pgvector"
```

---

### Task 6: Agent Tool Execution E2E Tests

Test the PydanticAI agent's tool execution chain against real PostgreSQL, using `TestModel` and `FunctionModel` instead of the real LLM.

**Files:**

- Modify: `projects/monolith/e2e/e2e_test.py`

**Step 1: Write agent tool tests**

Read `projects/monolith/chat/agent.py` for exact tool signatures and `ChatDeps` structure. Add `TestAgentTools` class:

- `test_search_history_returns_real_pgvector_results` -- seed a message, create agent with `TestModel`, run with deps pointing at real store. Verify agent produces output without errors. The key assertion is that the tool chain (embed query -> pgvector search -> format results) completes successfully against real Postgres.

- `test_get_user_summary_returns_real_data` -- upsert a summary into real PG, create agent with `TestModel`, run query about the user. Verify the agent can retrieve the summary through its tool.

Use `TestModel(custom_result_text="...")` to control LLM output while allowing tool execution to hit real Postgres.

**Step 2: Run tests**

Run: `bb remote test //projects/monolith:e2e_test --config=ci`

Expected: Agent tool tests pass with real PostgreSQL backing the store.

**Step 3: Commit**

```
git add projects/monolith/e2e/e2e_test.py
git commit -m "test(monolith): add agent tool execution e2e tests"
```

---

### Task 7: Playwright UI E2E Tests

Test the SvelteKit frontend flows against a live FastAPI + PostgreSQL backend.

**Files:**

- Create: `projects/monolith/e2e/e2e_playwright_test.py`
- Modify: `projects/monolith/e2e/conftest.py` (add live_server fixture)
- Modify: `projects/monolith/BUILD` (add playwright test target)
- Possibly modify: `projects/monolith/frontend/src/` (add data-testid attributes)

**Step 1: Add live_server fixture to conftest.py**

Add a session-scoped `live_server` fixture that:

- Sets `DATABASE_URL` env var to `pg.url`
- Starts uvicorn in a background thread on a random port
- Waits for server to be ready
- Yields the base URL (e.g., `http://127.0.0.1:PORT`)
- On teardown: signals server to exit, joins thread

**Step 2: Read the frontend source**

Read `projects/monolith/frontend/src/` to identify the actual component selectors. Determine whether `data-testid` attributes exist or need to be added.

**Step 3: Write Playwright tests**

Create `projects/monolith/e2e/e2e_playwright_test.py` with:

- `TestHomePage`:
  - `test_page_loads_with_task_slots` -- verify page renders weekly and daily task areas
  - `test_edit_and_save_tasks` -- fill in tasks, save, reload, verify persistence
  - `test_daily_reset_clears_tasks` -- set tasks, reset daily, verify cleared + archive

Use selectors that match the actual frontend markup (determined in step 2).

**Step 4: Add Bazel test target**

Add `py_test` target `e2e_playwright_test` with:

- `size = "large"`, `timeout = "long"`, `tags = ["e2e", "playwright"]`
- `data` deps: `@postgres_test//:postgres`, migrations, `:frontend_dist`
- `deps`: monolith_backend, playwright, uvicorn, fastapi, psycopg, pytest, sqlmodel, tzdata

**Step 5: Run tests**

Run: `bb remote test //projects/monolith:e2e_playwright_test --config=ci`

Expected: All Playwright tests pass.

**Step 6: Commit**

```
git add projects/monolith/e2e/ projects/monolith/BUILD
git commit -m "test(monolith): add Playwright UI e2e tests"
```

---

### Task 8: CI Verification and Cleanup

Verify the full test suite passes in CI and clean up redundant unit tests that are now covered by e2e tests.

**Files:**

- Review: `projects/monolith/app/integration_test.py` (candidate for removal)
- Modify: `projects/monolith/BUILD` (remove redundant test targets if applicable)

**Step 1: Run full CI test suite**

Run: `bb remote test //projects/monolith/... --config=ci`

Expected: All tests pass -- both existing unit tests and new e2e tests.

**Step 2: Identify redundant tests**

Compare the e2e test coverage against existing tests. Candidates for removal:

- `app/integration_test.py` -- its CRUD flows are fully covered by `TestHomeAPI` in e2e
- Individual store tests that only test behavior (not implementation edge cases) and are now covered by `TestMessageStore` in e2e

Do NOT remove:

- Unit tests for implementation edge cases (e.g., `bot_backoff_test.py`, `vision_timeout_test.py`)
- Tests that cover error handling paths not exercised by e2e
- Tests for pure functions (e.g., `_coerce_username`, `_build_embed_text`)

**Step 3: Remove redundant tests and their BUILD targets**

For each removed test file, delete the corresponding `py_test` target from BUILD.

**Step 4: Run CI again**

Run: `bb remote test //projects/monolith/... --config=ci`

Expected: All remaining tests pass.

**Step 5: Commit**

```
git add -u projects/monolith/
git commit -m "refactor(monolith): remove unit tests superseded by e2e suite"
```

**Step 6: Create PR**

```
git push -u origin feat/monolith-e2e-tests
gh pr create --title "test(monolith): add e2e integration tests with real PostgreSQL + pgvector" --body "..."
```
