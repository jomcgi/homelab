"""Tests for chat.web_search.search_web() -- HTTP headers and query parameters."""

from unittest.mock import AsyncMock, MagicMock, patch

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


def _mock_async_client(response=None):
    """Return an AsyncMock that behaves as an async context manager httpx.AsyncClient.

    The mock is pre-wired so that:
    - ``async with httpx.AsyncClient(...) as client`` yields itself
    - ``await client.get(url, ...)`` returns *response*
    """
    if response is None:
        response = _fake_response()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get.return_value = response
    return client


class TestSearchWebHeaders:
    @pytest.mark.asyncio
    async def test_sends_x_forwarded_for_header(self):
        """search_web creates the AsyncClient with X-Forwarded-For: 127.0.0.1 header."""
        mock_client = _mock_async_client()

        with patch(
            "chat.web_search.httpx.AsyncClient", return_value=mock_client
        ) as mock_cls:
            await search_web("test query", base_url="http://fake:8080")

        _, kwargs = mock_cls.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("X-Forwarded-For") == "127.0.0.1", (
            f"Expected X-Forwarded-For: 127.0.0.1 in headers, got: {headers}"
        )

    @pytest.mark.asyncio
    async def test_sends_format_json_query_param(self):
        """search_web passes format=json as a query parameter to the SearXNG endpoint."""
        mock_client = _mock_async_client()

        with patch("chat.web_search.httpx.AsyncClient", return_value=mock_client):
            await search_web("another query", base_url="http://fake:8080")

        mock_client.get.assert_called_once()
        _, call_kwargs = mock_client.get.call_args
        params = call_kwargs.get("params", {})
        assert params.get("format") == "json", (
            f"Expected format=json in query params, got: {params}"
        )

    @pytest.mark.asyncio
    async def test_sends_query_as_q_param(self):
        """search_web passes the query string as the 'q' parameter."""
        mock_client = _mock_async_client()

        with patch("chat.web_search.httpx.AsyncClient", return_value=mock_client):
            await search_web("python testing", base_url="http://fake:8080")

        _, call_kwargs = mock_client.get.call_args
        params = call_kwargs.get("params", {})
        assert params.get("q") == "python testing"

    @pytest.mark.asyncio
    async def test_hits_search_endpoint(self):
        """search_web calls the /search path of the base URL."""
        mock_client = _mock_async_client()

        with patch("chat.web_search.httpx.AsyncClient", return_value=mock_client):
            await search_web("foo", base_url="http://searxng:8888")

        call_args = mock_client.get.call_args
        url = call_args[0][0]
        assert url == "http://searxng:8888/search"

    @pytest.mark.asyncio
    async def test_x_forwarded_for_and_format_json_together(self):
        """Both X-Forwarded-For header and format=json param are sent in the same request."""
        mock_client = _mock_async_client()

        with patch(
            "chat.web_search.httpx.AsyncClient", return_value=mock_client
        ) as mock_cls:
            await search_web("combined check", base_url="http://fake:8080")

        # Verify header in constructor
        _, ctor_kwargs = mock_cls.call_args
        headers = ctor_kwargs.get("headers", {})
        assert headers.get("X-Forwarded-For") == "127.0.0.1"

        # Verify param in get() call
        _, get_kwargs = mock_client.get.call_args
        assert get_kwargs.get("params", {}).get("format") == "json"
