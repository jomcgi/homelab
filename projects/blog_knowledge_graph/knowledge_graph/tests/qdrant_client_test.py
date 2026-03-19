"""Tests for Qdrant client."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.models import ChunkPayload
from projects.blog_knowledge_graph.knowledge_graph.app.qdrant_client import QdrantClient

_QDRANT_PATH = (
    "projects.blog_knowledge_graph.knowledge_graph.app.qdrant_client.httpx.AsyncClient"
)


@pytest.fixture
def qdrant():
    return QdrantClient(url="http://localhost:6333", collection="test_collection")


class TestQdrantClientInit:
    def test_strips_trailing_slash_from_url(self):
        client = QdrantClient(url="http://localhost:6333/", collection="col")
        assert not client._url.endswith("/")
        assert client._url == "http://localhost:6333"

    def test_preserves_url_without_trailing_slash(self):
        client = QdrantClient(url="http://localhost:6333", collection="col")
        assert client._url == "http://localhost:6333"

    def test_stores_collection_name(self):
        client = QdrantClient(url="http://qdrant:6333", collection="my_collection")
        assert client._collection == "my_collection"


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_creates_collection_when_missing(self, qdrant):
        with patch(_QDRANT_PATH) as mock_cls:
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
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            get_resp = MagicMock()
            get_resp.status_code = 200
            mock_client.get.return_value = get_resp

            await qdrant.ensure_collection(vector_size=768)
            mock_client.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_collection_with_cosine_distance(self, qdrant):
        """Collection is created with Cosine distance metric."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            get_resp = MagicMock()
            get_resp.status_code = 404
            put_resp = MagicMock()
            put_resp.raise_for_status = MagicMock()
            mock_client.get.return_value = get_resp
            mock_client.put.return_value = put_resp

            await qdrant.ensure_collection(vector_size=1536)

        call_kwargs = mock_client.put.call_args.kwargs
        payload = call_kwargs.get("json") or mock_client.put.call_args[1].get("json")
        assert payload["vectors"]["distance"] == "Cosine"
        assert payload["vectors"]["size"] == 1536


class TestUpsertChunks:
    @pytest.mark.asyncio
    async def test_upserts_points(self, qdrant):
        with patch(_QDRANT_PATH) as mock_cls:
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

    @pytest.mark.asyncio
    async def test_upserts_multiple_chunks_with_deterministic_ids(self, qdrant):
        """Multiple chunks get deterministic UUID5 IDs based on hash+index."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            put_resp = MagicMock()
            put_resp.raise_for_status = MagicMock()
            mock_client.put.return_value = put_resp

            chunks = [
                ChunkPayload(
                    content_hash="myhash",
                    chunk_index=i,
                    chunk_text=f"chunk {i}",
                    section_header="## Section",
                    source_url="https://example.com",
                    source_type="html",
                    title="Title",
                    author=None,
                    published_at=None,
                )
                for i in range(3)
            ]
            vectors = [[float(i)] * 3 for i in range(3)]

            await qdrant.upsert_chunks(chunks, vectors)

        call_kwargs = mock_client.put.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        points = payload["points"]
        assert len(points) == 3

        _ns = uuid.UUID("00000000-0000-0000-0000-000000000000")
        for i, point in enumerate(points):
            expected_id = str(uuid.uuid5(_ns, f"myhash_{i}"))
            assert point["id"] == expected_id

    @pytest.mark.asyncio
    async def test_upsert_chunk_payload_contains_all_fields(self, qdrant):
        """Each upserted point contains all required payload fields."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            put_resp = MagicMock()
            put_resp.raise_for_status = MagicMock()
            mock_client.put.return_value = put_resp

            chunk = ChunkPayload(
                content_hash="deadbeef",
                chunk_index=2,
                chunk_text="The chunk text.",
                section_header="## Overview",
                source_url="https://blog.example.com/post",
                source_type="rss",
                title="Blog Post",
                author="Author Name",
                published_at="2025-01-15T00:00:00",
            )
            await qdrant.upsert_chunks([chunk], [[0.5, 0.6]])

        payload = mock_client.put.call_args.kwargs.get("json") or mock_client.put.call_args[1].get("json")
        point_payload = payload["points"][0]["payload"]
        assert point_payload["source_type"] == "rss"
        assert point_payload["source_url"] == "https://blog.example.com/post"
        assert point_payload["title"] == "Blog Post"
        assert point_payload["author"] == "Author Name"
        assert point_payload["section_header"] == "## Overview"
        assert point_payload["chunk_index"] == 2
        assert point_payload["chunk_text"] == "The chunk text."
        assert point_payload["content_hash"] == "deadbeef"

    @pytest.mark.asyncio
    async def test_upsert_empty_chunks_sends_empty_points(self, qdrant):
        """Upsert with empty lists sends a PUT with empty points array."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            put_resp = MagicMock()
            put_resp.raise_for_status = MagicMock()
            mock_client.put.return_value = put_resp

            await qdrant.upsert_chunks([], [])

        payload = mock_client.put.call_args.kwargs.get("json") or mock_client.put.call_args[1].get("json")
        assert payload["points"] == []


class TestSearch:
    @pytest.mark.asyncio
    async def test_returns_results(self, qdrant):
        with patch(_QDRANT_PATH) as mock_cls:
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

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(self, qdrant):
        """search() returns [] when Qdrant returns empty points."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {"result": {"points": []}}
            mock_client.post.return_value = search_resp

            results = await qdrant.search([0.1, 0.2], limit=5)
            assert results == []

    @pytest.mark.asyncio
    async def test_search_passes_limit_to_api(self, qdrant):
        """search() sends the limit parameter to Qdrant."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {"result": {"points": []}}
            mock_client.post.return_value = search_resp

            await qdrant.search([0.5], limit=10)

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_json["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_includes_payload_in_request(self, qdrant):
        """search() requests with_payload=True."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {"result": {"points": []}}
            mock_client.post.return_value = search_resp

            await qdrant.search([0.5])

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_json["with_payload"] is True

    @pytest.mark.asyncio
    async def test_search_result_includes_score_from_point(self, qdrant):
        """Result dict merges score with payload fields."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {
                "result": {
                    "points": [
                        {
                            "score": 0.87,
                            "payload": {"title": "Article", "chunk_index": 3},
                        }
                    ]
                }
            }
            mock_client.post.return_value = search_resp

            results = await qdrant.search([0.1])

        assert results[0]["score"] == 0.87
        assert results[0]["title"] == "Article"
        assert results[0]["chunk_index"] == 3


class TestHasContentHash:
    @pytest.mark.asyncio
    async def test_returns_true_when_exists(self, qdrant):
        with patch(_QDRANT_PATH) as mock_cls:
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
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"result": {"points": []}}
            mock_client.post.return_value = resp

            assert await qdrant.has_content_hash("missing") is False

    @pytest.mark.asyncio
    async def test_scroll_filter_uses_content_hash(self, qdrant):
        """has_content_hash sends the hash value in a scroll filter."""
        with patch(_QDRANT_PATH) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"result": {"points": []}}
            mock_client.post.return_value = resp

            await qdrant.has_content_hash("targethash")

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        must_clause = call_json["filter"]["must"][0]
        assert must_clause["key"] == "content_hash"
        assert must_clause["match"]["value"] == "targethash"
