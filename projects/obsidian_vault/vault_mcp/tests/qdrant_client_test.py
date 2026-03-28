"""Tests for Qdrant client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient


@pytest.fixture
def qdrant():
    return QdrantClient(url="http://localhost:6333", collection="test_collection")


def _mock_response(status_code: int = 200, json: dict | None = None) -> httpx.Response:
    """Build a fake httpx.Response."""
    return httpx.Response(status_code=status_code, json=json or {})


def _mock_async_client(**method_returns):
    """Build an AsyncMock that works as an async context manager."""
    mock = AsyncMock()
    for method, ret in method_returns.items():
        getattr(mock, method).return_value = ret
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


_PATCH_TARGET = "projects.obsidian_vault.vault_mcp.app.qdrant_client.httpx.AsyncClient"


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_creates_collection_when_missing(self, qdrant):
        mock = _mock_async_client(
            get=_mock_response(404),
            put=_mock_response(200, {"result": True}),
        )
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.ensure_collection(vector_size=768)
        mock.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_collection_exists(self, qdrant):
        mock = _mock_async_client(get=_mock_response(200, {"result": {}}))
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.ensure_collection(vector_size=768)
        mock.put.assert_not_called()


class TestUpsertChunks:
    @pytest.mark.asyncio
    async def test_upserts_points(self, qdrant):
        mock = _mock_async_client(
            put=_mock_response(200, {"result": {"status": "completed"}}),
        )
        chunks = [
            {
                "content_hash": "abc123",
                "chunk_index": 0,
                "chunk_text": "hello world",
                "section_header": "# Title",
                "source_url": "vault://note.md",
                "title": "note.md",
            }
        ]
        vectors = [[0.1] * 768]
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks(chunks, vectors)
        mock.put.assert_called_once()


class TestSearch:
    @pytest.mark.asyncio
    async def test_returns_results_with_scores(self, qdrant):
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "score": 0.95,
                                "payload": {
                                    "source_url": "vault://note.md",
                                    "chunk_text": "hello",
                                    "section_header": "# Title",
                                    "title": "note.md",
                                },
                            }
                        ]
                    },
                },
            ),
        )
        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768, limit=5)
        assert len(results) == 1
        assert results[0]["score"] == 0.95
        assert results[0]["source_url"] == "vault://note.md"


class TestDeleteBySourceUrl:
    @pytest.mark.asyncio
    async def test_sends_filter_delete(self, qdrant):
        mock = _mock_async_client(
            post=_mock_response(200, {"result": {"status": "completed"}}),
        )
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.delete_by_source_url("vault://old.md")
        mock.post.assert_called_once()


class TestGetIndexedSources:
    @pytest.mark.asyncio
    async def test_returns_source_hash_mapping(self, qdrant):
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "payload": {
                                    "source_url": "vault://a.md",
                                    "content_hash": "hash_a",
                                }
                            },
                            {
                                "payload": {
                                    "source_url": "vault://a.md",
                                    "content_hash": "hash_a",
                                }
                            },
                            {
                                "payload": {
                                    "source_url": "vault://b.md",
                                    "content_hash": "hash_b",
                                }
                            },
                        ],
                        "next_page_offset": None,
                    },
                },
            ),
        )
        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()
        assert result == {"vault://a.md": "hash_a", "vault://b.md": "hash_b"}
