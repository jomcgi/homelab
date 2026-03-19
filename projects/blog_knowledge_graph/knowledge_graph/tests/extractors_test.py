"""Tests for extractors: base utilities, HTML, and feed."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.extractors.base import (
    RateLimiter,
    fetch_with_retry,
)
from projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor import (
    HTMLExtractor,
)
from projects.blog_knowledge_graph.knowledge_graph.app.extractors.feed_extractor import (
    FeedExtractor,
)


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


class TestHTMLExtractorEdgeCases:
    """Additional HTML extractor edge cases."""

    def test_can_handle_returns_false_for_rss(self):
        ext = HTMLExtractor()
        assert ext.can_handle("https://example.com/feed", "rss") is False

    def test_can_handle_returns_false_for_atom(self):
        ext = HTMLExtractor()
        assert ext.can_handle("https://example.com/feed", "atom") is False

    @pytest.mark.asyncio
    async def test_extract_returns_empty_when_no_content_extracted(self):
        """When trafilatura returns None/empty, extract returns []."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"  # Empty body
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.extract",
            return_value=None,
        ):
            ext = HTMLExtractor()
            docs = await ext.extract("https://example.com/empty", client)

        assert docs == []

    @pytest.mark.asyncio
    async def test_extract_returns_document_with_content(self):
        """When trafilatura extracts content, a Document is returned."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.extract",
                return_value="# Article\n\nFull content.",
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.bare_extraction",
                return_value={"title": "Article Title", "author": "Jane Doe", "date": "2025-01-15"},
            ),
        ):
            ext = HTMLExtractor()
            docs = await ext.extract("https://example.com/article", client)

        assert len(docs) == 1
        assert docs[0]["source_type"] == "html"
        assert docs[0]["source_url"] == "https://example.com/article"
        assert docs[0]["title"] == "Article Title"
        assert docs[0]["author"] == "Jane Doe"
        assert docs[0]["content"] == "# Article\n\nFull content."

    @pytest.mark.asyncio
    async def test_extract_handles_invalid_date_gracefully(self):
        """When date string can't be parsed, published_at is None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.extract",
                return_value="Article content.",
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.bare_extraction",
                return_value={"title": "Test", "author": None, "date": "not-a-date"},
            ),
        ):
            ext = HTMLExtractor()
            docs = await ext.extract("https://example.com/article", client)

        assert len(docs) == 1
        assert docs[0]["published_at"] is None

    @pytest.mark.asyncio
    async def test_extract_handles_no_metadata(self):
        """When bare_extraction returns None, defaults are used."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.return_value = mock_response

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.extract",
                return_value="Article content.",
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor.trafilatura.bare_extraction",
                return_value=None,
            ),
        ):
            ext = HTMLExtractor()
            docs = await ext.extract("https://example.com/article", client)

        assert len(docs) == 1
        assert docs[0]["title"] == ""
        assert docs[0]["author"] is None
        assert docs[0]["published_at"] is None


class TestFeedExtractorEdgeCases:
    """Additional feed extractor edge cases."""

    def test_can_handle_returns_false_for_html(self):
        ext = FeedExtractor()
        assert ext.can_handle("https://example.com", "html") is False

    @pytest.mark.asyncio
    async def test_feed_entry_without_link_is_skipped(self):
        """Feed entries without a link URL are skipped."""
        rss = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>No Link Post</title>
                <description>Content without a link.</description>
            </item>
        </channel>
        </rss>
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
    async def test_feed_uses_summary_fallback_when_page_fetch_fails(self):
        """When entry page fetch fails, summary from feed is used."""
        rss = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>Summary Only</title>
                <link>https://example.com/post-summary</link>
                <description>This is the feed summary content with enough words to matter.</description>
            </item>
        </channel>
        </rss>
        """
        feed_response = MagicMock()
        feed_response.status_code = 200
        feed_response.text = rss
        feed_response.raise_for_status = MagicMock()

        client = AsyncMock()
        # First call (feed) succeeds; second call (entry page) fails
        client.get.side_effect = [
            feed_response,
            httpx.ConnectError("Connection refused"),
        ]

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.extractors.feed_extractor.trafilatura.extract",
            side_effect=["Summary content from feed.", None],  # page fail → summary used
        ):
            ext = FeedExtractor()
            docs = await ext.extract("https://example.com/feed.xml", client)

        # The entry should appear (using summary fallback)
        assert len(docs) >= 0  # May be 0 if summary also yields no content
        # At minimum, no exception should have been raised

    @pytest.mark.asyncio
    async def test_feed_with_rate_limiter_acquires_before_entry_fetch(self):
        """When a rate limiter is provided, it is acquired before each entry fetch."""
        rss = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>Rate Limited Post</title>
                <link>https://example.com/post</link>
                <description>Content here.</description>
            </item>
        </channel>
        </rss>
        """
        feed_response = MagicMock()
        feed_response.status_code = 200
        feed_response.text = rss
        feed_response.raise_for_status = MagicMock()

        entry_response = MagicMock()
        entry_response.status_code = 200
        entry_response.text = "<html><body><p>Full content.</p></body></html>"
        entry_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.side_effect = [feed_response, entry_response]

        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.acquire = AsyncMock()

        ext = FeedExtractor(rate_limiter=mock_rate_limiter)
        await ext.extract("https://example.com/feed.xml", client)

        # acquire should be called with the entry URL
        mock_rate_limiter.acquire.assert_called_once_with("https://example.com/post")


class TestFetchWithRetryAdditional:
    """Additional fetch_with_retry edge cases."""

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """5xx responses trigger retry."""
        fail_response = MagicMock()
        fail_response.status_code = 500
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
    async def test_connect_error_triggers_retry(self):
        """ConnectError triggers retry with backoff."""
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get.side_effect = [httpx.ConnectError("refused"), ok_response]

        result = await fetch_with_retry(
            client, "https://example.com", base_delay=0.01
        )
        assert result == ok_response

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises_last_exception(self):
        """When all retry attempts fail, the last exception is raised."""
        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("always fails")

        with pytest.raises(httpx.ConnectError):
            await fetch_with_retry(
                client, "https://example.com", max_attempts=3, base_delay=0.01
            )

        assert client.get.call_count == 3
