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


def _validate_path(path: str) -> Path | None:
    """Validate a note path is safe (no traversal, within vault)."""
    if os.path.isabs(path):
        return None
    resolved = (_vault_path() / path).resolve()
    if not resolved.is_relative_to(_vault_path().resolve()):
        return None
    return resolved


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
        # Skip dotfiles/directories (.git, .obsidian, etc.)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if pattern and not fnmatch.fnmatch(rel.name, pattern):
            continue
        notes.append(str(rel))

    return {"notes": sorted(notes)}


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
            line.strip() for line in content.splitlines() if query_lower in line.lower()
        ]
        if matching_lines:
            matches.append({"path": str(rel), "lines": matching_lines})

    return {"matches": matches}


def _git_commit(files: list[str], message: str) -> dict:
    """Stage files and commit with the given message."""
    for f in files:
        _git("add", f)
    _git("commit", "-m", message)
    return {"status": "ok", "commit_message": message}


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
        commits.append(
            {
                "hash": parts[0],
                "message": parts[1],
                "author": parts[2],
                "date": parts[3],
            }
        )
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
