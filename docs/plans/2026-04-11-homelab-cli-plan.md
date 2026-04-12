# Homelab CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `homelab` CLI at `tools/cli/` with knowledge subcommands, fix the HTTPRoute, and consolidate skills.

**Architecture:** Typer app with per-domain modules. Each domain registers as a typer subgroup in `main.py`. Shared auth and output formatting modules. Tests use FastAPI TestClient for full round-trip coverage.

**Tech Stack:** Python, typer, httpx, Bazel (`py_venv_binary`, `py_test`)

**Design doc:** `docs/plans/2026-04-11-homelab-cli-design.md`

**Worktree:** `/tmp/claude-worktrees/homelab-cli` (branch `feat/homelab-cli`)

---

### Task 1: Scaffold CLI with auth module

**Files:**

- Create: `tools/cli/__init__.py`
- Create: `tools/cli/main.py`
- Create: `tools/cli/auth.py`
- Create: `tools/cli/auth_test.py`
- Create: `tools/cli/BUILD`

**Step 1: Write failing test for `get_cf_token`**

Create `tools/cli/auth_test.py`:

```python
"""Tests for Cloudflare Access token management."""

from pathlib import Path
from unittest.mock import patch

import pytest

from auth import get_cf_token


class TestGetCfToken:
    def test_returns_token_from_existing_file(self, tmp_path):
        token_file = tmp_path / "private.jomcgi.dev-token"
        token_file.write_text("my-cf-token")
        with patch("auth.CF_TOKEN_DIR", tmp_path):
            assert get_cf_token() == "my-cf-token"

    def test_raises_when_no_token_and_cloudflared_missing(self, tmp_path):
        with (
            patch("auth.CF_TOKEN_DIR", tmp_path),
            patch("auth.shutil.which", return_value=None),
        ):
            with pytest.raises(SystemExit):
                get_cf_token()

    def test_runs_cloudflared_login_when_no_token(self, tmp_path):
        token_file = tmp_path / "private.jomcgi.dev-token"
        call_count = 0

        def fake_login(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            token_file.write_text("fresh-token")

        with (
            patch("auth.CF_TOKEN_DIR", tmp_path),
            patch("auth.shutil.which", return_value="/usr/local/bin/cloudflared"),
            patch("auth.subprocess.run", side_effect=fake_login),
        ):
            result = get_cf_token()
            assert result == "fresh-token"
            assert call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //tools/cli:auth_test --config=ci`
Expected: FAIL — module `auth` not found.

**Step 3: Write `auth.py`**

Create `tools/cli/auth.py`:

```python
"""Cloudflare Access token management.

Reads cached tokens from ~/.cloudflared/ or triggers interactive login
via `cloudflared access login`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CF_TOKEN_DIR = Path.home() / ".cloudflared"
DEFAULT_HOSTNAME = "private.jomcgi.dev"


def get_cf_token(hostname: str = DEFAULT_HOSTNAME) -> str:
    """Return a valid Cloudflare Access token for *hostname*.

    Checks ~/.cloudflared/ for an existing token file. If none found,
    runs ``cloudflared access login`` interactively, then reads the
    newly created token.

    Raises SystemExit if cloudflared is not installed.
    """
    token = _read_token(hostname)
    if token:
        return token

    if not shutil.which("cloudflared"):
        raise SystemExit(
            "cloudflared is not installed. "
            "Install it to authenticate with Cloudflare Access."
        )

    subprocess.run(
        ["cloudflared", "access", "login", f"https://{hostname}"],
        check=True,
    )

    token = _read_token(hostname)
    if not token:
        raise SystemExit(f"Failed to obtain token after login for {hostname}")
    return token


def _read_token(hostname: str) -> str | None:
    """Read the most recent token file matching *hostname*."""
    if not CF_TOKEN_DIR.is_dir():
        return None
    matches = sorted(CF_TOKEN_DIR.glob(f"*{hostname}*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        return None
    return matches[0].read_text().strip()
```

Create `tools/cli/__init__.py` (empty).

Create `tools/cli/main.py`:

```python
"""Homelab CLI — token-efficient cluster tooling for Claude Code."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="homelab",
    help="Token-efficient CLI for homelab operations.",
    no_args_is_help=True,
)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

**Step 4: Write BUILD file**

Create `tools/cli/BUILD`:

```starlark
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_library(
    name = "homelab_cli",
    srcs = glob(
        ["**/*.py"],
        exclude = ["**/*_test.py"],
    ),
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
        "@pip//typer",
    ],
)

py_venv_binary(
    name = "main",
    srcs = glob(
        ["**/*.py"],
        exclude = ["**/*_test.py"],
    ),
    imports = ["."],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
        "@pip//typer",
    ],
)

py_test(
    name = "auth_test",
    srcs = ["auth_test.py"],
    imports = ["."],
    deps = [
        ":homelab_cli",
        "@pip//pytest",
    ],
)
```

**Step 5: Run tests to verify they pass**

Run: `bb remote test //tools/cli:auth_test --config=ci`
Expected: PASS

**Step 6: Commit**

```bash
git add tools/cli/
git commit -m "feat(cli): scaffold homelab CLI with auth module"
```

---

### Task 2: Output formatting module

**Files:**

- Create: `tools/cli/output.py`
- Create: `tools/cli/output_test.py`

**Step 1: Write failing test for output helpers**

Create `tools/cli/output_test.py`:

```python
"""Tests for token-efficient output formatting."""

from pathlib import Path
from unittest.mock import patch

from output import compact_line, write_to_tmpfile, format_edges


class TestCompactLine:
    def test_basic_format(self):
        result = compact_line(42, "some/path.md", "obsidian", "bad JSON", 3)
        assert result == "[42] some/path.md (obsidian) — bad JSON [3 retries]"

    def test_no_error(self):
        result = compact_line(1, "path.md", "youtube", None, 0)
        assert result == "[1] path.md (youtube)"


class TestFormatEdges:
    def test_typed_edges(self):
        edges = [
            {"kind": "edge", "edge_type": "derives_from", "target_id": "note-a"},
            {"kind": "edge", "edge_type": "related", "target_id": "note-b"},
        ]
        result = format_edges(edges)
        assert result == "derives_from→note-a, related→note-b"

    def test_empty(self):
        assert format_edges([]) == ""


class TestWriteToTmpfile:
    def test_writes_content_and_returns_path(self, tmp_path):
        with patch("output.TMPDIR", tmp_path):
            path = write_to_tmpfile("my-note", "# Hello\nWorld")
            assert path.exists()
            assert path.read_text() == "# Hello\nWorld"
            assert "my-note" in path.name

    def test_overwrites_existing(self, tmp_path):
        with patch("output.TMPDIR", tmp_path):
            write_to_tmpfile("note", "v1")
            path = write_to_tmpfile("note", "v2")
            assert path.read_text() == "v2"
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //tools/cli:output_test --config=ci`
Expected: FAIL — module not found.

**Step 3: Write `output.py`**

Create `tools/cli/output.py`:

```python
"""Token-efficient output formatting for Claude Code consumption."""

from __future__ import annotations

from pathlib import Path

TMPDIR = Path("/tmp/homelab-cli/notes")


def compact_line(
    id: int,
    path: str,
    source: str,
    error: str | None = None,
    retry_count: int = 0,
) -> str:
    """One-line summary of a dead-lettered raw."""
    base = f"[{id}] {path} ({source})"
    if error:
        return f"{base} — {error} [{retry_count} retries]"
    return base


def search_line(
    score: float,
    note_id: str,
    title: str,
    note_type: str,
    edges: list[dict],
) -> str:
    """One-line summary of a search result with optional edge line."""
    line = f"[{score:.2f}] {note_id} — {title} ({note_type})"
    edge_str = format_edges(edges)
    if edge_str:
        line += f"\n  {edge_str}"
    return line


def format_edges(edges: list[dict]) -> str:
    """Compact edge representation: type→target, type→target."""
    typed = [e for e in edges if e.get("kind") == "edge"]
    if not typed:
        return ""
    return ", ".join(f"{e['edge_type']}→{e['target_id']}" for e in typed)


def write_to_tmpfile(name: str, content: str) -> Path:
    """Write content to a tmpfile and return the path."""
    TMPDIR.mkdir(parents=True, exist_ok=True)
    path = TMPDIR / f"{name}.md"
    path.write_text(content)
    return path
```

**Step 4: Add test target to BUILD**

Append to `tools/cli/BUILD`:

```starlark
py_test(
    name = "output_test",
    srcs = ["output_test.py"],
    imports = ["."],
    deps = [
        ":homelab_cli",
        "@pip//pytest",
    ],
)
```

**Step 5: Run tests**

Run: `bb remote test //tools/cli:output_test --config=ci`
Expected: PASS

**Step 6: Commit**

```bash
git add tools/cli/output.py tools/cli/output_test.py tools/cli/BUILD
git commit -m "feat(cli): add token-efficient output formatting"
```

---

### Task 3: Knowledge subcommands

**Files:**

- Create: `tools/cli/knowledge.py`
- Create: `tools/cli/knowledge_test.py`
- Modify: `tools/cli/main.py` (register subgroup)
- Modify: `tools/cli/BUILD` (add test target + monolith dep)

**Step 1: Write failing tests for knowledge commands**

Create `tools/cli/knowledge_test.py`:

```python
"""Tests for knowledge CLI subcommands.

Uses FastAPI TestClient to exercise the full round-trip:
CLI command → httpx call → FastAPI handler → response → formatted output.
"""

from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from knowledge.gardener import Gardener
from knowledge.models import AtomRawProvenance, RawInput
from main import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def session():
    from sqlmodel import Session, SQLModel, create_engine
    from sqlmodel.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            yield s
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


@pytest.fixture(autouse=True)
def _patch_fastapi(session):
    """Point the CLI's httpx calls at the FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    from app.db import get_session

    fastapi_app.dependency_overrides[get_session] = lambda: session
    client = TestClient(fastapi_app)

    # Patch httpx.Client used by knowledge.py to route to TestClient
    with patch("knowledge.httpx.Client") as mock_cls:
        mock_instance = mock_cls.return_value.__enter__ = lambda self: client
        mock_cls.return_value.__exit__ = lambda self, *args: None
        mock_cls.return_value.get = client.get
        mock_cls.return_value.post = client.post
        yield

    fastapi_app.dependency_overrides.clear()


def _make_raw(session, *, raw_id="raw-1", path="raw/test.md", source="test"):
    raw = RawInput(
        raw_id=raw_id, path=path, source=source,
        content="test content", content_hash="abc123",
    )
    session.add(raw)
    session.commit()
    session.refresh(raw)
    return raw


def _make_dead_letter(session, raw, *, error="boom", retry_count=3):
    prov = AtomRawProvenance(
        raw_fk=raw.id, derived_note_id="failed",
        gardener_version="test-v1", error=error, retry_count=retry_count,
    )
    session.add(prov)
    session.commit()
    session.refresh(prov)
    return prov


class TestDeadLetters:
    def test_lists_dead_letters(self, runner, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)
        result = runner.invoke(app, ["knowledge", "dead-letters"])
        assert result.exit_code == 0
        assert "raw/test.md" in result.output
        assert "boom" in result.output

    def test_empty_list(self, runner, session):
        result = runner.invoke(app, ["knowledge", "dead-letters"])
        assert result.exit_code == 0
        assert "No dead letters" in result.output

    def test_json_output(self, runner, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)
        result = runner.invoke(app, ["knowledge", "dead-letters", "--json"])
        assert result.exit_code == 0
        assert '"items"' in result.output


class TestReplay:
    def test_replays_dead_letter(self, runner, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)
        result = runner.invoke(app, ["knowledge", "replay", str(raw.id)])
        assert result.exit_code == 0
        assert "Replayed" in result.output

    def test_404_for_unknown(self, runner, session):
        result = runner.invoke(app, ["knowledge", "replay", "9999"])
        assert result.exit_code == 1
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //tools/cli:knowledge_test --config=ci`
Expected: FAIL — module `knowledge` (CLI) not found.

**Step 3: Write `knowledge.py`**

Create `tools/cli/knowledge.py`:

```python
"""Knowledge graph CLI subcommands."""

from __future__ import annotations

import json
import sys
from typing import Annotated, Optional

import httpx
import typer

from auth import get_cf_token
from output import compact_line, format_edges, search_line, write_to_tmpfile

API_BASE = "https://private.jomcgi.dev"

knowledge_app = typer.Typer(
    name="knowledge",
    help="Search, read, and debug the knowledge graph.",
    no_args_is_help=True,
)


def _client() -> httpx.Client:
    token = get_cf_token()
    return httpx.Client(
        base_url=API_BASE,
        cookies={"CF_Authorization": token},
        timeout=30.0,
    )


@knowledge_app.command()
def search(
    query: Annotated[str, typer.Argument(help="Natural language search query")],
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 10,
    type: Annotated[Optional[str], typer.Option("--type", "-t", help="Filter by note type")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Raw JSON output")] = False,
) -> None:
    """Search the knowledge graph by natural language query."""
    params: dict = {"q": query, "limit": limit}
    if type:
        params["type"] = type

    with _client() as client:
        resp = client.get("/api/knowledge/search", params=params)
        resp.raise_for_status()

    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    results = data.get("results", [])
    if not results:
        typer.echo("No results.")
        return

    for r in results:
        typer.echo(search_line(
            r["score"], r["note_id"], r["title"],
            r.get("type", ""), r.get("edges", []),
        ))


@knowledge_app.command()
def note(
    note_id: Annotated[str, typer.Argument(help="Note ID to fetch")],
    json_output: Annotated[bool, typer.Option("--json", help="Raw JSON output")] = False,
) -> None:
    """Fetch a note and write its content to a tmpfile."""
    with _client() as client:
        resp = client.get(f"/api/knowledge/notes/{note_id}")
        resp.raise_for_status()

    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    tags = ", ".join(data.get("tags", []))
    edges = format_edges(data.get("edges", []))

    typer.echo(f"{data['title']} ({data.get('type', '')}) [{tags}]")
    if edges:
        typer.echo(f"Edges: {edges}")

    content = data.get("content", "")
    if content:
        path = write_to_tmpfile(note_id, content)
        typer.echo(f"Content: {path}")


@knowledge_app.command(name="dead-letters")
def dead_letters(
    json_output: Annotated[bool, typer.Option("--json", help="Raw JSON output")] = False,
) -> None:
    """List raws that exhausted all retry attempts."""
    with _client() as client:
        resp = client.get("/api/knowledge/dead-letter")
        resp.raise_for_status()

    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    items = data.get("items", [])
    if not items:
        typer.echo("No dead letters.")
        return

    for item in items:
        typer.echo(compact_line(
            item["id"], item["path"], item["source"],
            item.get("error"), item.get("retry_count", 0),
        ))


@knowledge_app.command()
def replay(
    raw_id: Annotated[int, typer.Argument(help="Raw ID to replay")],
) -> None:
    """Replay a dead-lettered raw so the gardener retries it."""
    with _client() as client:
        resp = client.post(f"/api/knowledge/dead-letter/{raw_id}/replay")

    if resp.status_code == 404:
        typer.echo(f"Raw {raw_id} not found or not dead-lettered.", err=True)
        raise typer.Exit(1)

    resp.raise_for_status()
    typer.echo(f"Replayed raw {raw_id}. It will be retried on the next gardener cycle.")
```

**Step 4: Register knowledge subgroup in `main.py`**

Update `tools/cli/main.py` to add:

```python
from knowledge import knowledge_app

app.add_typer(knowledge_app)
```

**Step 5: Update BUILD with knowledge test target**

The knowledge test needs the monolith backend as a dependency. Add to `tools/cli/BUILD`:

```starlark
# gazelle:resolve py knowledge.gardener //projects/monolith:monolith_backend
# gazelle:resolve py knowledge.models //projects/monolith:monolith_backend
# gazelle:resolve py app.main //projects/monolith:monolith_backend
# gazelle:resolve py app.db //projects/monolith:monolith_backend
py_test(
    name = "knowledge_test",
    srcs = ["knowledge_test.py"],
    imports = ["."],
    deps = [
        ":homelab_cli",
        "//projects/monolith:monolith_backend",
        "@pip//pytest",
    ],
)
```

**Step 6: Run tests**

Run: `bb remote test //tools/cli:knowledge_test --config=ci`
Expected: PASS

**Step 7: Commit**

```bash
git add tools/cli/knowledge.py tools/cli/knowledge_test.py tools/cli/main.py tools/cli/BUILD
git commit -m "feat(cli): add knowledge subcommands (search, note, dead-letters, replay)"
```

---

### Task 4: Fix HTTPRoute for knowledge API

**Files:**

- Modify: `projects/monolith/chart/templates/httproute-private.yaml`
- Modify: `projects/monolith/chart/Chart.yaml` (version bump)
- Modify: `projects/monolith/deploy/application.yaml` (targetRevision bump)

**Step 1: Read current chart version**

```bash
grep '^version:' projects/monolith/chart/Chart.yaml
grep 'targetRevision' projects/monolith/deploy/application.yaml
```

**Step 2: Replace two specific knowledge routes with single PathPrefix**

In `projects/monolith/chart/templates/httproute-private.yaml`, replace:

```yaml
# Knowledge API — pass through to backend without rewriting
- matches:
    - path:
        type: Exact
        value: /api/knowledge/search
  backendRefs:
    - name: { { include "monolith.fullname" . } }
      port: { { .Values.service.apiPort | int } }
- matches:
    - path:
        type: PathPrefix
        value: /api/knowledge/notes
  backendRefs:
    - name: { { include "monolith.fullname" . } }
      port: { { .Values.service.apiPort | int } }
```

With:

```yaml
# Knowledge API — pass through to backend without rewriting
- matches:
    - path:
        type: PathPrefix
        value: /api/knowledge
  backendRefs:
    - name: { { include "monolith.fullname" . } }
      port: { { .Values.service.apiPort | int } }
```

**Step 3: Bump chart version**

Increment patch version in `Chart.yaml` and matching `targetRevision` in `deploy/application.yaml`.

**Step 4: Validate with helm template**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A5 "api/knowledge"
```

**Step 5: Commit**

```bash
git add projects/monolith/chart/ projects/monolith/deploy/application.yaml
git commit -m "fix(monolith): route all /api/knowledge paths to backend"
```

---

### Task 5: Consolidate skills

**Files:**

- Modify: `.claude/skills/knowledge/SKILL.md` (rewrite to use CLI)
- Delete: `.claude/skills/debug-knowledge-ingest/` (merged into knowledge)

**Step 1: Rewrite knowledge skill**

Replace the curl/auth-based skill with CLI-based version:

```markdown
---
name: knowledge
description: >
  Search and read Joe's Obsidian knowledge graph, or debug ingest failures.
  Use when ANY context about Joe's thinking, decisions, opinions, knowledge base,
  prior work, or personal notes might be relevant — even if there's only a 1%
  chance. Also use for dead-lettered raws, gardener errors, or ingest debugging.
---

# Knowledge Graph

Query and debug the knowledge graph via the `homelab` CLI.

## Commands

### Search notes

`homelab knowledge search "query" [--limit N] [--type TYPE]`

Returns compact one-liners: `[score] note-id — Title (type)` with edges.

### Read a note

`homelab knowledge note <note_id>`

Prints metadata to stdout, writes full markdown to a tmpfile.
Use `Read` on the tmpfile path to access content on demand.

### Check dead letters

`homelab knowledge dead-letters`

Lists raws that exhausted all retry attempts.

### Replay a dead letter

`homelab knowledge replay <raw_id>`

Removes failed provenance so the gardener retries on its next cycle.

## Tips

- Search queries work best as natural language phrases
- All commands support `--json` for raw API output
- After replaying, re-check dead-letters after the next gardener cycle
- Follow `derives_from` edges upstream to find conceptual lineage
```

**Step 2: Delete debug-knowledge-ingest skill**

```bash
rm -rf .claude/skills/debug-knowledge-ingest/
```

**Step 3: Commit**

```bash
git add .claude/skills/
git commit -m "refactor(skills): consolidate knowledge skills to use homelab CLI"
```

---

### Task 6: Format, test all, and create PR

**Step 1: Run formatter**

```bash
format
```

**Step 2: Run all tests**

```bash
bb remote test //tools/cli/... --config=ci
```

**Step 3: Push and create PR**

```bash
git push -u origin feat/homelab-cli
gh pr create --title "feat(cli): add homelab CLI with knowledge subcommands" --body "..."
```
