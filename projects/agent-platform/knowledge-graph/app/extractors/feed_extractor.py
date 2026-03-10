"""RSS/Atom feed extractor using feedparser."""

from __future__ import annotations

import logging
from datetime import datetime
from time import mktime

import feedparser
import httpx
import trafilatura

from services.knowledge_graph.app.extractors.base import RateLimiter, fetch_with_retry
from services.knowledge_graph.app.models import Document

logger = logging.getLogger(__name__)


class FeedExtractor:
    """Parses RSS/Atom feeds and extracts each entry's content."""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._rate_limiter = rate_limiter

    def can_handle(self, url: str, source_type: str) -> bool:
        return source_type == "rss"

    async def extract(self, url: str, client: httpx.AsyncClient) -> list[Document]:
        response = await fetch_with_retry(client, url)
        feed = feedparser.parse(response.text)

        if feed.bozo and not feed.entries:
            logger.warning("Failed to parse feed %s: %s", url, feed.bozo_exception)
            return []

        documents: list[Document] = []
        for entry in feed.entries:
            entry_url = entry.get("link", "")
            if not entry_url:
                continue

            title = entry.get("title", "")
            author = entry.get("author") or None
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime.fromtimestamp(
                        mktime(entry.published_parsed)
                    )
                except (ValueError, OverflowError):
                    pass

            # Try to extract full content from the entry page
            content = None
            try:
                if self._rate_limiter:
                    await self._rate_limiter.acquire(entry_url)
                entry_response = await fetch_with_retry(client, entry_url)
                content = trafilatura.extract(
                    entry_response.text,
                    output_format="markdown",
                    include_links=True,
                    include_images=False,
                    favor_recall=True,
                )
            except Exception:
                logger.warning("Failed to fetch entry %s, using summary", entry_url)

            # Fall back to feed summary/content if page fetch failed
            if not content:
                raw_content = ""
                if hasattr(entry, "content") and entry.content:
                    raw_content = entry.content[0].get("value", "")
                elif hasattr(entry, "summary"):
                    raw_content = entry.summary or ""
                if raw_content:
                    content = trafilatura.extract(
                        raw_content,
                        output_format="markdown",
                        include_links=True,
                        include_images=False,
                    )
                if not content:
                    content = raw_content

            if not content:
                logger.warning("No content for feed entry %s", entry_url)
                continue

            documents.append(
                Document(
                    source_type="rss",
                    source_url=entry_url,
                    title=title,
                    author=author,
                    published_at=published_at,
                    content=content,
                )
            )

        logger.info("Extracted %d documents from feed %s", len(documents), url)
        return documents
