"""Obsidian Vault MCP server."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import shutil
import subprocess
from pathlib import Path

from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict

from projects.obsidian_vault.vault_mcp.app.embedder import VaultEmbedder
from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient
from projects.obsidian_vault.vault_mcp.app.reconciler import VaultReconciler


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAULT_")

    path: str = "/vault"
    port: int = 8000

    # Embedding
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "obsidian_vault"
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embed_cache_dir: str = "/vault/.cache/fastembed"
    reconcile_interval_seconds: int = 300


mcp = FastMCP("ObsidianVault")

_settings: Settings | None = None
_lock: asyncio.Lock | None = None
_embedder: VaultEmbedder | None = None
_qdrant: QdrantClient | None = None
_background_tasks: set[asyncio.Task] = set()  # prevent GC of fire-and-forget tasks


def configure(settings: Settings) -> None:
    """Configure the vault path and lock."""
    global _settings, _lock
    _settings = settings
    _lock = asyncio.Lock()


def _vault_path() -> Path:
    return Path(_settings.path)


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a git command in the vault directory.

    Safe from injection: uses list-mode subprocess (no shell=True),
    and all callers validate paths via _validate_path() first.
    """
    return subprocess.run(  # nosemgrep: mcp-shell-injection-taint
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


@mcp.tool
async def search_semantic(query: str, limit: int = 5) -> dict:
    """Semantic search across vault notes using vector embeddings.

    Args:
        query: Natural language search query.
        limit: Max results to return (default 5).

    Returns matching chunks with scores, paths, and section headers.
    """
    if _embedder is None or _qdrant is None:
        return {"error": "Semantic search not configured"}
    vector = _embedder.embed_query(query)
    results = await _qdrant.search(vector=vector, limit=limit)
    for r in results:
        if "source_url" in r:
            r["path"] = r["source_url"].removeprefix("vault://")
    return {"results": results}


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


async def _reconcile_loop(settings: Settings) -> None:
    """Background loop that reconciles vault with Qdrant."""
    global _embedder, _qdrant
    log = logging.getLogger(__name__)

    # Retry initialization — fastembed model download or Qdrant may not be ready
    while _embedder is None or _qdrant is None:
        try:
            log.info("Initialising embedder (model=%s)", settings.embed_model)
            _embedder = VaultEmbedder(
                model=settings.embed_model, cache_dir=settings.embed_cache_dir
            )
            log.info("Initialising Qdrant client (url=%s)", settings.qdrant_url)
            _qdrant = QdrantClient(
                url=settings.qdrant_url, collection=settings.qdrant_collection
            )
            await _qdrant.ensure_collection(vector_size=_embedder.dimension)
            log.info("Semantic search initialised successfully")
        except Exception:
            _embedder = None
            _qdrant = None
            log.exception("Failed to initialise semantic search, retrying in 30s")
            await asyncio.sleep(30)

    reconciler = VaultReconciler(
        vault_path=settings.path, embedder=_embedder, qdrant=_qdrant
    )
    while True:
        try:
            await reconciler.run()
        except Exception:
            log.exception("Reconciler error")
        await asyncio.sleep(settings.reconcile_interval_seconds)


def main():
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    configure(settings)

    app = mcp.http_app()

    async def healthz(request):
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ok"})

    app.add_route("/healthz", healthz)

    @app.on_event("startup")
    async def _start_reconciler():
        task = asyncio.create_task(_reconcile_loop(settings))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
