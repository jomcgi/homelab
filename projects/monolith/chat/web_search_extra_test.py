"""Extra coverage for web_search.py -- TimeoutException path and request params verification."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.web_search import search_web


class TestSearchWebTimeout:
    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """search_web propagates httpx.TimeoutException when the request times out."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.side_effect = httpx.TimeoutException("request timed out")
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.TimeoutException):
                await search_web("what time is it", base_url="http://fake:8080")


class TestSearchWebRequestParams:
    @pytest.mark.asyncio
    async def test_request_includes_q_param_with_query(self):
        """search_web sends the query as the 'q' param in the GET request."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "results": [{"title": "T", "content": "C", "url": "http://ex.com"}]
        }

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            await search_web("my specific query", base_url="http://fake:8080")

            call_kwargs = mock_client.get.call_args
            params = call_kwargs[1]["params"]
            assert params["q"] == "my specific query"

    @pytest.mark.asyncio
    async def test_request_includes_format_json_param(self):
        """search_web sends 'format=json' as a request parameter."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "results": [{"title": "T", "content": "C", "url": "http://ex.com"}]
        }

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            await search_web("anything", base_url="http://fake:8080")

            call_kwargs = mock_client.get.call_args
            params = call_kwargs[1]["params"]
            assert params["format"] == "json"

    @pytest.mark.asyncio
    async def test_request_url_uses_search_endpoint(self):
        """search_web constructs the URL as <base_url>/search."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"results": []}

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            await search_web("anything", base_url="http://searxng-host:9090")

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert url == "http://searxng-host:9090/search"
