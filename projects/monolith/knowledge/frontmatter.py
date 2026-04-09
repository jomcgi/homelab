"""Lenient YAML frontmatter parser for Obsidian-style notes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
import datetime as _dt
from datetime import datetime, timezone
from typing import Any

import yaml

logger = logging.getLogger("monolith.knowledge.frontmatter")


class FrontmatterError(Exception):
    """Raised when a file has a frontmatter block that fails to parse."""


_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)

_PROMOTED_KEYS = {
    "id",
    "title",
    "type",
    "status",
    "source",
    "tags",
    "aliases",
    "edges",
    "created",
    "updated",
}

# Mirror of the CHECK constraint in chart/migrations/20260408000000_knowledge_schema.sql:67-70 — keep in sync.
_KNOWN_EDGE_TYPES = frozenset(
    {
        "refines",
        "generalizes",
        "related",
        "contradicts",
        "derives_from",
        "supersedes",
    }
)


@dataclass
class ParsedFrontmatter:
    note_id: str | None = None
    title: str | None = None
    type: str | None = None
    status: str | None = None
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    edges: dict[str, list[str]] = field(default_factory=dict)
    created: datetime | None = None
    updated: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def parse(raw: str) -> tuple[ParsedFrontmatter, str]:
    """Return (metadata, body).

    A file without any frontmatter block is a valid empty-metadata file and
    returns an empty ``ParsedFrontmatter`` with the full raw body. A file
    with a frontmatter block that fails to parse (invalid YAML, or YAML that
    is not a mapping) raises ``FrontmatterError`` — callers must skip such
    files rather than overwrite the existing row with empty defaults.
    """
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return ParsedFrontmatter(), raw
    block = match.group(1)
    body = raw[match.end() :]
    try:
        data = yaml.safe_load(block) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"failed to parse frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontmatterError(f"frontmatter is not a mapping: {type(data).__name__}")
    return _build(data), body


def _json_safe(v: Any) -> Any:
    """Coerce YAML-parsed values to JSON-serializable types.

    YAML safe_load produces Python date/datetime objects for bare ISO dates.
    These must be converted to strings before the extra dict reaches json.dumps.
    """
    if isinstance(v, _dt.datetime):
        return v.isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    return v


def _build(data: dict[str, Any]) -> ParsedFrontmatter:
    meta = ParsedFrontmatter()
    meta.note_id = _str_or_none(data.get("id"))
    meta.title = _str_or_none(data.get("title"))
    meta.type = _str_or_none(data.get("type"))
    meta.status = _str_or_none(data.get("status"))
    meta.source = _str_or_none(data.get("source"))
    meta.tags = _string_list(data.get("tags"))
    meta.aliases = _string_list(data.get("aliases"))
    meta.edges = _edges(data.get("edges"))
    meta.created = _to_datetime(data.get("created"))
    meta.updated = _to_datetime(data.get("updated"))
    meta.extra = {k: _json_safe(v) for k, v in data.items() if k not in _PROMOTED_KEYS}
    return meta


def _edges(v: Any) -> dict[str, list[str]]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        logger.warning("frontmatter edges is not a mapping: %r", type(v).__name__)
        return {}
    out: dict[str, list[str]] = {}
    for key, raw in v.items():
        key = str(key)
        if key not in _KNOWN_EDGE_TYPES:
            logger.warning("unknown edge type %r in frontmatter, dropping", key)
            continue
        targets = _string_list(raw)
        if targets:
            out[key] = targets
    return out


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)


def _string_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        if "," in v:
            return [p.strip() for p in v.split(",") if p.strip()]
        return [p for p in v.split() if p]
    return []


def _to_datetime(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if hasattr(v, "year") and hasattr(v, "month") and hasattr(v, "day"):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            logger.warning("invalid date in frontmatter: %r", v)
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    logger.warning("unparseable date type in frontmatter: %r", type(v).__name__)
    return None
