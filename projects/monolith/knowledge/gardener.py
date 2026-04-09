"""Knowledge gardener — decomposes raw vault notes into typed knowledge artifacts."""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import yaml

from knowledge import frontmatter

if TYPE_CHECKING:
    from knowledge.store import KnowledgeStore

logger = logging.getLogger("monolith.knowledge.gardener")

_EXCLUDED_DIRS = {"_processed", "_deleted_with_ttl", ".obsidian", ".trash"}
_TTL_HOURS = 24

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Model to use for the gardener. Override via GARDENER_MODEL env var.
_DEFAULT_MODEL = "claude-sonnet-4-5"

_SYSTEM_PROMPT = """\
You are a knowledge gardener. Your job is to decompose a raw note into atomic knowledge artifacts.

For each raw note, you should:
1. First, search for related existing notes using search_notes.
2. Read any closely related notes using get_note to understand existing coverage.
3. Decompose the raw note into one or more typed notes using create_note:
   - atom: a distilled concept or principle
   - fact: a specific, verifiable claim
   - active: a temporal or actionable item (journal entry, TODO, reminder)
4. Set appropriate edges on new notes (especially derives_from to link to related existing notes).
5. Optionally use patch_edges to add edges from existing notes back to the new ones.

Each created note should be atomic — covering exactly one concept, fact, or action. Prefer multiple small notes over one large note. Use clear, descriptive titles.\
"""

_TOOLS = [
    {
        "name": "search_notes",
        "description": "Search existing notes by semantic similarity. Use this to find related existing notes before creating new ones, so you can set appropriate edges.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search for similar notes.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_note",
        "description": "Read the full content of an existing note by its note_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The note_id (frontmatter id) of the note to read.",
                }
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new typed knowledge note. Each note should be atomic — one concept, one fact, or one actionable item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["atom", "fact", "active"],
                    "description": "atom = distilled concept/principle, fact = specific verifiable claim, active = temporal/actionable item (journal, TODO).",
                },
                "title": {
                    "type": "string",
                    "description": "Concise title for the note.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relevant tags for categorization.",
                },
                "edges": {
                    "type": "object",
                    "description": "Typed edges to other notes. Keys are edge types (refines, generalizes, related, contradicts, derives_from, supersedes), values are arrays of note_ids.",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "body": {
                    "type": "string",
                    "description": "The markdown body content of the note.",
                },
            },
            "required": ["type", "title", "body"],
        },
    },
    {
        "name": "patch_edges",
        "description": "Add edges to an existing note's frontmatter. Use this to link existing notes to the new notes you create.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The note_id of the existing note to patch.",
                },
                "edges": {
                    "type": "object",
                    "description": "Edges to add. Keys are edge types, values are arrays of note_ids.",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "required": ["note_id", "edges"],
        },
    },
]


def _is_error_result(result: str) -> bool:
    """Return True if a tool_result JSON string represents an error."""
    try:
        parsed = json.loads(result)
    except (ValueError, TypeError):
        return False
    return isinstance(parsed, dict) and "error" in parsed


def _slugify(text_in: str) -> str:
    normalized = unicodedata.normalize("NFKD", text_in)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    return slug or "note"


class _Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class GardenStats:
    ingested: int
    failed: int
    ttl_cleaned: int


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """Return (meta_dict, body) split from a markdown file's frontmatter.

    Returns ({}, raw) if no frontmatter block is present.
    """
    if not raw.startswith("---"):
        return {}, raw
    # Find the closing --- on its own line
    lines = raw.splitlines(keepends=True)
    if not lines or not lines[0].rstrip("\r\n") == "---":
        return {}, raw
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, raw
    block = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    try:
        meta = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(meta, dict):
        return {}, raw
    return meta, body


_DEFAULT_MAX_FILES_PER_RUN = 10


class Gardener:
    def __init__(
        self,
        *,
        vault_root: Path,
        anthropic_client: object | None,
        store: KnowledgeStore | None,
        embed_client: _Embedder | None,
        max_files_per_run: int = _DEFAULT_MAX_FILES_PER_RUN,
    ) -> None:
        self.vault_root = Path(vault_root)
        self.anthropic_client = anthropic_client
        self.store = store
        self.embed_client = embed_client
        # Cap the number of raw files processed per cycle. Each file triggers
        # a bounded tool-use loop against the Anthropic API (up to max_turns
        # calls), so an uncapped cycle over a large vault could burn through
        # API credit in a single tick. A value <= 0 disables the cap.
        self.max_files_per_run = max_files_per_run
        self.processed_root = self.vault_root / "_processed"
        self.deleted_root = self.vault_root / "_deleted_with_ttl"

    async def run(self) -> GardenStats:
        """Run one gardening cycle: ingest raw files, then TTL cleanup."""
        raw_files = self._discover_raw_files()
        if self.max_files_per_run > 0 and len(raw_files) > self.max_files_per_run:
            logger.info(
                "gardener: discovered %d raw files, capping this run at %d",
                len(raw_files),
                self.max_files_per_run,
            )
            raw_files = raw_files[: self.max_files_per_run]
        ingested = 0
        failed = 0
        for path in raw_files:
            try:
                await self._ingest_one(path)
                ingested += 1
            except Exception:
                logger.exception("gardener: failed to ingest %s", path)
                failed += 1
        ttl_cleaned = self._cleanup_ttl()
        stats = GardenStats(ingested=ingested, failed=failed, ttl_cleaned=ttl_cleaned)
        logger.info(
            "knowledge.garden: ingested=%d failed=%d ttl_cleaned=%d",
            stats.ingested,
            stats.failed,
            stats.ttl_cleaned,
        )
        return stats

    def _discover_raw_files(self) -> list[Path]:
        """Find .md files in the vault root that are not in excluded directories."""
        raw: list[Path] = []
        if not self.vault_root.exists():
            return raw
        for entry in self.vault_root.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.name in _EXCLUDED_DIRS:
                continue
            if entry.is_file():
                if entry.suffix == ".md":
                    raw.append(entry)
                continue
            if entry.is_dir():
                for p in entry.rglob("*.md"):
                    rel = p.relative_to(self.vault_root)
                    if any(part.startswith(".") for part in rel.parts):
                        continue
                    raw.append(p)
        return sorted(raw)

    async def _ingest_one(self, path: Path) -> None:
        """Decompose a single raw note via Sonnet tool-use loop."""
        if self.anthropic_client is None:
            raise RuntimeError("gardener: anthropic_client is not configured")

        raw = path.read_text(encoding="utf-8")
        meta, body = frontmatter.parse(raw)
        title = meta.title or path.stem

        model = os.environ.get("GARDENER_MODEL", _DEFAULT_MODEL)
        messages: list[dict] = [
            {
                "role": "user",
                "content": f"Decompose this note:\n\nTitle: {title}\n\n{body}",
            }
        ]

        # Tool-use loop — bounded to avoid runaway loops.
        created_any = False
        max_turns = 20
        for _ in range(max_turns):
            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                result = await self._handle_tool(block.name, block.input)
                if block.name == "create_note" and not _is_error_result(result):
                    created_any = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Loop exhausted without a non-tool_use stop_reason. Raise so
            # run() marks the file as failed and leaves the raw file in
            # place for the next cycle.
            raise RuntimeError(
                f"gardener: tool-use loop exhausted max_turns={max_turns} for {path}"
            )

        if not created_any:
            # Sonnet returned end_turn without creating any notes (e.g. a
            # refusal or plain-text apology). Don't soft-delete — leave the
            # raw file for the user to inspect or for the next cycle.
            logger.warning(
                "gardener: Sonnet produced no notes for %s; leaving raw file in place",
                path,
            )
            return

        self._soft_delete(path)

    async def _handle_tool(self, name: str, input_data: dict) -> str:
        """Dispatch a tool call and return the result as a string."""
        try:
            if name == "search_notes":
                return await self._handle_search_notes(input_data)
            if name == "get_note":
                return self._handle_get_note(input_data)
            if name == "create_note":
                return self._handle_create_note(input_data)
            if name == "patch_edges":
                return self._handle_patch_edges(input_data)
        except Exception as exc:
            logger.exception("gardener: tool %s failed", name)
            return json.dumps({"error": f"{name} failed: {exc}"})
        return json.dumps({"error": f"unknown tool: {name}"})

    async def _handle_search_notes(self, input_data: dict) -> str:
        if self.embed_client is None or self.store is None:
            return json.dumps({"error": "search unavailable: no store or embed client"})
        query = input_data["query"]
        embedding = await self.embed_client.embed(query)
        results = self.store.search_notes(query_embedding=embedding, limit=5)
        return json.dumps(results)

    def _handle_get_note(self, input_data: dict) -> str:
        if self.store is None:
            return json.dumps({"error": "store unavailable"})
        from sqlmodel import select

        from knowledge.models import Note

        note_id = input_data["note_id"]
        note = self.store.session.execute(
            select(Note).where(Note.note_id == note_id)
        ).scalar_one_or_none()
        if not note:
            return json.dumps({"error": f"note {note_id} not found"})
        path = self.vault_root / note.path
        if not path.exists():
            return json.dumps({"error": f"file not found for {note_id}"})
        return path.read_text(encoding="utf-8")

    def _handle_create_note(self, input_data: dict) -> str:
        note_type = input_data["type"]
        title = input_data["title"]
        tags = input_data.get("tags", [])
        edges = input_data.get("edges", {})
        body = input_data["body"]

        note_id = _slugify(title)

        fm: dict[str, Any] = {"id": note_id, "title": title, "type": note_type}
        if tags:
            fm["tags"] = tags
        if edges:
            fm["edges"] = edges

        fm_str = yaml.safe_dump(
            fm, default_flow_style=False, allow_unicode=True, sort_keys=False
        ).rstrip()
        content = f"---\n{fm_str}\n---\n{body}\n"

        self.processed_root.mkdir(parents=True, exist_ok=True)
        dest = self.processed_root / f"{note_id}.md"
        counter = 1
        while dest.exists():
            dest = self.processed_root / f"{note_id}-{counter}.md"
            counter += 1
        dest.write_text(content, encoding="utf-8")
        logger.info("gardener: created %s (%s)", dest.name, note_type)
        return json.dumps({"created": dest.name, "note_id": note_id})

    def _handle_patch_edges(self, input_data: dict) -> str:
        if self.store is None:
            return json.dumps({"error": "store unavailable"})
        from sqlmodel import select

        from knowledge.models import Note

        note_id = input_data["note_id"]
        new_edges = input_data["edges"]

        unknown_types = [k for k in new_edges if k not in frontmatter._KNOWN_EDGE_TYPES]
        if unknown_types:
            return json.dumps(
                {
                    "error": (
                        f"unknown edge types: {unknown_types}. "
                        f"Known types: {sorted(frontmatter._KNOWN_EDGE_TYPES)}"
                    ),
                }
            )

        note = self.store.session.execute(
            select(Note).where(Note.note_id == note_id)
        ).scalar_one_or_none()
        if not note:
            return json.dumps({"error": f"note {note_id} not found"})
        path = self.vault_root / note.path
        if not path.exists():
            return json.dumps({"error": f"file not found for {note_id}"})

        raw = path.read_text(encoding="utf-8")
        meta, body = frontmatter.parse(raw)
        for edge_type, targets in new_edges.items():
            existing = meta.edges.get(edge_type, [])
            merged = list(dict.fromkeys(existing + targets))  # dedupe, preserve order
            meta.edges[edge_type] = merged

        fm: dict[str, Any] = {}
        if meta.note_id:
            fm["id"] = meta.note_id
        if meta.title:
            fm["title"] = meta.title
        if meta.type:
            fm["type"] = meta.type
        if meta.status:
            fm["status"] = meta.status
        if meta.source:
            fm["source"] = meta.source
        if meta.tags:
            fm["tags"] = meta.tags
        if meta.aliases:
            fm["aliases"] = meta.aliases
        if meta.edges:
            fm["edges"] = meta.edges
        if meta.created:
            fm["created"] = meta.created.isoformat()
        if meta.updated:
            fm["updated"] = meta.updated.isoformat()
        if meta.extra:
            fm.update(meta.extra)

        fm_str = yaml.safe_dump(
            fm, default_flow_style=False, allow_unicode=True, sort_keys=False
        ).rstrip()
        new_raw = f"---\n{fm_str}\n---\n{body}"
        path.write_text(new_raw, encoding="utf-8")
        return json.dumps({"patched": note_id, "edges": meta.edges})

    def _soft_delete(self, source: Path) -> None:
        """Move a raw file to _deleted_with_ttl/ with a TTL in frontmatter."""
        rel = source.relative_to(self.vault_root)
        dest = self.deleted_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        raw = source.read_text(encoding="utf-8")
        ttl_dt = datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)
        ttl_iso = ttl_dt.isoformat()

        meta_dict, body = _split_frontmatter(raw)
        meta_dict["ttl"] = ttl_iso  # Overwrites any existing ttl

        new_raw = (
            f"---\n{yaml.safe_dump(meta_dict, sort_keys=False).rstrip()}\n---\n{body}"
        )

        dest.write_text(new_raw, encoding="utf-8")
        source.unlink()

    def _cleanup_ttl(self) -> int:
        """Delete files in _deleted_with_ttl/ whose TTL has expired."""
        if not self.deleted_root.exists():
            return 0
        now = datetime.now(timezone.utc)
        cleaned = 0
        for p in list(self.deleted_root.rglob("*.md")):
            try:
                raw = p.read_text(encoding="utf-8")
                meta, _ = frontmatter.parse(raw)
                ttl_str = meta.extra.get("ttl")
                if not ttl_str:
                    continue
                ttl_dt = datetime.fromisoformat(str(ttl_str))
                if ttl_dt.tzinfo is None:
                    ttl_dt = ttl_dt.replace(tzinfo=timezone.utc)
                if now >= ttl_dt:
                    p.unlink()
                    cleaned += 1
            except (
                ValueError,
                OSError,
                yaml.YAMLError,
                frontmatter.FrontmatterError,
            ) as exc:
                logger.warning("gardener: failed to check TTL for %s: %s", p, exc)
        return cleaned
