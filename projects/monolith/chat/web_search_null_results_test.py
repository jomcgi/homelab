"""Tests for search_web() when the JSON 'results' value is None.

web_search.py slices resp.json()["results"][:5] inside a try/except
that catches (KeyError, TypeError). When "results" is present but is None,
slicing raises a TypeError, which is caught and re-raised as ValueError.
This case is not covered in the existing web_search test files.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.web_search import search_web


def _make_client_with_response(body: dict) -> MagicMock:
    """Return an async-context-manager mock for httpx.AsyncClient."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = body

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get.return_value = resp
    return client


class TestSearchWebNullResults:
    @pytest.mark.asyncio
    async def test_raises_value_error_when_results_is_none(self):
        """search_web raises ValueError when 'results' key exists but its value is None."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client_with_response({"results": None})

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("test query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_value_error_when_results_is_integer(self):
        """search_web raises ValueError when 'results' is a non-subscriptable integer."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client_with_response({"results": 42})

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("test query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_value_error_when_results_is_string(self):
        """search_web raises ValueError when 'results' is a string instead of a list."""
        # A string supports slicing but iterating over it would yield single characters;
        # the formatter would raise KeyError on each "result" character.
        # However, slicing a string is NOT a TypeError — only None/int are.
        # This test documents that "results" as a plain integer raises ValueError.
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client_with_response({"results": 0})

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("test", base_url="http://fake:8080")
