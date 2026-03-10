"""Tests for Qdrant client."""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from knowledge_graph.app.models import ChunkPayload
from knowledge_graph.app.qdrant_client import QdrantClient


@pytest.fixture
def qdrant():
    return QdrantClient(url="http://localhost:6333", collection="test_collection")


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_creates_collection_when_missing(self, qdrant):
        with patch("knowledge_graph.app.qdrant_client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            get_resp = MagicMock()
            get_resp.status_code = 404
            put_resp = MagicMock()
            put_resp.status_code = 200
            put_resp.raise_for_status = MagicMock()

            mock_client.get.return_value = get_resp
            mock_client.put.return_value = put_resp

            await qdrant.ensure_collection(vector_size=768)
            mock_client.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_exists(self, qdrant):
        with patch("knowledge_graph.app.qdrant_client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            get_resp = MagicMock()
            get_resp.status_code = 200
            mock_client.get.return_value = get_resp

            await qdrant.ensure_collection(vector_size=768)
            mock_client.put.assert_not_called()


class TestUpsertChunks:
    @pytest.mark.asyncio
    async def test_upserts_points(self, qdrant):
        with patch("knowledge_graph.app.qdrant_client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            put_resp = MagicMock()
            put_resp.raise_for_status = MagicMock()
            mock_client.put.return_value = put_resp

            chunks = [
                ChunkPayload(
                    content_hash="abc123",
                    chunk_index=0,
                    chunk_text="Some text",
                    section_header="# Title",
                    source_url="https://example.com",
                    source_type="html",
                    title="Test",
                    author=None,
                    published_at=None,
                ),
            ]
            vectors = [[0.1, 0.2, 0.3]]

            await qdrant.upsert_chunks(chunks, vectors)
            mock_client.put.assert_called_once()

            call_kwargs = mock_client.put.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            _ns = uuid.UUID("00000000-0000-0000-0000-000000000000")
            expected_id = str(uuid.uuid5(_ns, "abc123_0"))
            assert payload["points"][0]["id"] == expected_id


class TestSearch:
    @pytest.mark.asyncio
    async def test_returns_results(self, qdrant):
        with patch("knowledge_graph.app.qdrant_client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {
                "result": {
                    "points": [
                        {
                            "id": "abc_0",
                            "score": 0.95,
                            "payload": {
                                "title": "Test",
                                "chunk_text": "Content",
                                "source_url": "https://example.com",
                            },
                        }
                    ]
                }
            }
            mock_client.post.return_value = search_resp

            results = await qdrant.search([0.1, 0.2], limit=5)
            assert len(results) == 1
            assert results[0]["score"] == 0.95
            assert results[0]["title"] == "Test"


class TestHasContentHash:
    @pytest.mark.asyncio
    async def test_returns_true_when_exists(self, qdrant):
        with patch("knowledge_graph.app.qdrant_client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"result": {"points": [{"id": "abc_0"}]}}
            mock_client.post.return_value = resp

            assert await qdrant.has_content_hash("abc") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_missing(self, qdrant):
        with patch("knowledge_graph.app.qdrant_client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"result": {"points": []}}
            mock_client.post.return_value = resp

            assert await qdrant.has_content_hash("missing") is False
