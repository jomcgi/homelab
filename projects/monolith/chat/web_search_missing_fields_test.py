"""Tests for search_web() when individual result objects have missing fields.

The existing coverage (web_search_coverage_test.py) already covers the case
where the 'title' key is absent.  These tests extend coverage to the 'content'
and 'url' keys, which are equally required by the formatting expression:

    f"**{r['title']}**\\n{r['content']}\\nURL: {r['url']}"
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.web_search import search_web


def _mock_client_returning(json_data: dict):
    """Return a patched httpx.AsyncClient that yields a specific JSON response."""
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = json_data
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get.return_value = fake_response
    return mock_client


class TestSearchWebMissingResultFields:
    @pytest.mark.asyncio
    async def test_raises_key_error_on_missing_content_field(self):
        """search_web raises KeyError when a result is missing the 'content' field."""
        mock_client = _mock_client_returning(
            {"results": [{"title": "T", "url": "http://ex.com"}]}
        )

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(KeyError):
                await search_web("test", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_key_error_on_missing_url_field(self):
        """search_web raises KeyError when a result is missing the 'url' field."""
        mock_client = _mock_client_returning(
            {"results": [{"title": "T", "content": "C"}]}
        )

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(KeyError):
                await search_web("test", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_missing_top_level_results_key(self):
        """search_web raises ValueError when the top-level 'results' key is absent."""
        mock_client = _mock_client_returning({"data": []})

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("test", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_raises_value_error_when_response_is_not_a_dict(self):
        """search_web raises ValueError when the JSON response is not a dict."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = ["not", "a", "dict"]
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = fake_response

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(ValueError, match="unexpected search response shape"):
                await search_web("test", base_url="http://fake:8080")

    @pytest.mark.asyncio
    async def test_succeeds_with_all_fields_present(self):
        """search_web returns formatted text when all required fields are present."""
        mock_client = _mock_client_returning(
            {
                "results": [
                    {
                        "title": "MyTitle",
                        "content": "MyContent",
                        "url": "http://example.com",
                    }
                ]
            }
        )

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            result = await search_web("test", base_url="http://fake:8080")

        assert "MyTitle" in result
        assert "MyContent" in result
        assert "http://example.com" in result
