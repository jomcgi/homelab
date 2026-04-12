"""Tests for fetch_webpage() title fallback branches.

The title extraction logic in fetch_webpage() has three branches:

    meta = trafilatura.extract_metadata(html)
    title = meta.title if meta and meta.title else urlparse(url).netloc

1. meta is None            → falls back to urlparse(url).netloc
2. meta.title is None      → falls back to urlparse(url).netloc
3. meta.title is ""        → falls back to urlparse(url).netloc (falsy)

The existing ingest_queue_test.py always exercises the happy path where
meta.title is a non-empty string.  None of these three branches are
covered by any existing test file.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from knowledge.ingest_queue import fetch_webpage


class TestFetchWebpageTitleFallback:
    """fetch_webpage() uses urlparse(url).netloc as title when metadata is absent."""

    @pytest.mark.asyncio
    async def test_meta_none_falls_back_to_netloc(self):
        """When trafilatura.extract_metadata returns None, title is the netloc."""
        with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Content</body></html>"
            mock_traf.extract.return_value = "Article body text."
            mock_traf.extract_metadata.return_value = None  # ← the gap

            title, body = await fetch_webpage("https://example.com/article")

        assert title == "example.com"
        assert body == "Article body text."

    @pytest.mark.asyncio
    async def test_meta_title_none_falls_back_to_netloc(self):
        """When meta is not None but meta.title is None, title is the netloc."""
        meta = MagicMock()
        meta.title = None  # ← the gap

        with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Content</body></html>"
            mock_traf.extract.return_value = "Article body text."
            mock_traf.extract_metadata.return_value = meta

            title, body = await fetch_webpage("https://news.example.org/story")

        assert title == "news.example.org"
        assert body == "Article body text."

    @pytest.mark.asyncio
    async def test_meta_title_empty_string_falls_back_to_netloc(self):
        """When meta.title is an empty string (falsy), title is the netloc."""
        meta = MagicMock()
        meta.title = ""  # ← the gap

        with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Content</body></html>"
            mock_traf.extract.return_value = "Article body text."
            mock_traf.extract_metadata.return_value = meta

            title, body = await fetch_webpage("https://blog.example.net/post/1")

        assert title == "blog.example.net"

    @pytest.mark.asyncio
    async def test_happy_path_with_meta_title_not_affected(self):
        """Sanity: when meta.title is set, it is used verbatim (no regression)."""
        meta = MagicMock()
        meta.title = "My Article Title"

        with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Content</body></html>"
            mock_traf.extract.return_value = "Body."
            mock_traf.extract_metadata.return_value = meta

            title, _ = await fetch_webpage("https://example.com/article")

        assert title == "My Article Title"

    @pytest.mark.asyncio
    async def test_netloc_extracted_from_complex_url(self):
        """Title fallback correctly extracts netloc from a URL with path and query."""
        with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Text</body></html>"
            mock_traf.extract.return_value = "Some content here."
            mock_traf.extract_metadata.return_value = None

            title, _ = await fetch_webpage(
                "https://sub.domain.example.co.uk/path/to/page?q=1&ref=2"
            )

        assert title == "sub.domain.example.co.uk"
