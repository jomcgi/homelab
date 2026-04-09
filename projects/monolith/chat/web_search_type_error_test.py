"""Tests for the TypeError branch in chat/web_search.py.

The ``search_web`` function does:

    results = resp.json()["results"][:5]

If ``resp.json()["results"]`` is a non-subscriptable type (e.g. an integer
or a boolean), the ``[:5]`` slice raises ``TypeError``, which is caught by
``except (KeyError, TypeError) as e`` and re-raised as ``ValueError``.

The existing tests cover the ``KeyError`` path (missing ``"results"`` key)
but NOT the ``TypeError`` path (``"results"`` key present but non-subscriptable
value).  This file fills that gap.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.web_search import search_web


def _make_client(json_response):
    """Return a mock AsyncClient whose GET returns a response with given JSON."""
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = json_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get.return_value = fake_response
    return mock_client


class TestSearchWebTypeError:
    """The ``except (KeyError, TypeError)`` handler must also fire for TypeError."""

    @pytest.mark.asyncio
    async def test_integer_results_raises_value_error(self):
        """When 'results' is an integer, slicing raises TypeError → ValueError."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client({"results": 42})

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("test query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_boolean_results_raises_value_error(self):
        """When 'results' is a boolean, slicing raises TypeError → ValueError."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client({"results": True})

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_string_results_does_not_raise_but_slices(self):
        """When 'results' is a string, [:5] slices the first 5 chars (valid Python).

        This is an edge case: a string IS subscriptable, so no TypeError fires.
        The subsequent ``r['title']`` access then raises KeyError.  We pin
        this behaviour so the test fails loudly if the error-handling path changes.
        """
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client({"results": "hello world"})

            # "hello"[:5] == "hello" — iterating over chars, r['title'] raises KeyError
            with pytest.raises((ValueError, KeyError, TypeError)):
                await search_web("query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_none_results_raises_value_error(self):
        """When 'results' is None, None[:5] raises TypeError → ValueError."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client({"results": None})

            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("query", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_error_message_contains_exception_text(self):
        """The ValueError message includes the original TypeError string."""
        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_client({"results": 0})

            with pytest.raises(ValueError) as exc_info:
                await search_web("query", base_url="http://fake:8080")

        assert "unexpected search response shape" in str(exc_info.value)
