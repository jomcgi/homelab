"""Additional coverage for web_search -- HTTP errors, missing fields, base_url env var."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.web_search import search_web


class TestSearchWebHTTPErrors:
    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        """search_web propagates HTTP errors raised by raise_for_status."""
        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(),
        )

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await search_web("test", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(self):
        """search_web propagates connection errors from httpx."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.ConnectError):
                await search_web("test", base_url="http://fake:8080")


class TestSearchWebEmptyResults:
    @pytest.mark.asyncio
    async def test_returns_empty_string_for_no_results(self):
        """search_web returns an empty string when results list is empty."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"results": []}

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("no hits", base_url="http://fake:8080")

        assert result == ""


class TestSearchWebBaseUrlFromEnv:
    @pytest.mark.asyncio
    async def test_uses_searxng_url_env_var_when_no_base_url(self):
        """search_web uses SEARXNG_URL env var when base_url is not provided."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "results": [
                {"title": "T", "content": "C", "url": "http://ex.com"}
            ]
        }

        with patch.dict(os.environ, {"SEARXNG_URL": "http://env-searxng:8888"}):
            # Re-import or patch the module-level constant directly
            with patch("chat.web_search.SEARXNG_URL", "http://env-searxng:8888"):
                with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=False)
                    mock_client.get.return_value = fake_response
                    mock_cls.return_value = mock_client

                    await search_web("query")

                    call_args = mock_client.get.call_args
                    assert "http://env-searxng:8888" in call_args[0][0]


class TestSearchWebMissingFields:
    @pytest.mark.asyncio
    async def test_raises_on_missing_title_field(self):
        """search_web raises KeyError when a result is missing the 'title' field."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        # Result missing 'title'
        fake_response.json.return_value = {
            "results": [{"content": "C", "url": "http://ex.com"}]
        }

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(KeyError):
                await search_web("test", base_url="http://fake:8080")
