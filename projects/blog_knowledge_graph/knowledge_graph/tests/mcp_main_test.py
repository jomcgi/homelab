"""Tests for MCP server."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import projects.blog_knowledge_graph.knowledge_graph.app.mcp_main as mcp_module
from projects.blog_knowledge_graph.knowledge_graph.app.mcp_main import app


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSearchKnowledgeEndpoint:
    """Tests for POST /tools/search_knowledge."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from httpx import ASGITransport, AsyncClient

        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(
            return_value=[
                {
                    "score": 0.95,
                    "title": "Test Article",
                    "source_url": "https://example.com",
                    "source_type": "html",
                    "section_header": "## Introduction",
                    "chunk_text": "Some content here.",
                    "content_hash": "abc123def456",
                    "chunk_index": 0,
                }
            ]
        )

        transport = ASGITransport(app=app)
        with (
            patch.object(mcp_module, "embedder", mock_embedder),
            patch.object(mcp_module, "qdrant", mock_qdrant),
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/tools/search_knowledge",
                    json={"query": "test query", "limit": 5},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["score"] == 0.95
        assert result["title"] == "Test Article"
        assert result["source_url"] == "https://example.com"
        assert result["source_type"] == "html"
        assert result["chunk_text"] == "Some content here."

    @pytest.mark.asyncio
    async def test_search_returns_empty_results(self):
        from httpx import ASGITransport, AsyncClient

        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1])
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        with (
            patch.object(mcp_module, "embedder", mock_embedder),
            patch.object(mcp_module, "qdrant", mock_qdrant),
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/tools/search_knowledge",
                    json={"query": "no results here"},
                )

        assert response.status_code == 200
        assert response.json()["results"] == []

    @pytest.mark.asyncio
    async def test_search_calls_embed_query_with_correct_text(self):
        from httpx import ASGITransport, AsyncClient

        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.5])
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        with (
            patch.object(mcp_module, "embedder", mock_embedder),
            patch.object(mcp_module, "qdrant", mock_qdrant),
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                await client.post(
                    "/tools/search_knowledge",
                    json={"query": "kubernetes deployment"},
                )

        mock_embedder.embed_query.assert_called_once_with("kubernetes deployment")

    @pytest.mark.asyncio
    async def test_search_passes_limit_to_qdrant(self):
        from httpx import ASGITransport, AsyncClient

        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1])
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        with (
            patch.object(mcp_module, "embedder", mock_embedder),
            patch.object(mcp_module, "qdrant", mock_qdrant),
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                await client.post(
                    "/tools/search_knowledge",
                    json={"query": "test", "limit": 10},
                )

        mock_qdrant.search.assert_called_once_with([0.1], limit=10)

    @pytest.mark.asyncio
    async def test_search_default_limit_is_5(self):
        from httpx import ASGITransport, AsyncClient

        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1])
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        with (
            patch.object(mcp_module, "embedder", mock_embedder),
            patch.object(mcp_module, "qdrant", mock_qdrant),
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                await client.post(
                    "/tools/search_knowledge",
                    json={"query": "test"},
                )

        mock_qdrant.search.assert_called_once_with([0.1], limit=5)

    @pytest.mark.asyncio
    async def test_search_result_has_all_fields(self):
        from httpx import ASGITransport, AsyncClient

        raw_result = {
            "score": 0.87,
            "title": "Bazel Tips",
            "source_url": "https://blog.example.com/bazel",
            "source_type": "rss",
            "section_header": "## Build Caching",
            "chunk_text": "Bazel caches build artifacts...",
            "content_hash": "deadbeef1234",
            "chunk_index": 2,
        }
        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1])
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[raw_result])

        transport = ASGITransport(app=app)
        with (
            patch.object(mcp_module, "embedder", mock_embedder),
            patch.object(mcp_module, "qdrant", mock_qdrant),
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/tools/search_knowledge",
                    json={"query": "bazel"},
                )

        result = response.json()["results"][0]
        assert result["score"] == 0.87
        assert result["section_header"] == "## Build Caching"
        assert result["chunk_index"] == 2
        assert result["content_hash"] == "deadbeef1234"


class TestGetSourceEndpoint:
    """Tests for POST /tools/get_source."""

    @pytest.mark.asyncio
    async def test_get_source_found(self):
        from httpx import ASGITransport, AsyncClient

        mock_storage = MagicMock()
        mock_storage.get_content.return_value = "# Hello\n\nFull article content."
        mock_storage.get_meta.return_value = {
            "title": "Hello World",
            "source_url": "https://example.com",
            "content_hash": "abc123",
        }

        transport = ASGITransport(app=app)
        with patch.object(mcp_module, "storage", mock_storage):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/tools/get_source",
                    params={"content_hash": "abc123"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "# Hello\n\nFull article content."
        assert data["meta"]["title"] == "Hello World"

    @pytest.mark.asyncio
    async def test_get_source_not_found(self):
        from httpx import ASGITransport, AsyncClient

        mock_storage = MagicMock()
        mock_storage.get_content.return_value = None
        mock_storage.get_meta.return_value = None

        transport = ASGITransport(app=app)
        with patch.object(mcp_module, "storage", mock_storage):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/tools/get_source",
                    params={"content_hash": "missing_hash"},
                )

        assert response.status_code == 200
        assert response.json()["error"] == "Not found"

    @pytest.mark.asyncio
    async def test_get_source_calls_storage_with_hash(self):
        from httpx import ASGITransport, AsyncClient

        mock_storage = MagicMock()
        mock_storage.get_content.return_value = "Some content."
        mock_storage.get_meta.return_value = {}

        transport = ASGITransport(app=app)
        with patch.object(mcp_module, "storage", mock_storage):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                await client.post(
                    "/tools/get_source",
                    params={"content_hash": "myhash123"},
                )

        mock_storage.get_content.assert_called_once_with("myhash123")
        mock_storage.get_meta.assert_called_once_with("myhash123")
