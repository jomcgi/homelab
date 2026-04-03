"""Tests for SearXNG web search client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.web_search import search_web


class TestSearchWeb:
    @pytest.mark.asyncio
    async def test_returns_formatted_results(self):
        """search_web returns formatted string of top results."""
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "results": [
                {
                    "title": "Result 1",
                    "content": "First result content",
                    "url": "http://example.com/1",
                },
                {
                    "title": "Result 2",
                    "content": "Second result content",
                    "url": "http://example.com/2",
                },
            ]
        }

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("test query", base_url="http://fake:8080")

        assert "Result 1" in result
        assert "First result content" in result
        assert "Result 2" in result

    @pytest.mark.asyncio
    async def test_limits_to_5_results(self):
        """search_web returns at most 5 results."""
        fake_results = [
            {"title": f"R{i}", "content": f"C{i}", "url": f"http://example.com/{i}"}
            for i in range(10)
        ]
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"results": fake_results}

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("test", base_url="http://fake:8080")

        # Should only contain 5 results
        assert result.count("http://example.com/") == 5
