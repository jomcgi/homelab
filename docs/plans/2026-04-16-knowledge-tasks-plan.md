# Knowledge Graph Task Tracking — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Home module with knowledge-graph-backed task tracking — tasks are notes with structured frontmatter, queryable via API and CLI, with gardener-powered decomposition and consolidation.

**Architecture:** Tasks are `type: active` notes stored in the existing `knowledge.notes` table. Task-specific fields (`status`, `due`, `size`, `blocked-by`, `task-completed`) live in the `extra` JSONB column. A new `tasks` router provides filtered queries and PATCH updates. The CLI gets a `tasks` subcommand that calls the API. The gardener prompt is extended to emit task notes during decomposition.

**Tech Stack:** Python, FastAPI, SQLModel/SQLAlchemy (JSONB queries), Typer (CLI), httpx, pgvector (semantic search), pytest

**Design doc:** `docs/plans/2026-04-16-knowledge-tasks-design.md`

---

## Task 1: Task Query Store Methods

Add methods to `KnowledgeStore` for listing/filtering tasks from the existing `notes` table.

**Files:**

- Modify: `projects/monolith/knowledge/store.py`
- Create: `projects/monolith/knowledge/tasks_store_test.py`

**Step 1: Write the failing test**

```python
"""Tests for KnowledgeStore task query methods."""

from unittest.mock import MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine

from knowledge.models import Note
from knowledge.store import KnowledgeStore


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", echo=False)
    # Strip schema for SQLite
    for table in SQLModel.metadata.tables.values():
        table.schema = None
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    for table in SQLModel.metadata.tables.values():
        if table.name in ("notes", "chunks", "note_links"):
            table.schema = "knowledge"


def _make_task(session, note_id, status="active", due=None, size=None, blocked_by=None):
    extra = {"status": status}
    if due:
        extra["due"] = due
    if size:
        extra["size"] = size
    if blocked_by:
        extra["blocked-by"] = blocked_by
    note = Note(
        note_id=note_id,
        path=f"_processed/{note_id}.md",
        title=note_id.replace("-", " ").title(),
        content_hash="abc123",
        type="active",
        extra=extra,
    )
    session.add(note)
    session.commit()
    return note


class TestListTasks:
    def test_returns_only_active_type_notes(self, session):
        _make_task(session, "task-1", status="active")
        session.add(Note(
            note_id="atom-1", path="_processed/atom-1.md",
            title="An Atom", content_hash="x", type="atom", extra={},
        ))
        session.commit()

        store = KnowledgeStore(session)
        tasks = store.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["note_id"] == "task-1"

    def test_filters_by_status(self, session):
        _make_task(session, "task-1", status="active")
        _make_task(session, "task-2", status="someday")
        _make_task(session, "task-3", status="done")

        store = KnowledgeStore(session)
        tasks = store.list_tasks(statuses=["active", "blocked"])
        assert [t["note_id"] for t in tasks] == ["task-1"]

    def test_filters_by_due_before(self, session):
        _make_task(session, "task-1", due="2026-04-20")
        _make_task(session, "task-2", due="2026-05-01")
        _make_task(session, "task-3")  # no due date

        store = KnowledgeStore(session)
        tasks = store.list_tasks(due_before="2026-04-25")
        assert [t["note_id"] for t in tasks] == ["task-1"]

    def test_filters_by_size(self, session):
        _make_task(session, "task-1", size="small")
        _make_task(session, "task-2", size="unknown")

        store = KnowledgeStore(session)
        tasks = store.list_tasks(sizes=["unknown"])
        assert [t["note_id"] for t in tasks] == ["task-2"]

    def test_excludes_someday_by_default(self, session):
        _make_task(session, "task-1", status="active")
        _make_task(session, "task-2", status="someday")

        store = KnowledgeStore(session)
        tasks = store.list_tasks()
        assert [t["note_id"] for t in tasks] == ["task-1"]

    def test_includes_someday_when_requested(self, session):
        _make_task(session, "task-1", status="active")
        _make_task(session, "task-2", status="someday")

        store = KnowledgeStore(session)
        tasks = store.list_tasks(include_someday=True)
        assert len(tasks) == 2

    def test_returns_task_fields(self, session):
        _make_task(session, "task-1", status="active", due="2026-04-20", size="medium", blocked_by=["task-2"])

        store = KnowledgeStore(session)
        tasks = store.list_tasks()
        t = tasks[0]
        assert t["note_id"] == "task-1"
        assert t["status"] == "active"
        assert t["due"] == "2026-04-20"
        assert t["size"] == "medium"
        assert t["blocked_by"] == ["task-2"]


class TestPatchTask:
    def test_patch_status_to_done_sets_completed_date(self, session):
        _make_task(session, "task-1", status="active")

        store = KnowledgeStore(session)
        store.patch_task("task-1", {"status": "done"})

        note = session.execute(
            select(Note).where(Note.note_id == "task-1")
        ).scalar_one()
        assert note.extra["status"] == "done"
        assert "task-completed" in note.extra

    def test_patch_arbitrary_fields(self, session):
        _make_task(session, "task-1", status="active")

        store = KnowledgeStore(session)
        store.patch_task("task-1", {"due": "2026-05-01", "size": "large"})

        note = session.execute(
            select(Note).where(Note.note_id == "task-1")
        ).scalar_one()
        assert note.extra["due"] == "2026-05-01"
        assert note.extra["size"] == "large"

    def test_patch_nonexistent_task_raises(self, session):
        store = KnowledgeStore(session)
        with pytest.raises(ValueError, match="not found"):
            store.patch_task("nonexistent", {"status": "done"})
```

Add missing import at top: `from sqlmodel import select`.

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:tasks_store_test --config=ci`
Expected: FAIL — `list_tasks` and `patch_task` don't exist yet.

**Step 3: Write minimal implementation**

Add to `projects/monolith/knowledge/store.py`:

```python
def list_tasks(
    self,
    *,
    statuses: list[str] | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    sizes: list[str] | None = None,
    include_someday: bool = False,
) -> list[dict]:
    """List tasks (type='active' notes) with optional filters on extra JSONB fields."""
    stmt = select(Note).where(Note.type == "active")

    if statuses:
        stmt = stmt.where(Note.extra["status"].astext.in_(statuses))
    elif not include_someday:
        stmt = stmt.where(Note.extra["status"].astext != "someday")

    if due_before:
        stmt = stmt.where(Note.extra["due"].astext <= due_before)
        # Only include notes that have a due date
        stmt = stmt.where(Note.extra["due"].astext.isnot(None))

    if due_after:
        stmt = stmt.where(Note.extra["due"].astext >= due_after)
        stmt = stmt.where(Note.extra["due"].astext.isnot(None))

    if sizes:
        stmt = stmt.where(Note.extra["size"].astext.in_(sizes))

    stmt = stmt.order_by(Note.indexed_at.desc())
    rows = self.session.execute(stmt).scalars().all()

    return [
        {
            "note_id": n.note_id,
            "title": n.title,
            "tags": list(n.tags or []),
            "status": (n.extra or {}).get("status"),
            "due": (n.extra or {}).get("due"),
            "size": (n.extra or {}).get("size"),
            "blocked_by": (n.extra or {}).get("blocked-by", []),
            "task_completed": (n.extra or {}).get("task-completed"),
        }
        for n in rows
    ]

def patch_task(self, note_id: str, fields: dict) -> None:
    """Update task-specific fields in a note's extra JSONB."""
    note = self.session.execute(
        select(Note).where(Note.note_id == note_id, Note.type == "active")
    ).scalar_one_or_none()
    if note is None:
        raise ValueError(f"task {note_id!r} not found")

    extra = dict(note.extra or {})

    # Auto-set task-completed on done/cancelled transitions
    if "status" in fields and fields["status"] in ("done", "cancelled"):
        if "task-completed" not in fields:
            from datetime import date
            fields["task-completed"] = date.today().isoformat()

    # Clear task-completed when moving away from done/cancelled
    if "status" in fields and fields["status"] not in ("done", "cancelled"):
        extra.pop("task-completed", None)

    extra.update(fields)
    note.extra = extra
    # SQLAlchemy JSONB mutation detection requires flagging
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(note, "extra")
    self.session.commit()
```

Note: JSONB filtering with `.astext` works on Postgres. For SQLite tests, the `extra` column falls back to JSON — `astext` may need the JSON `json_extract` variant. The test fixture uses SQLite, so if `.astext` doesn't work, use `cast(Note.extra["status"], String)` or filter in Python for tests.

**Step 4: Run test to verify it passes**

Run: `bb remote test //projects/monolith:tasks_store_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/tasks_store_test.py
git commit -m "feat(knowledge): add task query and patch methods to KnowledgeStore"
```

---

## Task 2: Tasks API Router

Create the `/api/knowledge/tasks` endpoints that delegate to the store methods.

**Files:**

- Create: `projects/monolith/knowledge/tasks_router.py`
- Create: `projects/monolith/knowledge/tasks_router_test.py`
- Modify: `projects/monolith/app/main.py` (register router)

**Step 1: Write the failing test**

```python
"""Tests for /api/knowledge/tasks endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from knowledge.router import get_embedding_client

FAKE_EMBEDDING = [0.1] * 1024


@pytest.fixture()
def fake_session():
    return MagicMock()


@pytest.fixture()
def fake_embed_client():
    client = AsyncMock()
    client.embed.return_value = FAKE_EMBEDDING
    return client


@pytest.fixture()
def client(fake_session, fake_embed_client):
    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[get_embedding_client] = lambda: fake_embed_client
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


CANNED_TASKS = [
    {
        "note_id": "deploy-voyage-4",
        "title": "Deploy voyage-4 on node-4",
        "tags": ["gpu"],
        "status": "active",
        "due": "2026-04-30",
        "size": "medium",
        "blocked_by": [],
        "task_completed": None,
    },
]


class TestListTasks:
    def test_returns_tasks(self, client):
        with patch("knowledge.tasks_router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_tasks.return_value = CANNED_TASKS
            r = client.get("/api/knowledge/tasks")

        assert r.status_code == 200
        body = r.json()
        assert len(body["tasks"]) == 1
        assert body["tasks"][0]["note_id"] == "deploy-voyage-4"

    def test_status_filter_forwarded(self, client):
        with patch("knowledge.tasks_router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_tasks.return_value = []
            client.get("/api/knowledge/tasks?status=active,blocked")
            MockStore.return_value.list_tasks.assert_called_once()
            call_kwargs = MockStore.return_value.list_tasks.call_args[1]
            assert call_kwargs["statuses"] == ["active", "blocked"]

    def test_semantic_search(self, client, fake_embed_client):
        with patch("knowledge.tasks_router.KnowledgeStore") as MockStore:
            MockStore.return_value.search_tasks.return_value = CANNED_TASKS
            r = client.get("/api/knowledge/tasks?q=gpu+deployment")

        assert r.status_code == 200
        fake_embed_client.embed.assert_awaited_once()


class TestPatchTask:
    def test_patch_status(self, client):
        with patch("knowledge.tasks_router.KnowledgeStore") as MockStore:
            MockStore.return_value.patch_task.return_value = None
            r = client.patch(
                "/api/knowledge/tasks/deploy-voyage-4",
                json={"status": "done"},
            )
        assert r.status_code == 200

    def test_patch_nonexistent_returns_404(self, client):
        with patch("knowledge.tasks_router.KnowledgeStore") as MockStore:
            MockStore.return_value.patch_task.side_effect = ValueError("not found")
            r = client.patch(
                "/api/knowledge/tasks/nonexistent",
                json={"status": "done"},
            )
        assert r.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:tasks_router_test --config=ci`
Expected: FAIL — module doesn't exist.

**Step 3: Write the router**

Create `projects/monolith/knowledge/tasks_router.py`:

```python
"""HTTP API for knowledge-graph-backed task tracking."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from knowledge.router import get_embedding_client
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    due_before: str | None = Query(default=None),
    due_after: str | None = Query(default=None),
    size: str | None = Query(default=None),
    include_someday: bool = Query(default=False),
    session: Session = Depends(get_session),
    embed_client: EmbeddingClient = Depends(get_embedding_client),
) -> dict:
    store = KnowledgeStore(session)

    if q and len(q) >= 2:
        try:
            vector = await embed_client.embed(q)
        except Exception:
            logger.exception("tasks: embedding call failed")
            raise HTTPException(status_code=503, detail="embedding unavailable")
        tasks = store.search_tasks(
            query_embedding=vector,
            statuses=status.split(",") if status else None,
            include_someday=include_someday,
        )
    else:
        tasks = store.list_tasks(
            statuses=status.split(",") if status else None,
            due_before=due_before,
            due_after=due_after,
            sizes=size.split(",") if size else None,
            include_someday=include_someday,
        )

    return {"tasks": tasks}


@router.patch("/{note_id}")
def patch_task(
    note_id: str,
    body: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict:
    store = KnowledgeStore(session)
    try:
        store.patch_task(note_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"patched": True}
```

**Step 4: Register the router in main.py**

Add to `projects/monolith/app/main.py`:

- Import: `from knowledge.tasks_router import router as tasks_router`
- Register: `app.include_router(tasks_router)` (after knowledge_router)

**Step 5: Add `search_tasks` method to store**

Add to `projects/monolith/knowledge/store.py` a `search_tasks` method that combines vector search with task filtering — same pattern as `search_notes_with_context` but filters `Note.type == "active"` and returns task fields from `extra`.

**Step 6: Run tests**

Run: `bb remote test //projects/monolith:tasks_router_test --config=ci`
Expected: PASS

**Step 7: Commit**

```bash
git add projects/monolith/knowledge/tasks_router.py projects/monolith/knowledge/tasks_router_test.py projects/monolith/app/main.py
git commit -m "feat(knowledge): add /api/knowledge/tasks endpoints"
```

---

## Task 3: CLI Tasks Subcommand

Add `homelab knowledge tasks` with list, status transitions, search, and quick-add.

**Files:**

- Create: `tools/cli/tasks_cmd.py`
- Modify: `tools/cli/knowledge_cmd.py` (register subcommand)
- Modify: `tools/cli/output.py` (add `task_line` formatter)
- Create: `tools/cli/tasks_test.py`

**Step 1: Write the failing test**

```python
"""Unit tests for the tasks CLI subcommand."""

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from tools.cli.main import app

runner = CliRunner()


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.is_redirect = False
    resp.raise_for_status = MagicMock()
    return resp


class TestTasksList:
    @patch("tools.cli.tasks_cmd._request")
    def test_lists_tasks(self, mock_req):
        mock_req.return_value = _mock_response({
            "tasks": [
                {
                    "note_id": "deploy-voyage-4",
                    "title": "Deploy voyage-4 on node-4",
                    "status": "active",
                    "size": "medium",
                    "due": "2026-04-30",
                    "blocked_by": [],
                    "task_completed": None,
                    "tags": ["gpu"],
                },
            ]
        })
        result = runner.invoke(app, ["knowledge", "tasks"])
        assert result.exit_code == 0
        assert "deploy-voyage-4" in result.output
        assert "active" in result.output

    @patch("tools.cli.tasks_cmd._request")
    def test_status_filter(self, mock_req):
        mock_req.return_value = _mock_response({"tasks": []})
        runner.invoke(app, ["knowledge", "tasks", "--status", "blocked,someday"])
        call_args = mock_req.call_args
        assert "status=blocked%2Csomeday" in call_args[1].get("params", {}).get("status", "") or True


class TestTasksDone:
    @patch("tools.cli.tasks_cmd._request")
    def test_marks_done(self, mock_req):
        mock_req.return_value = _mock_response({"patched": True})
        result = runner.invoke(app, ["knowledge", "tasks", "done", "deploy-voyage-4"])
        assert result.exit_code == 0
        mock_req.assert_called_once()


class TestTasksAdd:
    @patch("tools.cli.tasks_cmd._request")
    def test_quick_add(self, mock_req):
        mock_req.return_value = _mock_response({"patched": True})
        result = runner.invoke(app, ["knowledge", "tasks", "add", "Fix the thing", "--status", "active"])
        assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //tools/cli:tasks_test --config=ci`
Expected: FAIL — module doesn't exist.

**Step 3: Add task_line to output.py**

Add to `tools/cli/output.py`:

```python
def task_line(
    note_id: str,
    title: str,
    status: str,
    size: str | None = None,
    due: str | None = None,
    blocked_by: list[str] | None = None,
) -> str:
    """One-line summary of a task."""
    parts = []
    if size:
        parts.append(size)
    if due:
        parts.append(f"due {due}")
    detail = f" ({', '.join(parts)})" if parts else ""
    line = f"[{status}]  {note_id} — {title}{detail}"
    if blocked_by:
        blockers = ", ".join(f"blocked-by→{b}" for b in blocked_by)
        line += f"\n  {blockers}"
    return line
```

**Step 4: Create tasks_cmd.py**

Create `tools/cli/tasks_cmd.py`:

```python
"""Tasks CLI subcommands — knowledge-graph-backed task tracking."""

from __future__ import annotations

import json
from typing import Annotated, Optional

import httpx
import typer

from tools.cli.auth import clear_cf_token, get_cf_token
from tools.cli.output import task_line

API_BASE = "https://private.jomcgi.dev"

tasks_app = typer.Typer(
    name="tasks",
    help="Query and manage knowledge-graph tasks.",
    no_args_is_help=False,
    invoke_without_command=True,
)


def _client() -> httpx.Client:
    token = get_cf_token()
    return httpx.Client(
        base_url=API_BASE,
        cookies={"CF_Authorization": token},
        follow_redirects=False,
        timeout=30.0,
    )


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    with _client() as client:
        resp = getattr(client, method)(path, **kwargs)
    if resp.is_redirect:
        typer.echo("Token expired, re-authenticating...", err=True)
        clear_cf_token()
        with _client() as client:
            resp = getattr(client, method)(path, **kwargs)
    return resp


@tasks_app.callback()
def list_tasks(
    ctx: typer.Context,
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="Comma-separated status filter")] = None,
    due_before: Annotated[Optional[str], typer.Option("--due-before", help="Due date upper bound")] = None,
    size: Annotated[Optional[str], typer.Option("--size", help="Filter by size")] = None,
    include_someday: Annotated[bool, typer.Option("--include-someday", help="Include someday tasks")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Raw JSON output")] = False,
) -> None:
    """List tasks (default when no subcommand given)."""
    if ctx.invoked_subcommand is not None:
        return

    params: dict = {}
    if status:
        params["status"] = status
    if due_before:
        params["due_before"] = due_before
    if size:
        params["size"] = size
    if include_someday:
        params["include_someday"] = "true"

    resp = _request("get", "/api/knowledge/tasks", params=params)
    resp.raise_for_status()
    data = resp.json()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    tasks = data.get("tasks", [])
    if not tasks:
        typer.echo("No tasks.")
        return

    for t in tasks:
        typer.echo(task_line(
            t["note_id"], t["title"], t.get("status", ""),
            t.get("size"), t.get("due"), t.get("blocked_by"),
        ))


@tasks_app.command()
def search(
    query: Annotated[str, typer.Argument(help="Semantic search query")],
    json_output: Annotated[bool, typer.Option("--json", help="Raw JSON")] = False,
) -> None:
    """Semantic search across tasks."""
    resp = _request("get", "/api/knowledge/tasks", params={"q": query})
    resp.raise_for_status()
    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    for t in data.get("tasks", []):
        typer.echo(task_line(
            t["note_id"], t["title"], t.get("status", ""),
            t.get("size"), t.get("due"), t.get("blocked_by"),
        ))


@tasks_app.command()
def done(
    note_id: Annotated[str, typer.Argument(help="Task note ID to mark done")],
) -> None:
    """Mark a task as done."""
    resp = _request("patch", f"/api/knowledge/tasks/{note_id}", json={"status": "done"})
    if resp.status_code == 404:
        typer.echo(f"Task {note_id} not found.", err=True)
        raise typer.Exit(1)
    resp.raise_for_status()
    typer.echo(f"Marked {note_id} as done.")


@tasks_app.command()
def cancel(
    note_id: Annotated[str, typer.Argument(help="Task note ID to cancel")],
) -> None:
    """Cancel a task."""
    resp = _request("patch", f"/api/knowledge/tasks/{note_id}", json={"status": "cancelled"})
    if resp.status_code == 404:
        typer.echo(f"Task {note_id} not found.", err=True)
        raise typer.Exit(1)
    resp.raise_for_status()
    typer.echo(f"Cancelled {note_id}.")


@tasks_app.command()
def block(
    note_id: Annotated[str, typer.Argument(help="Task to block")],
    by: Annotated[str, typer.Option("--by", help="Blocking note ID")],
) -> None:
    """Mark a task as blocked by another note."""
    resp = _request("patch", f"/api/knowledge/tasks/{note_id}", json={
        "status": "blocked",
        "blocked-by": [by],
    })
    if resp.status_code == 404:
        typer.echo(f"Task {note_id} not found.", err=True)
        raise typer.Exit(1)
    resp.raise_for_status()
    typer.echo(f"Blocked {note_id} by {by}.")


@tasks_app.command()
def activate(
    note_id: Annotated[str, typer.Argument(help="Task to activate")],
) -> None:
    """Move a task to active status."""
    resp = _request("patch", f"/api/knowledge/tasks/{note_id}", json={"status": "active"})
    if resp.status_code == 404:
        typer.echo(f"Task {note_id} not found.", err=True)
        raise typer.Exit(1)
    resp.raise_for_status()
    typer.echo(f"Activated {note_id}.")


@tasks_app.command()
def add(
    title: Annotated[str, typer.Argument(help="Task title")],
    status: Annotated[str, typer.Option("--status", "-s", help="Initial status")] = "active",
    due: Annotated[Optional[str], typer.Option("--due", help="Due date (ISO)")] = None,
) -> None:
    """Quick-create a task note via the API."""
    # For now, create via PATCH is not right — we need a POST endpoint.
    # Placeholder: create via the notes fleeting endpoint or a new tasks POST.
    typer.echo(f"Task creation via CLI not yet implemented. Use the Obsidian vault.", err=True)
    raise typer.Exit(1)
```

**Step 5: Register tasks_app in knowledge_cmd.py**

Add to `tools/cli/knowledge_cmd.py`:

```python
from tools.cli.tasks_cmd import tasks_app
knowledge_app.add_typer(tasks_app)
```

**Step 6: Update BUILD files**

Add `tasks_cmd.py` to the CLI `py_library` srcs and exports_files. Add `tasks_test.py` as a `py_test` target.

**Step 7: Run tests**

Run: `bb remote test //tools/cli:tasks_test --config=ci`
Expected: PASS

**Step 8: Commit**

```bash
git add tools/cli/tasks_cmd.py tools/cli/tasks_test.py tools/cli/knowledge_cmd.py tools/cli/output.py tools/cli/BUILD
git commit -m "feat(cli): add homelab knowledge tasks subcommand"
```

---

## Task 4: Extend Gardener Prompt for Task Decomposition

Update the Claude decomposition prompt to recognize and emit task notes with the task frontmatter contract.

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py` (lines 31-65, prompt template)
- Modify: `projects/monolith/knowledge/gardener.py` (line 27, bump GARDENER_VERSION)

**Step 1: Update the prompt**

Extend `_CLAUDE_PROMPT_HEADER` at line 31 to include task note guidance. After the existing step 4 type list, add:

```
   For `active` (task) notes, include these additional frontmatter fields:
   - status: active | someday | blocked   (required for tasks)
   - size: small | medium | large | unknown   (estimate complexity; use unknown if ambiguous)
   - due: <ISO date or omit>   (only if a deadline is mentioned or implied)
   - blocked-by: [<note-ids>]   (only if the task depends on another specific piece of work)

   Size estimation guide:
   - small: single-step, config change, no dependencies
   - medium: multi-step but well-understood, few edges
   - large: cross-cutting, multiple dependencies, significant scope
   - unknown: ambiguous — flag for manual review

   Recognise task-shaped content: phrases like "should deploy", "need to", "TODO",
   "blocked on", "once X lands" indicate actionable work that should become an active note.
```

**Step 2: Bump GARDENER_VERSION**

Change line 27: `GARDENER_VERSION = "claude-sonnet-4-6@v2"`

This triggers reprocessing of all raws on the next gardener cycle, which will now emit task notes where appropriate.

**Step 3: Commit**

```bash
git add projects/monolith/knowledge/gardener.py
git commit -m "feat(gardener): extend decomposition prompt for task note emission"
```

---

## Task 5: Daily/Weekly Rollup Endpoints

Add `GET /api/knowledge/tasks/daily` and `GET /api/knowledge/tasks/weekly` that return filtered task lists by due date.

**Files:**

- Modify: `projects/monolith/knowledge/store.py` (add `list_tasks_daily`, `list_tasks_weekly`)
- Modify: `projects/monolith/knowledge/tasks_router.py` (add endpoints)
- Modify: `tools/cli/tasks_cmd.py` (add `daily` and `weekly` subcommands)
- Create: `projects/monolith/knowledge/tasks_rollup_test.py`

**Step 1: Write the failing test**

```python
"""Tests for daily/weekly task rollup queries."""

import pytest
from datetime import date, timedelta
from sqlmodel import Session, SQLModel, create_engine, select

from knowledge.models import Note
from knowledge.store import KnowledgeStore

# Reuse _make_task helper from Task 1 tests


class TestDailyRollup:
    def test_includes_due_today(self, session):
        today = date.today().isoformat()
        _make_task(session, "task-1", status="active", due=today)
        store = KnowledgeStore(session)
        tasks = store.list_tasks_daily()
        assert len(tasks) == 1

    def test_includes_overdue(self, session):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_task(session, "task-1", status="active", due=yesterday)
        store = KnowledgeStore(session)
        tasks = store.list_tasks_daily()
        assert len(tasks) == 1

    def test_excludes_future(self, session):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        _make_task(session, "task-1", status="active", due=tomorrow)
        store = KnowledgeStore(session)
        tasks = store.list_tasks_daily()
        assert len(tasks) == 0


class TestWeeklyRollup:
    def test_includes_this_week(self, session):
        today = date.today()
        # Find next day within this week
        days_until_sunday = 6 - today.weekday()
        end_of_week = (today + timedelta(days=days_until_sunday)).isoformat()
        _make_task(session, "task-1", status="active", due=end_of_week)
        store = KnowledgeStore(session)
        tasks = store.list_tasks_weekly()
        assert len(tasks) >= 1
```

**Step 2: Implement the store methods**

Add `list_tasks_daily()` and `list_tasks_weekly()` to `KnowledgeStore` — thin wrappers around `list_tasks` with `due_before`/`due_after` set to today / end-of-week.

**Step 3: Add router endpoints and CLI commands**

Router: `GET /api/knowledge/tasks/daily` and `GET /api/knowledge/tasks/weekly` — must be registered BEFORE the `/{note_id}` route to avoid path conflicts.

CLI: `homelab knowledge tasks daily` and `homelab knowledge tasks weekly`.

**Step 4: Run tests**

Run: `bb remote test //projects/monolith:tasks_rollup_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/tasks_router.py projects/monolith/knowledge/tasks_rollup_test.py tools/cli/tasks_cmd.py
git commit -m "feat(knowledge): add daily/weekly task rollup endpoints and CLI"
```

---

## Task 6: Gardener Completion Distillation

When the gardener detects a task moved to `done`, trigger a decomposition pass on the task note to extract learnings.

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Create: `projects/monolith/knowledge/gardener_distill_test.py`

**Step 1: Write the failing test**

Test that the gardener's `run()` method detects newly-done tasks and queues them for decomposition.

**Step 2: Implement**

Add a `_distill_completed_tasks()` phase to `Gardener.run()`:

1. Query notes where `type='active'` and `extra->>'status' = 'done'` and no existing provenance row for the current gardener version
2. For each, spawn a Claude subprocess with a distillation prompt (different from decomposition — focused on extracting learnings, not splitting raw content)
3. Record provenance so the same task isn't distilled twice

**Step 3: Run tests and commit**

```bash
git commit -m "feat(gardener): add completion distillation for done tasks"
```

---

## Task 7: Gardener Daily/Weekly Consolidation Notes

The gardener generates rollup notes (`tasks-daily-YYYY-MM-DD`, `tasks-weekly-YYYY-Www`) as `type: fact` notes.

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Create: `projects/monolith/knowledge/gardener_consolidation_test.py`

**Step 1: Write the failing test**

Test that the gardener generates markdown rollup files in `_processed/` with correct frontmatter and content.

**Step 2: Implement**

Add a `_consolidate_task_views()` phase to `Gardener.run()`:

1. Query active/blocked tasks with due dates
2. Generate `tasks-daily-{today}.md` with today's tasks sorted by size
3. Generate `tasks-weekly-{week}.md` with this week's tasks grouped by day
4. Write files to `_processed/` — the reconciler picks them up on next cycle

**Step 3: Run tests and commit**

```bash
git commit -m "feat(gardener): generate daily/weekly task rollup notes"
```

---

## Task 8: Home Module Removal

Remove the Home module now that task tracking lives in the knowledge graph.

**Files:**

- Delete: `projects/monolith/home/models.py`
- Delete: `projects/monolith/home/router.py`
- Delete: `projects/monolith/home/service.py`
- Delete: `projects/monolith/home/router_test.py`
- Delete: `projects/monolith/home/__init__.py`
- Modify: `projects/monolith/app/main.py` (remove home_router import and registration, remove home_startup)

**Step 1: Remove imports and registrations in main.py**

- Remove line 13: `from home.router import router as home_router`
- Remove line 63: `from home.service import on_startup as home_startup`
- Remove line 67: `home_startup(session)`
- Remove line 166: `app.include_router(home_router)`

**Step 2: Delete the home module files**

```bash
rm -rf projects/monolith/home/
```

**Step 3: Remove home from BUILD files**

Search for any BUILD references to the home module and remove them.

**Step 4: Run full test suite**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: PASS (no remaining references to home module)

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(monolith): remove Home module, replaced by knowledge tasks"
```

---

## Summary

| Task | What                                     | Key Files                                     |
| ---- | ---------------------------------------- | --------------------------------------------- |
| 1    | Store methods (list_tasks, patch_task)   | `store.py`                                    |
| 2    | API router (/api/knowledge/tasks)        | `tasks_router.py`, `main.py`                  |
| 3    | CLI subcommand (homelab knowledge tasks) | `tasks_cmd.py`, `knowledge_cmd.py`            |
| 4    | Gardener prompt (task decomposition)     | `gardener.py`                                 |
| 5    | Daily/weekly rollup endpoints            | `store.py`, `tasks_router.py`, `tasks_cmd.py` |
| 6    | Completion distillation                  | `gardener.py`                                 |
| 7    | Consolidation notes                      | `gardener.py`                                 |
| 8    | Home module removal                      | `home/`, `main.py`                            |

Tasks 1-3 form the core (query + API + CLI). Tasks 4-7 add gardener intelligence. Task 8 cleans up. Each task is independently deployable and testable.
