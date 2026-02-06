"""Shared data models for the knowledge graph scraper."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, TypedDict


class Document(TypedDict):
    source_type: str
    source_url: str
    title: str
    author: str | None
    published_at: datetime | None
    content: str  # markdown


class SourceConfig(TypedDict):
    url: str
    type: Literal["rss", "html"]
    name: str | None


class ScrapeResult(TypedDict):
    url: str
    content_hash: str | None
    is_new: bool
    title: str
    error: str | None


class ChunkPayload(TypedDict):
    content_hash: str
    chunk_index: int
    chunk_text: str
    section_header: str
    source_url: str
    source_type: str
    title: str
    author: str | None
    published_at: str | None


def content_hash(content: str) -> str:
    """SHA256 hash of content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
