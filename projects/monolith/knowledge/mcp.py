"""MCP tools for knowledge graph search and note retrieval.

Registers ``search_knowledge``, ``get_note``, ``create_note``,
``edit_note``, and ``delete_note`` on the shared monolith MCP instance.
Tools call KnowledgeStore directly (no HTTP round-trip).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from sqlmodel import Session

from app.db import get_engine
from app.mcp_app import mcp
from knowledge import frontmatter
from knowledge.gardener import _slugify
from knowledge.service import DEFAULT_VAULT_ROOT, VAULT_ROOT_ENV
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)


@mcp.tool
async def search_knowledge(
    query: str,
    limit: int = 20,
    type: str | None = None,
) -> dict:
    """Semantic search over the knowledge graph.

    Embeds the query and searches notes by cosine similarity.
    Returns ranked results with title, type, tags, best-matching
    section, a 240-char snippet, and graph edges.

    Args:
        query: Natural language search query (minimum 2 characters).
        limit: Maximum results to return (default 20, max 100).
        type: Optional note type filter (e.g. "concept", "paper").
    """
    if len(query) < 2:
        return {"results": []}

    embed_client = EmbeddingClient()
    try:
        vector = await embed_client.embed(query)
    except Exception:
        logger.exception("knowledge mcp: embedding call failed")
        return {"error": "embedding unavailable"}

    with Session(get_engine()) as session:
        results = KnowledgeStore(session).search_notes_with_context(
            query_embedding=vector,
            limit=min(limit, 100),
            type_filter=type,
        )
    return {"results": results}


@mcp.tool
async def get_note(note_id: str) -> dict:
    """Retrieve a knowledge note by its stable ID.

    Returns note metadata (title, type, tags), the full markdown
    content read from the vault, and all outgoing graph edges.

    Args:
        note_id: The stable note identifier (e.g. "attention-is-all-you-need").
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

        edges = store.get_note_links(note_id)
        return {**note, "content": resolved.read_text(), "edges": edges}


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
    The file is named from a slugified title with collision handling.

    Args:
        content: The markdown body of the note (required, must not be empty).
        title: Note title (defaults to first 60 characters of content).
        source: Optional source URL or reference.
        tags: Optional list of tags.
        type: Optional note type (e.g. "concept", "paper").
    """
    if not content or not content.strip():
        return {"error": "content must not be empty"}

    if title is None:
        title = content.strip()[:60]

    fm: dict[str, object] = {"title": title}
    if source:
        fm["source"] = source
    if tags:
        fm["tags"] = tags
    if type:
        fm["type"] = type

    file_content = "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n" + content

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
    slug = _slugify(title)
    candidate = vault_root / f"{slug}.md"
    counter = 1
    while candidate.exists():
        candidate = vault_root / f"{slug}-{counter}.md"
        counter += 1

    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(file_content)
    return {"path": candidate.name}


@mcp.tool
async def edit_note(
    note_id: str,
    content: str | None = None,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Edit an existing knowledge note.

    Looks up the note by ID, merges the provided fields into the
    existing frontmatter, and writes the updated file back.

    Args:
        note_id: The stable note identifier.
        content: New markdown body (replaces existing body if provided).
        title: New title (updates frontmatter if provided).
        tags: New tags list (updates frontmatter if provided).
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

        raw = resolved.read_text()
        parsed, body = frontmatter.parse(raw)

        if title is not None:
            parsed.title = title
        if tags is not None:
            parsed.tags = tags
        if content is not None:
            body = content

        fm_dict: dict[str, object] = {}
        if parsed.note_id:
            fm_dict["id"] = parsed.note_id
        if parsed.title:
            fm_dict["title"] = parsed.title
        if parsed.type:
            fm_dict["type"] = parsed.type
        if parsed.status:
            fm_dict["status"] = parsed.status
        if parsed.source:
            fm_dict["source"] = parsed.source
        if parsed.tags:
            fm_dict["tags"] = parsed.tags
        if parsed.aliases:
            fm_dict["aliases"] = parsed.aliases
        if parsed.edges:
            fm_dict["edges"] = parsed.edges
        if parsed.extra:
            fm_dict.update(parsed.extra)

        file_content = (
            "---\n" + yaml.dump(fm_dict, default_flow_style=False) + "---\n" + body
        )
        resolved.write_text(file_content)
        return {"path": note["path"], "note_id": note_id}


@mcp.tool
async def delete_note(note_id: str) -> dict:
    """Delete a knowledge note from the vault and database.

    Removes both the markdown file from disk and the database record.

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
