# Knowledge Notes CRUD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add create/edit/delete note operations to the monolith's knowledge module as HTTP endpoints and MCP tools, replacing the vault-mcp proxy.

**Architecture:** Notes are written as markdown files to the vault root filesystem. The existing `move_phase` catalogues them into `_raw/`, `reconcile_raw_phase` creates DB records, and the gardener decomposes them. Edit/delete operate on notes already in the DB by resolving their vault file path. All three operations are exposed as both FastAPI endpoints (`/api/knowledge/notes`) and MCP tools on the shared `mcp` instance.

**Tech Stack:** Python, FastAPI, SQLModel, FastMCP, YAML frontmatter

---

### Task 1: Add `create_note` to knowledge router + service

**Files:**

- Modify: `projects/monolith/knowledge/router.py`
- Test: `projects/monolith/knowledge/notes_crud_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Context:**

- The `_slugify` function lives in `knowledge/gardener.py:70` (imported by `knowledge/raw_paths.py:9`).
- Vault root is read from env `VAULT_ROOT` (default `/vault`), imported as `VAULT_ROOT_ENV` / `DEFAULT_VAULT_ROOT` from `knowledge/service.py`.
- The file should be written to vault root (not `_raw/`). The existing `move_phase` in `knowledge/raw_ingest.py` will discover and catalogue it.
- Follow the existing pattern in `knowledge/router.py` for session injection via `Depends(get_session)`.

**Step 1: Write the failing test**

Create `projects/monolith/knowledge/notes_crud_test.py`:

```python
"""Tests for knowledge notes CRUD endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from knowledge.service import VAULT_ROOT_ENV


@pytest.fixture()
def fake_session():
    return MagicMock()


@pytest.fixture()
def client(fake_session):
    app.dependency_overrides[get_session] = lambda: fake_session
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestCreateNote:
    def test_create_note_writes_file(self, tmp_path, fake_session, monkeypatch):
        monkeypatch.setenv(VAULT_ROOT_ENV, str(tmp_path))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            r = c.post(
                "/api/knowledge/notes",
                json={"content": "Hello world", "title": "My Note"},
            )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 201
        body = r.json()
        assert "path" in body
        # File should exist on disk at vault root
        written = tmp_path / body["path"]
        assert written.exists()
        text = written.read_text()
        assert "Hello world" in text
        assert "title:" in text  # frontmatter present

    def test_create_note_content_required(self, client):
        r = client.post("/api/knowledge/notes", json={"title": "No body"})
        assert r.status_code == 422

    def test_create_note_empty_content_rejected(self, client):
        r = client.post("/api/knowledge/notes", json={"content": "  "})
        assert r.status_code == 400

    def test_create_note_generates_title_from_content(self, tmp_path, fake_session, monkeypatch):
        monkeypatch.setenv(VAULT_ROOT_ENV, str(tmp_path))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            r = c.post(
                "/api/knowledge/notes",
                json={"content": "A quick thought about testing"},
            )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 201
        body = r.json()
        # When no title given, filename should be derived from content
        assert body["path"].endswith(".md")
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test --config=ci`
Expected: FAIL — endpoint not found (404) or test file not in BUILD.

**Step 3: Implement the create endpoint**

Add to `projects/monolith/knowledge/router.py`:

```python
# Add these imports at the top:
from knowledge.gardener import _slugify

# Add this Pydantic model after IngestRequest:
class NoteCreateRequest(BaseModel):
    content: str
    title: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    type: str | None = None


# Add this endpoint:
@router.post("/notes", status_code=201)
def create_note(
    data: NoteCreateRequest,
) -> dict:
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()

    # Build frontmatter
    fm: dict = {}
    title = data.title or data.content.strip()[:60]
    fm["title"] = title
    if data.source:
        fm["source"] = data.source
    if data.tags:
        fm["tags"] = data.tags
    if data.type:
        fm["type"] = data.type

    # Build markdown
    import yaml
    frontmatter_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True).strip()
    markdown = f"---\n{frontmatter_str}\n---\n\n{data.content.strip()}\n"

    # Write to vault root
    slug = _slugify(title)
    filename = f"{slug}.md"
    target = vault_root / filename

    # Avoid collisions
    counter = 1
    while target.exists():
        filename = f"{slug}-{counter}.md"
        target = vault_root / filename
        counter += 1

    target.write_text(markdown, encoding="utf-8")
    return {"path": filename}
```

**Step 4: Add BUILD target**

Add to `projects/monolith/BUILD`:

```starlark
py_test(
    name = "knowledge_notes_crud_test",
    srcs = ["knowledge/notes_crud_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)
```

**Step 5: Run test to verify it passes**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test --config=ci`
Expected: PASS

**Step 6: Commit**

```bash
git add knowledge/router.py knowledge/notes_crud_test.py
# Also BUILD if modified
git commit -m "feat(monolith): add POST /api/knowledge/notes endpoint"
```

---

### Task 2: Add `edit_note` endpoint

**Files:**

- Modify: `projects/monolith/knowledge/router.py`
- Modify: `projects/monolith/knowledge/notes_crud_test.py`

**Context:**

- `KnowledgeStore.get_note_by_id(note_id)` returns `{"note_id", "title", "path", "type", "tags"}` or `None`.
- The vault file path is resolved via `vault_root / note["path"]`.
- After editing, the file's content hash changes. The reconciler detects this on its next 5-minute cycle.
- Use `knowledge/frontmatter.py:parse()` to read existing frontmatter, merge updates, and re-serialize.

**Step 1: Write the failing tests**

Add to `projects/monolith/knowledge/notes_crud_test.py`:

```python
class TestEditNote:
    def test_edit_note_updates_content(self, tmp_path, fake_session, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "papers" / "test.md"
        note_file.parent.mkdir(parents=True)
        note_file.write_text("---\ntitle: Old Title\n---\n\nOld content\n")

        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = {
                    "note_id": "test",
                    "title": "Old Title",
                    "path": "papers/test.md",
                    "type": None,
                    "tags": [],
                }
                r = c.put(
                    "/api/knowledge/notes/test",
                    json={"content": "New content", "title": "New Title"},
                )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200
        body = r.json()
        assert body["note_id"] == "test"
        text = note_file.read_text()
        assert "New content" in text
        assert "New Title" in text

    def test_edit_note_not_found(self, client):
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.get_note_by_id.return_value = None
            r = client.put(
                "/api/knowledge/notes/nonexistent",
                json={"content": "updated"},
            )
        assert r.status_code == 404

    def test_edit_note_missing_vault_file(self, tmp_path, fake_session, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = {
                    "note_id": "test",
                    "title": "Test",
                    "path": "missing/file.md",
                    "type": None,
                    "tags": [],
                }
                r = c.put(
                    "/api/knowledge/notes/test",
                    json={"content": "updated"},
                )
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test --config=ci`
Expected: FAIL — 405 Method Not Allowed (PUT endpoint doesn't exist yet).

**Step 3: Implement the edit endpoint**

Add to `projects/monolith/knowledge/router.py`:

```python
# Add import:
from knowledge import frontmatter

# Add model:
class NoteEditRequest(BaseModel):
    content: str | None = None
    title: str | None = None
    tags: list[str] | None = None


# Add endpoint:
@router.put("/notes/{note_id}")
def edit_note(
    note_id: str,
    data: NoteEditRequest,
    session: Session = Depends(get_session),
) -> dict:
    store = KnowledgeStore(session)
    note = store.get_note_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
    resolved = (vault_root / note["path"]).resolve()
    if not resolved.is_relative_to(vault_root) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="vault file missing")

    # Parse existing file
    existing_text = resolved.read_text(encoding="utf-8")
    meta, body = frontmatter.parse(existing_text)

    # Merge updates
    if data.title is not None:
        meta.title = data.title
    if data.tags is not None:
        meta.tags = data.tags
    if data.content is not None:
        body = data.content.strip()

    # Re-serialize
    import yaml
    fm_dict: dict = {}
    if meta.note_id:
        fm_dict["id"] = meta.note_id
    if meta.title:
        fm_dict["title"] = meta.title
    if meta.type:
        fm_dict["type"] = meta.type
    if meta.status:
        fm_dict["status"] = meta.status
    if meta.source:
        fm_dict["source"] = meta.source
    if meta.tags:
        fm_dict["tags"] = meta.tags
    if meta.aliases:
        fm_dict["aliases"] = meta.aliases
    if meta.edges:
        fm_dict["edges"] = meta.edges
    if meta.extra:
        fm_dict.update(meta.extra)

    fm_str = yaml.dump(fm_dict, default_flow_style=False, allow_unicode=True).strip()
    markdown = f"---\n{fm_str}\n---\n\n{body}\n"
    resolved.write_text(markdown, encoding="utf-8")

    return {"path": note["path"], "note_id": note_id}
```

**Step 4: Run test to verify it passes**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git commit -m "feat(monolith): add PUT /api/knowledge/notes/{note_id} endpoint"
```

---

### Task 3: Add `delete_note` endpoint

**Files:**

- Modify: `projects/monolith/knowledge/router.py`
- Modify: `projects/monolith/knowledge/notes_crud_test.py`

**Context:**

- `KnowledgeStore.delete_note(path)` already exists at `knowledge/store.py:367`. It deletes the Note, Chunk, and NoteLink rows.
- The endpoint also needs to unlink the vault file from disk.

**Step 1: Write the failing tests**

Add to `projects/monolith/knowledge/notes_crud_test.py`:

```python
class TestDeleteNote:
    def test_delete_note_removes_file_and_db(self, tmp_path, fake_session, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "papers" / "test.md"
        note_file.parent.mkdir(parents=True)
        note_file.write_text("---\ntitle: Test\n---\n\nContent\n")

        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = {
                    "note_id": "test",
                    "title": "Test",
                    "path": "papers/test.md",
                    "type": None,
                    "tags": [],
                }
                r = c.delete("/api/knowledge/notes/test")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200
        body = r.json()
        assert body["deleted"] is True
        assert body["note_id"] == "test"
        assert not note_file.exists()
        MockStore.return_value.delete_note.assert_called_once_with("papers/test.md")

    def test_delete_note_not_found(self, client):
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.get_note_by_id.return_value = None
            r = client.delete("/api/knowledge/notes/nonexistent")
        assert r.status_code == 404

    def test_delete_note_missing_file_still_cleans_db(self, tmp_path, fake_session, monkeypatch):
        """If vault file is already gone, still clean up DB records."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = {
                    "note_id": "test",
                    "title": "Test",
                    "path": "missing/file.md",
                    "type": None,
                    "tags": [],
                }
                r = c.delete("/api/knowledge/notes/test")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200
        MockStore.return_value.delete_note.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test --config=ci`
Expected: FAIL — 405 Method Not Allowed.

**Step 3: Implement the delete endpoint**

Add to `projects/monolith/knowledge/router.py`:

```python
@router.delete("/notes/{note_id}")
def delete_note_endpoint(
    note_id: str,
    session: Session = Depends(get_session),
) -> dict:
    store = KnowledgeStore(session)
    note = store.get_note_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
    resolved = (vault_root / note["path"]).resolve()
    if resolved.is_relative_to(vault_root) and resolved.is_file():
        resolved.unlink()

    store.delete_note(note["path"])
    return {"deleted": True, "note_id": note_id}
```

**Step 4: Run test to verify it passes**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git commit -m "feat(monolith): add DELETE /api/knowledge/notes/{note_id} endpoint"
```

---

### Task 4: Add MCP tools for create/edit/delete

**Files:**

- Modify: `projects/monolith/knowledge/mcp.py`
- Modify: `projects/monolith/knowledge/mcp_test.py`

**Context:**

- MCP tools are registered on the shared `mcp` instance imported from `app/mcp_app.py`.
- Existing MCP tools (`search_knowledge`, `get_note`) create their own `Session(get_engine())` — no DI. Follow the same pattern.
- The MCP tools should call the same logic as the HTTP endpoints. Factor the core logic into helper functions in `knowledge/router.py` or import and call directly.

**Step 1: Write the failing tests**

Add to `projects/monolith/knowledge/mcp_test.py`:

```python
class TestCreateNoteTool:
    @pytest.mark.asyncio
    async def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        result = await create_note(content="Test note body", title="Test Note")
        assert "path" in result
        written = tmp_path / result["path"]
        assert written.exists()
        text = written.read_text()
        assert "Test note body" in text
        assert "Test Note" in text

    @pytest.mark.asyncio
    async def test_empty_content_returns_error(self):
        result = await create_note(content="  ")
        assert "error" in result


class TestEditNoteTool:
    @pytest.mark.asyncio
    async def test_updates_content(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "test.md"
        note_file.write_text("---\ntitle: Old\n---\n\nOld body\n")

        monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = {
                "note_id": "test", "title": "Old", "path": "test.md",
                "type": None, "tags": [],
            }
            result = await edit_note(note_id="test", content="New body")

        assert result["note_id"] == "test"
        assert "New body" in note_file.read_text()

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = None
            result = await edit_note(note_id="nope", content="x")
        assert "error" in result


class TestDeleteNoteTool:
    @pytest.mark.asyncio
    async def test_deletes_file_and_db(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "test.md"
        note_file.write_text("---\ntitle: Test\n---\n\nContent\n")

        monkeypatch.setenv("VAULT_ROOT", str(vault_dir))
        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = {
                "note_id": "test", "title": "Test", "path": "test.md",
                "type": None, "tags": [],
            }
            result = await delete_note(note_id="test")

        assert result["deleted"] is True
        assert not note_file.exists()
        MockStore.return_value.delete_note.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = None
            result = await delete_note(note_id="nope")
        assert "error" in result
```

Update the import at the top of `mcp_test.py`:

```python
from knowledge.mcp import create_note, delete_note, edit_note, get_note, search_knowledge
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_mcp_test --config=ci`
Expected: FAIL — ImportError (functions don't exist yet).

**Step 3: Implement the MCP tools**

Add to `projects/monolith/knowledge/mcp.py`:

```python
# Add imports:
import yaml

from knowledge import frontmatter
from knowledge.gardener import _slugify


@mcp.tool
async def create_note(
    content: str,
    title: str | None = None,
    source: str | None = None,
    tags: list[str] | None = None,
    type: str | None = None,
) -> dict:
    """Create a new knowledge note in the vault.

    Writes a markdown file with YAML frontmatter to the vault root.
    The knowledge pipeline will automatically catalogue and process it.

    Args:
        content: The markdown body of the note (required).
        title: Optional title. Defaults to first 60 chars of content.
        source: Optional source identifier (e.g. "web-ui", "mcp").
        tags: Optional list of tags.
        type: Optional note type (e.g. "atom", "fact").
    """
    if not content.strip():
        return {"error": "content is required"}

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()

    fm: dict = {}
    resolved_title = title or content.strip()[:60]
    fm["title"] = resolved_title
    if source:
        fm["source"] = source
    if tags:
        fm["tags"] = tags
    if type:
        fm["type"] = type

    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True).strip()
    markdown = f"---\n{fm_str}\n---\n\n{content.strip()}\n"

    slug = _slugify(resolved_title)
    filename = f"{slug}.md"
    target = vault_root / filename
    counter = 1
    while target.exists():
        filename = f"{slug}-{counter}.md"
        target = vault_root / filename
        counter += 1

    target.write_text(markdown, encoding="utf-8")
    return {"path": filename}


@mcp.tool
async def edit_note(
    note_id: str,
    content: str | None = None,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Edit an existing knowledge note.

    Updates the note's content and/or metadata. The reconciler will
    detect the content hash change on its next cycle.

    Args:
        note_id: The stable note identifier.
        content: New markdown body (replaces existing).
        title: New title.
        tags: New tags list (replaces existing).
    """
    with Session(get_engine()) as session:
        store = KnowledgeStore(session)
        note = store.get_note_by_id(note_id)
        if note is None:
            return {"error": f"note not found: {note_id}"}

        vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
        resolved = (vault_root / note["path"]).resolve()
        if not resolved.is_relative_to(vault_root) or not resolved.is_file():
            return {"error": f"vault file missing for {note_id}"}

        existing_text = resolved.read_text(encoding="utf-8")
        meta, body = frontmatter.parse(existing_text)

        if title is not None:
            meta.title = title
        if tags is not None:
            meta.tags = tags
        if content is not None:
            body = content.strip()

        fm_dict: dict = {}
        if meta.note_id:
            fm_dict["id"] = meta.note_id
        if meta.title:
            fm_dict["title"] = meta.title
        if meta.type:
            fm_dict["type"] = meta.type
        if meta.status:
            fm_dict["status"] = meta.status
        if meta.source:
            fm_dict["source"] = meta.source
        if meta.tags:
            fm_dict["tags"] = meta.tags
        if meta.aliases:
            fm_dict["aliases"] = meta.aliases
        if meta.edges:
            fm_dict["edges"] = meta.edges
        if meta.extra:
            fm_dict.update(meta.extra)

        fm_str = yaml.dump(fm_dict, default_flow_style=False, allow_unicode=True).strip()
        markdown = f"---\n{fm_str}\n---\n\n{body}\n"
        resolved.write_text(markdown, encoding="utf-8")

    return {"path": note["path"], "note_id": note_id}


@mcp.tool
async def delete_note(note_id: str) -> dict:
    """Delete a knowledge note from the vault.

    Removes the file from disk and cleans up database records
    (note, chunks, links).

    Args:
        note_id: The stable note identifier.
    """
    with Session(get_engine()) as session:
        store = KnowledgeStore(session)
        note = store.get_note_by_id(note_id)
        if note is None:
            return {"error": f"note not found: {note_id}"}

        vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
        resolved = (vault_root / note["path"]).resolve()
        if resolved.is_relative_to(vault_root) and resolved.is_file():
            resolved.unlink()

        store.delete_note(note["path"])

    return {"deleted": True, "note_id": note_id}
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:knowledge_mcp_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git commit -m "feat(monolith): add create/edit/delete MCP tools for knowledge notes"
```

---

### Task 5: Remove old notes proxy module

**Files:**

- Delete: `projects/monolith/notes/service.py`
- Delete: `projects/monolith/notes/router.py`
- Delete: `projects/monolith/notes/__init__.py` (if exists)
- Delete: `projects/monolith/notes/router_test.py`
- Delete: `projects/monolith/notes/service_test.py`
- Delete: `projects/monolith/notes/service_network_errors_test.py`
- Delete: `projects/monolith/notes/router_whitespace_test.py`
- Modify: `projects/monolith/app/main.py` — remove notes router import and mount
- Modify: `projects/monolith/BUILD` — remove old notes test targets, remove old notes test targets: `notes_router_test`, `notes_service_test`, `notes_service_network_errors_test`, `notes_router_whitespace_test`

**Context:**

- The old `notes/router.py` exposes `POST /api/notes` which proxies to vault-mcp. This is replaced by `POST /api/knowledge/notes`.
- The frontend homepage may still POST to `/api/notes` — if so, it needs updating. But that's a frontend change, tracked separately.

**Step 1: Remove the notes router mount from main.py**

In `projects/monolith/app/main.py`, remove:

```python
from notes.router import router as notes_router
```

and:

```python
app.include_router(notes_router)
```

**Step 2: Delete the notes module files and test files**

Delete `projects/monolith/notes/service.py`, `notes/router.py`, `notes/__init__.py`, `notes/router_test.py`, `notes/service_test.py`, `notes/service_network_errors_test.py`, `notes/router_whitespace_test.py`.

**Step 3: Remove BUILD test targets**

Remove the `notes_router_test`, `notes_service_test`, `notes_service_network_errors_test`, and `notes_router_whitespace_test` targets from `projects/monolith/BUILD`.

**Step 4: Run all knowledge + app tests**

Run: `bb remote test //projects/monolith:knowledge_notes_crud_test //projects/monolith:knowledge_mcp_test //projects/monolith:knowledge_router_test --config=ci`
Expected: PASS — no references to old notes module.

**Step 5: Commit**

```bash
git commit -m "refactor(monolith): remove vault-mcp notes proxy module"
```

---

### Task 6: Run full test suite and verify

**Files:** None (verification only)

**Step 1: Run all monolith tests**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: All PASS. Watch for any remaining imports of `notes.service` or `notes.router`.

**Step 2: Run format**

Run: `format` in the worktree root.
Expected: No formatting changes, or auto-fixed changes that need committing.

**Step 3: Commit any format fixes**

```bash
git commit -m "style(monolith): format knowledge notes CRUD"
```
