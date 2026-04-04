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


# ---------------------------------------------------------------------------
# Malformed JSON response (200 OK but resp.json() raises)
# ---------------------------------------------------------------------------


class TestSearchWebMalformedJson:
    @pytest.mark.asyncio
    async def test_raises_on_malformed_json_response(self):
        """search_web propagates ValueError when the response body is not valid JSON."""
        import json

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        # json() raises when body cannot be decoded
        fake_response.json.side_effect = json.JSONDecodeError(
            "Expecting value", doc="not json", pos=0
        )

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(
                Exception
            ):  # json.JSONDecodeError is a subclass of ValueError
                await search_web("query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_on_missing_results_key(self):
        """search_web raises ValueError when the JSON body has no 'results' key."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "error": "backend unavailable"
        }  # no 'results'

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_returns_formatted_string_with_null_fields(self):
        """search_web handles result dicts with None values by formatting them as 'None'."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "results": [{"title": None, "content": None, "url": None}]
        }

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("query", base_url="http://fake:8080")

        # None fields are stringified; the function should not raise
        assert "None" in result

    @pytest.mark.asyncio
    async def test_results_with_partial_null_fields_formatted(self):
        """search_web includes all fields even when only some are None."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "results": [
                {"title": "Real Title", "content": None, "url": "http://ex.com"}
            ]
        }

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("query", base_url="http://fake:8080")

        assert "Real Title" in result
        assert "http://ex.com" in result
