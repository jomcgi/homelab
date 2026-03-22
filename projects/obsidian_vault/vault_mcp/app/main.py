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
