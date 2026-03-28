"""Tests for Qdrant client."""

from __future__ import annotations

import pytest

from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient


@pytest.fixture
def qdrant():
    return QdrantClient(url="http://localhost:6333", collection="test_collection")


class TestEnsureCollection:
    async def test_creates_collection_when_missing(self, qdrant, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection",
            method="GET", status_code=404,
        )
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection",
            method="PUT", status_code=200, json={"result": True},
        )
        await qdrant.ensure_collection(vector_size=768)

    async def test_skips_when_collection_exists(self, qdrant, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection",
            method="GET", status_code=200, json={"result": {}},
        )
        await qdrant.ensure_collection(vector_size=768)


class TestUpsertChunks:
    async def test_upserts_points(self, qdrant, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection/points",
            method="PUT", status_code=200, json={"result": {"status": "completed"}},
        )
        chunks = [{
            "content_hash": "abc123", "chunk_index": 0, "chunk_text": "hello world",
            "section_header": "# Title", "source_url": "vault://note.md", "title": "note.md",
        }]
        vectors = [[0.1] * 768]
        await qdrant.upsert_chunks(chunks, vectors)


class TestSearch:
    async def test_returns_results_with_scores(self, qdrant, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection/points/query",
            method="POST", status_code=200,
            json={"result": {"points": [{
                "score": 0.95,
                "payload": {"source_url": "vault://note.md", "chunk_text": "hello",
                            "section_header": "# Title", "title": "note.md"},
            }]}},
        )
        results = await qdrant.search(vector=[0.1] * 768, limit=5)
        assert len(results) == 1
        assert results[0]["score"] == 0.95
        assert results[0]["source_url"] == "vault://note.md"


class TestDeleteBySourceUrl:
    async def test_sends_filter_delete(self, qdrant, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection/points/delete",
            method="POST", status_code=200, json={"result": {"status": "completed"}},
        )
        await qdrant.delete_by_source_url("vault://old.md")


class TestGetIndexedSources:
    async def test_returns_source_hash_mapping(self, qdrant, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:6333/collections/test_collection/points/scroll",
            method="POST", status_code=200,
            json={"result": {
                "points": [
                    {"payload": {"source_url": "vault://a.md", "content_hash": "hash_a"}},
                    {"payload": {"source_url": "vault://a.md", "content_hash": "hash_a"}},
                    {"payload": {"source_url": "vault://b.md", "content_hash": "hash_b"}},
                ],
                "next_page_offset": None,
            }},
        )
        result = await qdrant.get_indexed_sources()
        assert result == {"vault://a.md": "hash_a", "vault://b.md": "hash_b"}
