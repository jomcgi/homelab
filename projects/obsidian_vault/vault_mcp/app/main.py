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


def _git_commit(files: list[str], message: str) -> dict:
    """Stage files and commit with the given message."""
    for f in files:
        _git("add", f)
    _git("commit", "-m", message)
    return {"status": "ok", "commit_message": message}
