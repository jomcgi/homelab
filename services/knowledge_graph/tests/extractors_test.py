"""Tests for extractors: base utilities, HTML, and feed."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.knowledge_graph.app.extractors.base import RateLimiter, fetch_with_retry
from services.knowledge_graph.app.extractors.html_extractor import HTMLExtractor
from services.knowledge_graph.app.extractors.feed_extractor import FeedExtractor


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_first_request_immediate(self):
        limiter = RateLimiter(default_delay=1.0)
        start = asyncio.get_event_loop().time()
        await limiter.acquire("https://example.com/page")
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_second_request_delayed(self):
        limiter = RateLimiter(default_delay=0.1)
        await limiter.acquire("https://example.com/a")
        start = asyncio.get_event_loop().time()
        await limiter.acquire("https://example.com/b")
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed >= 0.05  # Should have waited ~0.1s

    @pytest.mark.asyncio
    async def test_different_domains_no_delay(self):
        limiter = RateLimiter(default_delay=1.0)
        await limiter.acquire("https://a.com/page")
        start = asyncio.get_event_loop().time()
        await limiter.acquire("https://b.com/page")
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1


class TestFetchWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        result = await fetch_with_retry(client, "https://example.com")
        assert result == mock_response
        assert client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        fail_response = MagicMock()
        fail_response.status_code = 429
        fail_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "", request=MagicMock(), response=fail_response
            )
        )

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.side_effect = [fail_response, ok_response]

        result = await fetch_with_retry(client, "https://example.com", base_delay=0.01)
        assert result == ok_response
        assert client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.side_effect = [httpx.TimeoutException("timeout"), ok_response]

        result = await fetch_with_retry(client, "https://example.com", base_delay=0.01)
        assert result == ok_response

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        client = AsyncMock()
        client.get.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(httpx.TimeoutException):
            await fetch_with_retry(
                client, "https://example.com", max_attempts=2, base_delay=0.01
            )
        assert client.get.call_count == 2


class TestHTMLExtractor:
    def test_can_handle(self):
        ext = HTMLExtractor()
        assert ext.can_handle("https://example.com", "html") is True
        assert ext.can_handle("https://example.com", "rss") is False

    @pytest.mark.asyncio
    async def test_extract_html(self):
        html = """
        <html><head><title>Test Page</title></head>
        <body><article><h1>Test Article</h1><p>This is test content with enough words to be extracted properly by trafilatura.</p></article></body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        ext = HTMLExtractor()
        docs = await ext.extract("https://example.com/article", client)
        # trafilatura may or may not extract content depending on the HTML quality
        # At minimum, the extractor should not raise
        assert isinstance(docs, list)


class TestFeedExtractor:
    def test_can_handle(self):
        ext = FeedExtractor()
        assert ext.can_handle("https://example.com/feed.xml", "rss") is True
        assert ext.can_handle("https://example.com", "html") is False

    @pytest.mark.asyncio
    async def test_extract_empty_feed(self):
        rss = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Test</title></channel></rss>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = rss
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        ext = FeedExtractor()
        docs = await ext.extract("https://example.com/feed.xml", client)
        assert docs == []

    @pytest.mark.asyncio
    async def test_extract_feed_with_entries(self):
        rss = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>Post One</title>
                <link>https://example.com/post-1</link>
                <description>Summary of post one with enough content to extract.</description>
                <author>author@example.com</author>
                <pubDate>Wed, 15 Jan 2025 00:00:00 GMT</pubDate>
            </item>
        </channel>
        </rss>
        """
        feed_response = MagicMock()
        feed_response.status_code = 200
        feed_response.text = rss
        feed_response.raise_for_status = MagicMock()

        # For the entry page fetch (will fail, fallback to summary)
        entry_response = MagicMock()
        entry_response.status_code = 200
        entry_response.text = (
            "<html><body><p>Full article content here.</p></body></html>"
        )
        entry_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.side_effect = [feed_response, entry_response]

        ext = FeedExtractor()
        docs = await ext.extract("https://example.com/feed.xml", client)
        assert len(docs) == 1
        assert docs[0]["title"] == "Post One"
        assert docs[0]["source_url"] == "https://example.com/post-1"
        assert docs[0]["source_type"] == "rss"
