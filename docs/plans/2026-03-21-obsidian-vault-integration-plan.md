# Obsidian Vault Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy an Obsidian vault sync + git-backed audit trail + FastMCP server into the homelab cluster.

**Architecture:** Three containers in one pod sharing a PVC: obsidian-headless for sync, a git sidecar for auto-commits + push to private GitHub repo, and a FastMCP Python server for Claude access via Context Forge.

**Tech Stack:** Python (FastMCP, pydantic_settings), Node.js 22 (obsidian-headless), shell (git sidecar), Helm, ArgoCD, apko, 1Password Operator

**Design doc:** `docs/plans/2026-03-21-obsidian-vault-integration-design.md`

---

### Task 1: Scaffold project directory and MCP server boilerplate

**Files:**

- Create: `projects/obsidian_vault/__init__.py`
- Create: `projects/obsidian_vault/vault_mcp/__init__.py`
- Create: `projects/obsidian_vault/vault_mcp/app/__init__.py`
- Create: `projects/obsidian_vault/vault_mcp/app/main.py`
- Create: `projects/obsidian_vault/vault_mcp/tests/__init__.py`
- Create: `projects/obsidian_vault/vault_mcp/tests/conftest.py`

**Step 1: Create directory structure and empty `__init__.py` files**

```bash
mkdir -p projects/obsidian_vault/vault_mcp/{app,tests}
touch projects/obsidian_vault/__init__.py
touch projects/obsidian_vault/vault_mcp/__init__.py
touch projects/obsidian_vault/vault_mcp/app/__init__.py
touch projects/obsidian_vault/vault_mcp/tests/__init__.py
```

**Step 2: Create conftest.py**

```python
"""Pytest configuration for Vault MCP tests."""

import pytest_asyncio  # noqa: F401 — registers the asyncio marker


def pytest_configure(config):
    """Set asyncio_mode to auto so @pytest.mark.asyncio is not needed."""
    config.option.asyncio_mode = "auto"
```

**Step 3: Create main.py with Settings + FastMCP skeleton**

```python
"""Obsidian Vault MCP server."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import shutil
import subprocess
from pathlib import Path

from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAULT_")

    path: str = "/vault"
    port: int = 8000


mcp = FastMCP("ObsidianVault")

_settings: Settings | None = None
_lock: asyncio.Lock | None = None


def configure(settings: Settings) -> None:
    """Configure the vault path and lock."""
    global _settings, _lock
    _settings = settings
    _lock = asyncio.Lock()


def _vault_path() -> Path:
    return Path(_settings.path)


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a git command in the vault directory."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd or _vault_path(),
        capture_output=True,
        text=True,
        check=True,
    )


def _git_commit(files: list[str], message: str) -> dict:
    """Stage files and commit with the given message."""
    for f in files:
        _git("add", f)
    _git("commit", "-m", message)
    return {"status": "ok", "commit_message": message}
```

**Step 4: Commit**

```bash
git add projects/obsidian_vault/
git commit -m "feat(obsidian-vault): scaffold project and MCP server boilerplate"
```

---

### Task 2: Implement `list_notes` tool + tests

**Files:**

- Modify: `projects/obsidian_vault/vault_mcp/app/main.py`
- Create: `projects/obsidian_vault/vault_mcp/tests/main_test.py`

**Step 1: Write the failing test**

```python
"""Tests for Obsidian Vault MCP server tools."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    configure,
    list_notes,
)


@pytest.fixture(autouse=True)
def _configure_vault(tmp_path):
    """Configure vault to use a temporary directory for each test."""
    configure(Settings(path=str(tmp_path)))


class TestSettings:
    def test_default_path(self):
        s = Settings()
        assert s.path == "/vault"

    def test_default_port(self):
        s = Settings()
        assert s.port == 8000

    def test_custom_values(self):
        s = Settings(path="/my/vault", port=9090)
        assert s.path == "/my/vault"
        assert s.port == 9090

    def test_env_prefix(self):
        assert Settings.model_config["env_prefix"] == "VAULT_"

    def test_path_from_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULT_PATH", "/from-env")
        monkeypatch.delenv("VAULT_PORT", raising=False)
        s = Settings()
        assert s.path == "/from-env"


class TestListNotes:
    async def test_lists_markdown_files(self, tmp_path):
        (tmp_path / "note1.md").write_text("# Note 1")
        (tmp_path / "note2.md").write_text("# Note 2")
        (tmp_path / "not-a-note.txt").write_text("ignored")
        result = await list_notes()
        assert sorted(result["notes"]) == ["note1.md", "note2.md"]

    async def test_lists_nested_files(self, tmp_path):
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "2026-03-21.md").write_text("# Today")
        (tmp_path / "root.md").write_text("# Root")
        result = await list_notes()
        assert sorted(result["notes"]) == ["daily/2026-03-21.md", "root.md"]

    async def test_filter_by_folder(self, tmp_path):
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "today.md").write_text("# Today")
        (tmp_path / "projects").mkdir()
        (tmp_path / "projects" / "homelab.md").write_text("# Homelab")
        result = await list_notes(folder="daily")
        assert result["notes"] == ["daily/today.md"]

    async def test_filter_by_pattern(self, tmp_path):
        (tmp_path / "note-a.md").write_text("a")
        (tmp_path / "note-b.md").write_text("b")
        (tmp_path / "other.md").write_text("c")
        result = await list_notes(pattern="note-*")
        assert sorted(result["notes"]) == ["note-a.md", "note-b.md"]

    async def test_empty_vault(self, tmp_path):
        result = await list_notes()
        assert result["notes"] == []

    async def test_ignores_dotfiles_and_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config.md").write_text("git stuff")
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / ".obsidian" / "config.md").write_text("obsidian config")
        (tmp_path / "real.md").write_text("# Real note")
        result = await list_notes()
        assert result["notes"] == ["real.md"]
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: FAIL — `list_notes` not defined

**Step 3: Implement `list_notes` in main.py**

Add to `main.py`:

```python
@mcp.tool
async def list_notes(
    folder: str | None = None,
    pattern: str | None = None,
) -> dict:
    """List markdown files in the vault.

    Args:
        folder: Optional subfolder to list (e.g. "daily", "projects").
        pattern: Optional glob pattern to filter filenames (e.g. "note-*").

    Returns a list of relative paths to all matching .md files.
    """
    vault = _vault_path()
    base = vault / folder if folder else vault
    if not base.exists():
        return {"notes": []}

    notes = []
    for md in base.rglob("*.md"):
        rel = md.relative_to(vault)
        # Skip dotfiles/directories (.git, .obsidian, _archive)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if pattern and not fnmatch.fnmatch(rel.name, pattern):
            continue
        notes.append(str(rel))

    return {"notes": sorted(notes)}
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/obsidian_vault/vault_mcp/
git commit -m "feat(obsidian-vault): add list_notes MCP tool"
```

---

### Task 3: Implement `read_note` and `search_notes` tools + tests

**Files:**

- Modify: `projects/obsidian_vault/vault_mcp/app/main.py`
- Modify: `projects/obsidian_vault/vault_mcp/tests/main_test.py`

**Step 1: Write failing tests**

Add to `main_test.py`:

```python
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    configure,
    list_notes,
    read_note,
    search_notes,
)


class TestReadNote:
    async def test_reads_content(self, tmp_path):
        (tmp_path / "hello.md").write_text("# Hello\n\nWorld")
        result = await read_note(path="hello.md")
        assert result["content"] == "# Hello\n\nWorld"
        assert result["path"] == "hello.md"

    async def test_reads_nested_note(self, tmp_path):
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "today.md").write_text("# Today")
        result = await read_note(path="daily/today.md")
        assert result["content"] == "# Today"

    async def test_not_found(self, tmp_path):
        result = await read_note(path="missing.md")
        assert "error" in result

    async def test_rejects_path_traversal(self, tmp_path):
        result = await read_note(path="../../../etc/passwd")
        assert "error" in result

    async def test_rejects_absolute_path(self, tmp_path):
        result = await read_note(path="/etc/passwd")
        assert "error" in result


class TestSearchNotes:
    async def test_finds_matching_content(self, tmp_path):
        (tmp_path / "a.md").write_text("# Homelab\n\nKubernetes cluster")
        (tmp_path / "b.md").write_text("# Recipes\n\nChocolate cake")
        result = await search_notes(query="kubernetes")
        assert len(result["matches"]) == 1
        assert result["matches"][0]["path"] == "a.md"

    async def test_case_insensitive(self, tmp_path):
        (tmp_path / "a.md").write_text("KUBERNETES is great")
        result = await search_notes(query="kubernetes")
        assert len(result["matches"]) == 1

    async def test_no_matches(self, tmp_path):
        (tmp_path / "a.md").write_text("# Nothing relevant")
        result = await search_notes(query="zyxwvu")
        assert result["matches"] == []

    async def test_returns_matching_lines(self, tmp_path):
        (tmp_path / "a.md").write_text("line1\nfound here\nline3")
        result = await search_notes(query="found")
        assert "found here" in result["matches"][0]["lines"][0]

    async def test_ignores_dotfiles(self, tmp_path):
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / ".obsidian" / "config.md").write_text("query match")
        (tmp_path / "real.md").write_text("query match")
        result = await search_notes(query="query match")
        assert len(result["matches"]) == 1
        assert result["matches"][0]["path"] == "real.md"
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: FAIL

**Step 3: Implement `read_note` and `search_notes`**

Add to `main.py`:

```python
def _validate_path(path: str) -> Path | None:
    """Validate a note path is safe (no traversal, within vault)."""
    if os.path.isabs(path):
        return None
    resolved = (_vault_path() / path).resolve()
    if not resolved.is_relative_to(_vault_path().resolve()):
        return None
    return resolved


@mcp.tool
async def read_note(path: str) -> dict:
    """Read the full content of a note.

    Args:
        path: Relative path to the note (e.g. "daily/2026-03-21.md").

    Returns the note content and path, or an error if not found.
    """
    resolved = _validate_path(path)
    if resolved is None:
        return {"error": f"Invalid path: {path}"}
    if not resolved.exists():
        return {"error": f"Note not found: {path}"}
    return {"path": path, "content": resolved.read_text()}


@mcp.tool
async def search_notes(query: str) -> dict:
    """Full-text search across all vault notes.

    Args:
        query: Text to search for (case-insensitive).

    Returns matching files with the lines containing the query.
    """
    vault = _vault_path()
    matches = []
    query_lower = query.lower()

    for md in vault.rglob("*.md"):
        rel = md.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts):
            continue
        content = md.read_text()
        matching_lines = [
            line.strip()
            for line in content.splitlines()
            if query_lower in line.lower()
        ]
        if matching_lines:
            matches.append({"path": str(rel), "lines": matching_lines})

    return {"matches": matches}
```

**Step 4: Run tests to verify they pass**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/obsidian_vault/vault_mcp/
git commit -m "feat(obsidian-vault): add read_note and search_notes MCP tools"
```

---

### Task 4: Implement `write_note` and `edit_note` tools + tests (git-backed)

**Files:**

- Modify: `projects/obsidian_vault/vault_mcp/app/main.py`
- Modify: `projects/obsidian_vault/vault_mcp/tests/main_test.py`

**Step 1: Write failing tests**

Add to `main_test.py`:

```python
from unittest.mock import patch, MagicMock
from projects.obsidian_vault.vault_mcp.app.main import (
    # ... existing imports ...
    write_note,
    edit_note,
)


@pytest.fixture(autouse=True)
def _init_git(tmp_path):
    """Initialize a git repo in the tmp vault so commits work."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True,
    )


class TestWriteNote:
    async def test_creates_new_note(self, tmp_path):
        result = await write_note(
            path="new.md", content="# New Note", reason="created for testing"
        )
        assert result["status"] == "ok"
        assert (tmp_path / "new.md").read_text() == "# New Note"

    async def test_creates_parent_dirs(self, tmp_path):
        result = await write_note(
            path="daily/2026-03-21.md", content="# Today", reason="daily note"
        )
        assert result["status"] == "ok"
        assert (tmp_path / "daily" / "2026-03-21.md").exists()

    async def test_overwrites_existing(self, tmp_path):
        (tmp_path / "existing.md").write_text("old content")
        # Need initial commit for the file
        subprocess.run(["git", "add", "existing.md"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)
        result = await write_note(
            path="existing.md", content="new content", reason="updated"
        )
        assert result["status"] == "ok"
        assert (tmp_path / "existing.md").read_text() == "new content"

    async def test_commits_with_reason(self, tmp_path):
        await write_note(path="a.md", content="# A", reason="test reason")
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert "mcp(write_note)" in log.stdout
        assert "test reason" in log.stdout

    async def test_rejects_path_traversal(self, tmp_path):
        result = await write_note(
            path="../escape.md", content="bad", reason="nope"
        )
        assert "error" in result

    async def test_reason_required(self, tmp_path):
        """Reason is a required parameter — empty string is rejected."""
        result = await write_note(path="a.md", content="# A", reason="")
        assert "error" in result


class TestEditNote:
    async def test_replaces_section(self, tmp_path):
        (tmp_path / "note.md").write_text("# Title\n\nOld paragraph\n\n## End")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        result = await edit_note(
            path="note.md",
            old_text="Old paragraph",
            new_text="New paragraph",
            reason="updated paragraph",
        )
        assert result["status"] == "ok"
        assert "New paragraph" in (tmp_path / "note.md").read_text()
        assert "Old paragraph" not in (tmp_path / "note.md").read_text()

    async def test_old_text_not_found(self, tmp_path):
        (tmp_path / "note.md").write_text("# Title\n\nContent")
        result = await edit_note(
            path="note.md",
            old_text="nonexistent text",
            new_text="replacement",
            reason="fix",
        )
        assert "error" in result

    async def test_note_not_found(self, tmp_path):
        result = await edit_note(
            path="missing.md",
            old_text="a",
            new_text="b",
            reason="fix",
        )
        assert "error" in result

    async def test_commits_with_reason(self, tmp_path):
        (tmp_path / "note.md").write_text("# Old")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        await edit_note(
            path="note.md", old_text="# Old", new_text="# New", reason="rename"
        )
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert "mcp(edit_note)" in log.stdout
        assert "rename" in log.stdout
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: FAIL

**Step 3: Implement `write_note` and `edit_note`**

Add to `main.py`:

```python
@mcp.tool
async def write_note(path: str, content: str, reason: str) -> dict:
    """Create or overwrite a note. Commits the change to git.

    Args:
        path: Relative path for the note (e.g. "daily/2026-03-21.md").
        content: Full markdown content to write.
        reason: Why this change is being made (used in commit message).

    Returns status and commit message, or an error.
    """
    if not reason:
        return {"error": "reason is required"}
    resolved = _validate_path(path)
    if resolved is None:
        return {"error": f"Invalid path: {path}"}

    async with _lock:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return _git_commit([path], f"mcp(write_note): {path} — {reason}")


@mcp.tool
async def edit_note(path: str, old_text: str, new_text: str, reason: str) -> dict:
    """Replace a section of an existing note. Commits the change to git.

    Args:
        path: Relative path to the note.
        old_text: Exact text to find and replace.
        new_text: Replacement text.
        reason: Why this change is being made (used in commit message).

    Returns status and commit message, or an error.
    """
    if not reason:
        return {"error": "reason is required"}
    resolved = _validate_path(path)
    if resolved is None:
        return {"error": f"Invalid path: {path}"}
    if not resolved.exists():
        return {"error": f"Note not found: {path}"}

    content = resolved.read_text()
    if old_text not in content:
        return {"error": f"Text not found in {path}"}

    async with _lock:
        resolved.write_text(content.replace(old_text, new_text, 1))
        return _git_commit([path], f"mcp(edit_note): {path} — {reason}")
```

**Step 4: Run tests to verify they pass**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/obsidian_vault/vault_mcp/
git commit -m "feat(obsidian-vault): add write_note and edit_note MCP tools with git commits"
```

---

### Task 5: Implement `delete_note`, `get_history`, `restore_note` tools + tests

**Files:**

- Modify: `projects/obsidian_vault/vault_mcp/app/main.py`
- Modify: `projects/obsidian_vault/vault_mcp/tests/main_test.py`

**Step 1: Write failing tests**

Add to `main_test.py`:

```python
from projects.obsidian_vault.vault_mcp.app.main import (
    # ... existing imports ...
    delete_note,
    get_history,
    restore_note,
)


class TestDeleteNote:
    async def test_moves_to_archive(self, tmp_path):
        (tmp_path / "doomed.md").write_text("# Doomed")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        result = await delete_note(path="doomed.md", reason="no longer needed")
        assert result["status"] == "ok"
        assert not (tmp_path / "doomed.md").exists()
        assert (tmp_path / "_archive" / "doomed.md").exists()
        assert (tmp_path / "_archive" / "doomed.md").read_text() == "# Doomed"

    async def test_preserves_nested_path_in_archive(self, tmp_path):
        (tmp_path / "projects").mkdir()
        (tmp_path / "projects" / "old.md").write_text("# Old")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        await delete_note(path="projects/old.md", reason="archived")
        assert (tmp_path / "_archive" / "projects" / "old.md").exists()

    async def test_not_found(self, tmp_path):
        result = await delete_note(path="missing.md", reason="cleanup")
        assert "error" in result

    async def test_commits_with_reason(self, tmp_path):
        (tmp_path / "note.md").write_text("# Note")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        await delete_note(path="note.md", reason="test delete")
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert "mcp(delete_note)" in log.stdout
        assert "test delete" in log.stdout


class TestGetHistory:
    async def test_returns_commits_for_file(self, tmp_path):
        (tmp_path / "note.md").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, capture_output=True)
        (tmp_path / "note.md").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=tmp_path, capture_output=True)
        result = await get_history(path="note.md")
        assert len(result["commits"]) == 2
        assert "second" in result["commits"][0]["message"]

    async def test_returns_all_commits_when_no_path(self, tmp_path):
        (tmp_path / "a.md").write_text("a")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add a"], cwd=tmp_path, capture_output=True)
        (tmp_path / "b.md").write_text("b")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True)
        result = await get_history()
        assert len(result["commits"]) == 2

    async def test_limit_parameter(self, tmp_path):
        for i in range(5):
            (tmp_path / f"note{i}.md").write_text(f"v{i}")
            subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"commit {i}"], cwd=tmp_path, capture_output=True)
        result = await get_history(limit=3)
        assert len(result["commits"]) == 3


class TestRestoreNote:
    async def test_restores_from_commit(self, tmp_path):
        (tmp_path / "note.md").write_text("original")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=tmp_path, capture_output=True)
        v1_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path, capture_output=True, text=True,
        ).stdout.strip()
        (tmp_path / "note.md").write_text("modified")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=tmp_path, capture_output=True)
        result = await restore_note(path="note.md", commit=v1_hash)
        assert result["status"] == "ok"
        assert (tmp_path / "note.md").read_text() == "original"

    async def test_invalid_commit(self, tmp_path):
        (tmp_path / "note.md").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        result = await restore_note(path="note.md", commit="0000000000")
        assert "error" in result
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: FAIL

**Step 3: Implement `delete_note`, `get_history`, `restore_note`**

Add to `main.py`:

```python
@mcp.tool
async def delete_note(path: str, reason: str) -> dict:
    """Soft-delete a note by moving it to _archive/. Commits the change to git.

    Args:
        path: Relative path to the note to delete.
        reason: Why this note is being deleted (used in commit message).

    The note is moved to _archive/<original-path>, not permanently removed.
    """
    if not reason:
        return {"error": "reason is required"}
    resolved = _validate_path(path)
    if resolved is None:
        return {"error": f"Invalid path: {path}"}
    if not resolved.exists():
        return {"error": f"Note not found: {path}"}

    archive_path = _vault_path() / "_archive" / path
    archive_rel = str(Path("_archive") / path)

    async with _lock:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved), str(archive_path))
        _git("add", path)
        _git("add", archive_rel)
        _git("commit", "-m", f"mcp(delete_note): {path} — {reason}")
        return {"status": "ok", "archived_to": archive_rel}


@mcp.tool
async def get_history(
    path: str | None = None,
    limit: int = 20,
) -> dict:
    """Get git commit history for a file or the whole vault.

    Args:
        path: Optional file path to get history for. If omitted, returns all commits.
        limit: Maximum number of commits to return (default 20).

    Returns a list of commits with hash, message, author, and date.
    """
    args = ["log", f"--max-count={limit}", "--format=%H|%s|%an|%ai"]
    if path:
        args.append("--")
        args.append(path)

    try:
        result = _git(*args)
    except subprocess.CalledProcessError:
        return {"commits": []}

    commits = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|", 3)
        commits.append({
            "hash": parts[0],
            "message": parts[1],
            "author": parts[2],
            "date": parts[3],
        })
    return {"commits": commits}


@mcp.tool
async def restore_note(path: str, commit: str) -> dict:
    """Restore a note from a specific git commit.

    Args:
        path: Relative path to the note.
        commit: Git commit hash to restore from.

    Checks out the file from the given commit and creates a new commit.
    """
    resolved = _validate_path(path)
    if resolved is None:
        return {"error": f"Invalid path: {path}"}

    async with _lock:
        try:
            _git("checkout", commit, "--", path)
        except subprocess.CalledProcessError:
            return {"error": f"Could not restore {path} from commit {commit}"}
        return _git_commit(
            [path],
            f"mcp(restore_note): {path} — restored from {commit[:8]}",
        )
```

**Step 4: Run tests to verify they pass**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/obsidian_vault/vault_mcp/
git commit -m "feat(obsidian-vault): add delete_note, get_history, restore_note MCP tools"
```

---

### Task 6: Add `main()` entry point and BUILD files

**Files:**

- Modify: `projects/obsidian_vault/vault_mcp/app/main.py`
- Create: `projects/obsidian_vault/vault_mcp/app/BUILD` (generated by `format`)
- Create: `projects/obsidian_vault/vault_mcp/tests/BUILD` (generated by `format`)
- Create: `projects/obsidian_vault/BUILD` (generated by `format`)
- Create: `projects/obsidian_vault/vault_mcp/BUILD` (generated by `format`)

**Step 1: Add `main()` to main.py**

The entry point should already exist from the scaffold but verify it's at the bottom:

```python
def main():
    settings = Settings()
    configure(settings)
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
```

**Step 2: Run `format` to generate BUILD files**

```bash
format
```

This auto-generates BUILD files via gazelle. Review the generated files to ensure deps are correct. The `app/BUILD` should include `@pip//fastmcp`, `@pip//pydantic_settings`. The `tests/BUILD` should include a `py_test` target with deps on the app library.

**Step 3: Add gazelle resolve hints if needed**

If gazelle can't resolve the import `projects.obsidian_vault.vault_mcp.app.main`, add a comment to `tests/BUILD`:

```
# gazelle:resolve py projects.obsidian_vault.vault_mcp.app.main //projects/obsidian_vault/vault_mcp/app:app
```

**Step 4: Run tests via Bazel**

```bash
bazel test //projects/obsidian_vault/...
```

Expected: PASS

**Step 5: Commit**

```bash
git add projects/obsidian_vault/
git commit -m "build(obsidian-vault): add BUILD files for vault MCP server"
```

---

### Task 7: Build container image (apko)

**Files:**

- Create: `projects/obsidian_vault/image/apko.yaml`
- Create: `projects/obsidian_vault/image/BUILD`

**Step 1: Check an existing apko image for reference**

Read: `projects/todo_app/image/apko.yaml` and `projects/todo_app/image/BUILD` for the pattern.

**Step 2: Create apko.yaml**

```yaml
contents:
  packages:
    - python-3.12
    - python-3.12-dev
    - py3.12-pip
    - busybox
    - git

accounts:
  groups:
    - groupname: nonroot
      gid: 65532
  users:
    - username: nonroot
      uid: 65532
      gid: 65532
  run-as: 65532

archs:
  - x86_64
  - aarch64
```

Note: `git` is required in the image because the MCP server runs git commands for commits.

**Step 3: Create BUILD file**

Follow the pattern from the todo_app image BUILD. This will need `apko_image` and `oci_push` rules.

**Step 4: Run `format` to ensure BUILD is valid**

```bash
format
```

**Step 5: Commit**

```bash
git add projects/obsidian_vault/image/
git commit -m "build(obsidian-vault): add apko container image definition"
```

---

### Task 8: Create Helm chart

**Files:**

- Create: `projects/obsidian_vault/chart/Chart.yaml`
- Create: `projects/obsidian_vault/chart/values.yaml`
- Create: `projects/obsidian_vault/chart/templates/_helpers.tpl`
- Create: `projects/obsidian_vault/chart/templates/deployment.yaml`
- Create: `projects/obsidian_vault/chart/templates/service.yaml`
- Create: `projects/obsidian_vault/chart/templates/pvc.yaml`
- Create: `projects/obsidian_vault/chart/templates/onepassworditem.yaml`
- Create: `projects/obsidian_vault/chart/templates/serviceaccount.yaml`

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: obsidian-vault
description: Obsidian vault sync with git audit trail and MCP server
type: application
version: 0.1.0
appVersion: "0.1.0"
```

**Step 2: Create values.yaml**

```yaml
headlessSync:
  image:
    repository: node
    tag: "22-alpine"

gitSidecar:
  image:
    repository: alpine/git
    tag: "latest"
  remote: "" # e.g. git@github.com:jomcgi/obsidian-vault.git
  branch: "main"
  debounceSeconds: 10

vaultMcp:
  image:
    repository: ghcr.io/jomcgi/homelab/obsidian-vault-mcp
    tag: "latest"
  port: 8000

persistence:
  size: 5Gi
  storageClass: ""

secrets:
  obsidian:
    name: obsidian-credentials
    itemPath: ""
  github:
    name: github-deploy-key
    itemPath: ""
```

**Step 3: Create deployment.yaml with 3 containers**

The deployment template should define a single pod with:

- `headless-sync` container: runs `ob sync --continuous`, mounts vault PVC at `/vault`
- `git-sidecar` container: runs the git watch/commit/push script, mounts vault PVC at `/vault`, mounts github SSH key
- `vault-mcp` container: runs the FastMCP server, mounts vault PVC at `/vault`

All three share the vault PVC. The `vault-mcp` container exposes port 8000.

Security context: `runAsNonRoot: true`, `runAsUser: 65532`, `seccompProfile: RuntimeDefault`.

**Step 4: Create service.yaml**

Simple ClusterIP service exposing port 8000 pointing to the `vault-mcp` container.

**Step 5: Create pvc.yaml**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ include "obsidian-vault.fullname" . }}-data
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: {{ .Values.persistence.size }}
  {{- if .Values.persistence.storageClass }}
  storageClassName: {{ .Values.persistence.storageClass }}
  {{- end }}
```

**Step 6: Create onepassworditem.yaml for secrets**

Two `OnePasswordItem` CRDs: one for Obsidian credentials, one for GitHub deploy key.

**Step 7: Verify with helm template**

```bash
helm template obsidian-vault projects/obsidian_vault/chart/ -f projects/obsidian_vault/deploy/values.yaml
```

**Step 8: Commit**

```bash
git add projects/obsidian_vault/chart/
git commit -m "feat(obsidian-vault): add Helm chart with 3-container pod"
```

---

### Task 9: Create git sidecar script

**Files:**

- Create: `projects/obsidian_vault/scripts/git-sidecar.sh`

**Step 1: Write the sidecar script**

```bash
#!/bin/sh
set -e

VAULT_PATH="${VAULT_PATH:-/vault}"
REMOTE="${GIT_REMOTE}"
BRANCH="${GIT_BRANCH:-main}"
DEBOUNCE="${DEBOUNCE_SECONDS:-10}"
LOCKFILE="$VAULT_PATH/.git/mcp.lock"

cd "$VAULT_PATH"

# Initialize git repo if needed
if [ ! -d .git ]; then
    git init
    git config user.email "vault-sidecar@homelab.local"
    git config user.name "vault-sidecar"
    if [ -n "$REMOTE" ]; then
        git remote add origin "$REMOTE"
        # Pull existing history if any
        git fetch origin "$BRANCH" 2>/dev/null && \
            git checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null || \
            git checkout -b "$BRANCH"
    fi
    # Initial commit of any existing files
    git add -A
    git diff --cached --quiet || git commit -m "sync: initial vault state"
fi

echo "Git sidecar started. Watching $VAULT_PATH for changes..."

while true; do
    sleep "$DEBOUNCE"

    # Skip if MCP server is mid-operation
    if [ -f "$LOCKFILE" ]; then
        continue
    fi

    # Check for uncommitted changes
    if ! git diff --quiet || ! git diff --cached --quiet || \
       [ -n "$(git ls-files --others --exclude-standard)" ]; then
        git add -A
        git commit -m "sync: external changes"

        if [ -n "$REMOTE" ]; then
            git push origin "$BRANCH" 2>/dev/null || \
                (git pull --rebase origin "$BRANCH" && git push origin "$BRANCH")
        fi
    fi
done
```

**Step 2: Commit**

```bash
chmod +x projects/obsidian_vault/scripts/git-sidecar.sh
git add projects/obsidian_vault/scripts/
git commit -m "feat(obsidian-vault): add git sidecar script for auto-commit and push"
```

---

### Task 10: Create ArgoCD deploy configuration

**Files:**

- Create: `projects/obsidian_vault/deploy/application.yaml`
- Create: `projects/obsidian_vault/deploy/kustomization.yaml`
- Create: `projects/obsidian_vault/deploy/values.yaml`

**Step 1: Create application.yaml**

Follow the pattern from existing services. Point to the chart at `projects/obsidian_vault/chart/`, set `targetRevision: 0.1.0`.

**Step 2: Create kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 3: Create values.yaml with cluster-specific overrides**

Fill in 1Password item paths, git remote URL, Context Forge gateway URL, etc.

**Step 4: Run `format` to update home-cluster kustomization**

```bash
format
```

This regenerates `projects/home-cluster/kustomization.yaml` to include the new service.

**Step 5: Verify with helm template**

```bash
helm template obsidian-vault projects/obsidian_vault/chart/ -f projects/obsidian_vault/deploy/values.yaml
```

**Step 6: Commit**

```bash
git add projects/obsidian_vault/deploy/ projects/home-cluster/
git commit -m "feat(obsidian-vault): add ArgoCD deploy configuration"
```

---

### Task 11: Set up 1Password secrets and private GitHub repo

**This task requires manual steps outside the codebase.**

**Step 1: Create private GitHub repo**

```bash
gh repo create jomcgi/obsidian-vault --private
```

**Step 2: Create a deploy key**

```bash
ssh-keygen -t ed25519 -f /tmp/obsidian-vault-deploy-key -N "" -C "obsidian-vault-sidecar"
```

Add the public key to the repo as a deploy key with write access:

```bash
gh repo deploy-key add /tmp/obsidian-vault-deploy-key.pub -R jomcgi/obsidian-vault -w
```

**Step 3: Store secrets in 1Password**

- Obsidian account token (from `ob login` output)
- GitHub deploy key private key

**Step 4: Update `values.yaml` with 1Password item paths**

**Step 5: Commit any values.yaml changes**

```bash
git add projects/obsidian_vault/deploy/values.yaml
git commit -m "chore(obsidian-vault): configure 1Password secret paths"
```

---

### Task 12: Register MCP server with Context Forge

**Files:**

- Modify: `projects/obsidian_vault/chart/templates/` (add registration-job.yaml)
- Or: Add vault-mcp to the existing `mcp_servers` deploy values as an additional server entry

**Step 1: Decide on registration approach**

Check how the existing MCP servers register with Context Forge — either via a registration Job in the chart or via the mcp_servers chart values. Follow the established pattern.

**Step 2: Add registration job or values entry**

**Step 3: Verify registration works after deploy**

Use ArgoCD MCP tools to check the application status after deployment.

**Step 4: Commit**

```bash
git add projects/obsidian_vault/
git commit -m "feat(obsidian-vault): add Context Forge registration"
```

---

### Task 13: End-to-end verification

**Step 1: Push branch and create PR**

```bash
git push -u origin design/obsidian-vault
gh pr create --title "feat: obsidian vault integration" --body "..."
```

**Step 2: Wait for CI to pass**

Monitor with: `gh pr view --json state,mergeStateStatus`

**Step 3: After merge, verify ArgoCD sync**

Use ArgoCD MCP tools:

- `argocd-mcp-get-application` — check sync status
- `kubernetes-mcp-pods-list` — verify all 3 containers running

**Step 4: Test MCP tools via Context Forge**

- `list_notes` — should return files from the vault
- `write_note` — create a test note, verify it appears in Obsidian on a device
- `get_history` — verify the commit appears
- `search_notes` — search for the test note content
