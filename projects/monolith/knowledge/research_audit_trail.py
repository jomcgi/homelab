"""Parse `claude --print --output-format stream-json` transcripts into a
mechanically-verifiable audit trail of tool retrievals.

The research agent uses Claude's built-in tools (WebFetch/WebSearch/Read/
Glob/Grep). Each successful tool-use becomes an AuditEntry; the harness
filters research claims against ``trail.refs`` so a claim cannot cite a
URL the agent never actually fetched -- preserving the original "never
trust prose for citations" invariant from the Qwen-era design without
requiring a second LLM pass.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# Tools whose successful invocations contribute citable refs.
# WebFetch -> URL, Read -> vault: or absolute path.
_CITABLE_TOOLS = frozenset({"WebFetch", "Read"})

# Tools whose invocations are recorded for debugging but do NOT yield
# citable refs (a claim cannot cite a search query).
_RECORDED_TOOLS = frozenset({"WebSearch", "Glob", "Grep"})


@dataclass(frozen=True)
class AuditEntry:
    tool: str
    ref: str  # URL for WebFetch, vault:path or absolute path for Read,
    # query for WebSearch, glob:/grep: prefix for Glob/Grep.


@dataclass(frozen=True)
class AuditTrail:
    entries: tuple[AuditEntry, ...]

    @property
    def refs(self) -> frozenset[str]:
        """The subset of entries whose refs are citable in a research claim.

        Only WebFetch URLs and Read paths qualify -- a claim can be backed
        by a fetched page or a vault note, but not by a search query.
        """
        return frozenset(e.ref for e in self.entries if e.tool in _CITABLE_TOOLS)


def parse_stream_json(
    transcript: str, *, vault_root: str | Path | None = None
) -> AuditTrail:
    """Parse stream-json stdout into an AuditTrail.

    Tolerates malformed lines (logs and skips). Pairs tool_use with
    tool_result by ``tool_use_id``; only successful (is_error=False)
    pairs become entries. Unknown tools are silently dropped.
    """
    pending: dict[str, tuple[str, dict]] = {}
    successes: list[tuple[str, dict]] = []

    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(
                "research_audit_trail: skipping malformed line: %r", line[:200]
            )
            continue

        if event.get("type") == "assistant":
            for part in _iter_content(event):
                if part.get("type") == "tool_use":
                    pending[part["id"]] = (
                        part.get("name", ""),
                        part.get("input", {}) or {},
                    )
        elif event.get("type") == "user":
            for part in _iter_content(event):
                if part.get("type") != "tool_result":
                    continue
                tu_id = part.get("tool_use_id")
                if tu_id is None or part.get("is_error"):
                    pending.pop(tu_id, None)
                    continue
                call = pending.pop(tu_id, None)
                if call is not None:
                    successes.append(call)

    entries: list[AuditEntry] = []
    vault_str = str(vault_root) if vault_root is not None else None
    for name, args in successes:
        entry = _to_entry(name, args, vault_str)
        if entry is not None:
            entries.append(entry)
    return AuditTrail(entries=tuple(entries))


def _iter_content(event: dict) -> Iterable[dict]:
    msg = event.get("message") or {}
    content = msg.get("content") or []
    if isinstance(content, list):
        yield from (p for p in content if isinstance(p, dict))


def _to_entry(name: str, args: dict, vault_root: str | None) -> AuditEntry | None:
    if name == "WebFetch":
        url = args.get("url")
        return AuditEntry(tool="WebFetch", ref=url) if url else None
    if name == "WebSearch":
        query = args.get("query")
        return AuditEntry(tool="WebSearch", ref=query) if query else None
    if name == "Read":
        path = args.get("file_path")
        if not path:
            return None
        return AuditEntry(tool="Read", ref=_normalize_read_path(path, vault_root))
    if name == "Glob":
        pat = args.get("pattern")
        return AuditEntry(tool="Glob", ref=f"glob:{pat}") if pat else None
    if name == "Grep":
        pat = args.get("pattern")
        return AuditEntry(tool="Grep", ref=f"grep:{pat}") if pat else None
    return None


def _normalize_read_path(path: str, vault_root: str | None) -> str:
    """Map an absolute Read path to ``vault:<rel>`` if it lies inside vault_root,
    else return the path unchanged. Keeps citation refs short and stable."""
    if vault_root is None:
        return path
    try:
        rel = Path(path).resolve().relative_to(Path(vault_root).resolve())
    except (ValueError, OSError):
        return path
    return f"vault:{rel}"
