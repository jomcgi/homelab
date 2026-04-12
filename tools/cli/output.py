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
