"""Generic HTML extractor using trafilatura."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
import trafilatura

from projects.blog_knowledge_graph.knowledge_graph.app.extractors.base import (
    fetch_with_retry,
)
from projects.blog_knowledge_graph.knowledge_graph.app.models import Document

logger = logging.getLogger(__name__)


class HTMLExtractor:
    """Extracts article content from HTML pages, converts to markdown."""

    def can_handle(self, url: str, source_type: str) -> bool:
        return source_type == "html"

    async def extract(self, url: str, client: httpx.AsyncClient) -> list[Document]:
        response = await fetch_with_retry(client, url)
        html = response.text

        content = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_images=False,
            favor_recall=True,
        )
        if not content:
            logger.warning("No content extracted from %s", url)
            return []

        metadata = trafilatura.bare_extraction(html)

        title = ""
        author = None
        published_at = None

        if metadata:
            title = metadata.get("title", "") or ""
            author = metadata.get("author") or None
            date_str = metadata.get("date")
            if date_str:
                try:
                    published_at = datetime.fromisoformat(date_str)
                except (ValueError, TypeError):
                    pass

        return [
            Document(
                source_type="html",
                source_url=url,
                title=title,
                author=author,
                published_at=published_at,
                content=content,
            )
        ]
