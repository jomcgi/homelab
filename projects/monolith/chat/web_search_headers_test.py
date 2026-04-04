"""Tests for chat.web_search.search_web() -- HTTP headers and query parameters."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chat.web_search import search_web


def _fake_response(results=None):
    """Build a minimal fake httpx response."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": results
        or [
            {
                "title": "Example",
                "content": "Some content",
                "url": "http://example.com",
            }
        ]
    }
    return resp


class _FakeAsyncClient:
    """Context-manager compatible fake for httpx.AsyncClient."""

    def __init__(self, response, **kwargs):
        self._response = response
        self.init_kwargs = kwargs
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self._response


class TestSearchWebHeaders:
    @pytest.mark.asyncio
    async def test_sends_x_forwarded_for_header(self):
        """search_web creates the AsyncClient with X-Forwarded-For: 127.0.0.1 header."""
        fake_client = _FakeAsyncClient(_fake_response())

        with patch("chat.web_search.httpx.AsyncClient", return_value=fake_client) as mock_cls:
            await search_web("test query", base_url="http://fake:8080")

        # Check the headers passed to AsyncClient constructor
        _, kwargs = mock_cls.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("X-Forwarded-For") == "127.0.0.1", (
            f"Expected X-Forwarded-For: 127.0.0.1 in headers, got: {headers}"
        )

    @pytest.mark.asyncio
    async def test_sends_format_json_query_param(self):
        """search_web passes format=json as a query parameter to the SearXNG endpoint."""
        fake_client = _FakeAsyncClient(_fake_response())

        with patch("chat.web_search.httpx.AsyncClient", return_value=fake_client):
            await search_web("another query", base_url="http://fake:8080")

        assert len(fake_client.get_calls) == 1
        _, call_kwargs = fake_client.get_calls[0]
        params = call_kwargs.get("params", {})
        assert params.get("format") == "json", (
            f"Expected format=json in query params, got: {params}"
        )

    @pytest.mark.asyncio
    async def test_sends_query_as_q_param(self):
        """search_web passes the query string as the 'q' parameter."""
        fake_client = _FakeAsyncClient(_fake_response())

        with patch("chat.web_search.httpx.AsyncClient", return_value=fake_client):
            await search_web("python testing", base_url="http://fake:8080")

        _, call_kwargs = fake_client.get_calls[0]
        params = call_kwargs.get("params", {})
        assert params.get("q") == "python testing"

    @pytest.mark.asyncio
    async def test_hits_search_endpoint(self):
        """search_web calls the /search path of the base URL."""
        fake_client = _FakeAsyncClient(_fake_response())

        with patch("chat.web_search.httpx.AsyncClient", return_value=fake_client):
            await search_web("foo", base_url="http://searxng:8888")

        url, _ = fake_client.get_calls[0]
        assert url == "http://searxng:8888/search"

    @pytest.mark.asyncio
    async def test_x_forwarded_for_and_format_json_together(self):
        """Both X-Forwarded-For header and format=json param are sent in the same request."""
        fake_client = _FakeAsyncClient(_fake_response())

        with patch("chat.web_search.httpx.AsyncClient", return_value=fake_client) as mock_cls:
            await search_web("combined check", base_url="http://fake:8080")

        # Verify header in constructor
        _, ctor_kwargs = mock_cls.call_args
        headers = ctor_kwargs.get("headers", {})
        assert headers.get("X-Forwarded-For") == "127.0.0.1"

        # Verify param in get() call
        _, get_kwargs = fake_client.get_calls[0]
        assert get_kwargs.get("params", {}).get("format") == "json"
