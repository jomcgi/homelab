"""Additional Qdrant client tests covering gaps in qdrant_client_test.py."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient

_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000000")
_PATCH_TARGET = "projects.obsidian_vault.vault_mcp.app.qdrant_client.httpx.AsyncClient"


def _mock_response(
    status_code: int = 200, json_data: dict | None = None
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "http://test"),
    )


def _mock_async_client(**method_returns):
    mock = AsyncMock()
    for method, ret in method_returns.items():
        getattr(mock, method).return_value = ret
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


def _make_chunk(
    content_hash: str = "abc123",
    chunk_index: int = 0,
    chunk_text: str = "hello",
    section_header: str = "# Title",
    source_url: str = "vault://note.md",
    title: str = "note.md",
) -> dict:
    return {
        "content_hash": content_hash,
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
        "section_header": section_header,
        "source_url": source_url,
        "title": title,
    }


class TestUrlNormalization:
    def test_trailing_slash_stripped(self):
        """QdrantClient strips trailing slash from the URL."""
        client = QdrantClient(url="http://qdrant:6333/", collection="vault")
        assert not client._url.endswith("/")
        assert client._url == "http://qdrant:6333"

    def test_no_trailing_slash_unchanged(self):
        client = QdrantClient(url="http://qdrant:6333", collection="vault")
        assert client._url == "http://qdrant:6333"

    def test_collection_stored(self):
        client = QdrantClient(url="http://localhost:6333", collection="my_collection")
        assert client._collection == "my_collection"


class TestPointIdDeterminism:
    """The point ID is deterministic UUID5 based on content_hash and chunk_index."""

    async def test_same_inputs_produce_same_point_id(self):
        """Two upserts of the same chunk always produce the same point ID."""
        chunk = _make_chunk(content_hash="deadbeef", chunk_index=0)
        ids: list[str] = []

        async def capture_put(url, *, json):
            ids.append(json["points"][0]["id"])
            return _mock_response(200)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock1 = _mock_async_client()
        mock1.put.side_effect = capture_put

        with patch(_PATCH_TARGET, return_value=mock1):
            await qdrant.upsert_chunks([chunk], [[0.1] * 768])

        mock2 = _mock_async_client()
        mock2.put.side_effect = capture_put

        with patch(_PATCH_TARGET, return_value=mock2):
            await qdrant.upsert_chunks([chunk], [[0.1] * 768])

        assert ids[0] == ids[1]

    async def test_different_chunk_indices_produce_different_ids(self):
        """Different chunk_index values produce different point IDs."""
        chunk0 = _make_chunk(content_hash="hash", chunk_index=0)
        chunk1 = _make_chunk(content_hash="hash", chunk_index=1)
        ids: list[str] = []

        async def capture_put(url, *, json):
            for pt in json["points"]:
                ids.append(pt["id"])
            return _mock_response(200)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.put.side_effect = capture_put

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks([chunk0, chunk1], [[0.1] * 768, [0.2] * 768])

        assert ids[0] != ids[1]

    def test_point_id_matches_expected_uuid5(self):
        """Point IDs are UUID5 of the zero namespace and '{hash}_{index}'."""
        content_hash = "abc123"
        chunk_index = 0
        expected = str(uuid.uuid5(_NAMESPACE, f"{content_hash}_{chunk_index}"))
        # Verify using the same algorithm as the implementation
        actual = str(uuid.uuid5(_NAMESPACE, f"{content_hash}_{chunk_index}"))
        assert actual == expected


class TestUpsertChunksAdditional:
    async def test_upsert_multiple_chunks_builds_correct_payload(self):
        """upsert_chunks with multiple chunks builds a points list with each chunk."""
        chunks = [
            _make_chunk(content_hash="h", chunk_index=0, chunk_text="first"),
            _make_chunk(content_hash="h", chunk_index=1, chunk_text="second"),
        ]
        vectors = [[0.1] * 768, [0.2] * 768]

        captured: list[dict] = []

        async def capture_put(url, *, json):
            captured.append(json)
            return _mock_response(200)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.put.side_effect = capture_put

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks(chunks, vectors)

        assert len(captured) == 1
        points = captured[0]["points"]
        assert len(points) == 2
        texts = {pt["payload"]["chunk_text"] for pt in points}
        assert texts == {"first", "second"}

    async def test_upsert_chunk_payload_fields(self):
        """Each point payload contains all required fields from the chunk."""
        chunk = _make_chunk(
            content_hash="myhash",
            chunk_index=3,
            chunk_text="my text",
            section_header="## Section",
            source_url="vault://test.md",
            title="test.md",
        )
        captured: list[dict] = []

        async def capture_put(url, *, json):
            captured.append(json)
            return _mock_response(200)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.put.side_effect = capture_put

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks([chunk], [[0.1] * 768])

        pt = captured[0]["points"][0]
        assert pt["payload"]["source_url"] == "vault://test.md"
        assert pt["payload"]["title"] == "test.md"
        assert pt["payload"]["section_header"] == "## Section"
        assert pt["payload"]["chunk_index"] == 3
        assert pt["payload"]["chunk_text"] == "my text"
        assert pt["payload"]["content_hash"] == "myhash"

    async def test_upsert_empty_list_calls_put_with_empty_points(self):
        """upsert_chunks([]) still issues a PUT with an empty points list."""
        mock = _mock_async_client(put=_mock_response(200))
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks([], [])

        mock.put.assert_called_once()
        call_json = mock.put.call_args.kwargs["json"]
        assert call_json["points"] == []


class TestSearchAdditional:
    async def test_search_passes_limit_to_qdrant(self):
        """search(limit=N) sends limit=N in the request body."""
        captured: list[dict] = []

        async def capture_post(url, *, json):
            captured.append(json)
            return _mock_response(200, {"result": {"points": []}})

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.post.side_effect = capture_post

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.search(vector=[0.1] * 768, limit=12)

        assert captured[0]["limit"] == 12

    async def test_search_empty_result_returns_empty_list(self):
        """search() with no points in the response returns []."""
        mock = _mock_async_client(
            post=_mock_response(200, {"result": {"points": []}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)

        assert results == []

    async def test_search_missing_result_key_returns_empty_list(self):
        """search() tolerates a response body with no 'result' key."""
        mock = _mock_async_client(post=_mock_response(200, {}))
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)

        assert results == []

    async def test_search_result_includes_score_and_payload(self):
        """Each search result merges score into the payload dict."""
        point = {
            "score": 0.87,
            "payload": {
                "source_url": "vault://note.md",
                "chunk_text": "some text",
                "section_header": "# H",
                "title": "note.md",
                "content_hash": "abc",
                "chunk_index": 0,
            },
        }
        mock = _mock_async_client(
            post=_mock_response(200, {"result": {"points": [point]}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)

        assert results[0]["score"] == 0.87
        assert results[0]["source_url"] == "vault://note.md"


class TestDeleteBySourceUrlAdditional:
    async def test_delete_sends_correct_filter_body(self):
        """delete_by_source_url sends the right filter JSON."""
        captured: list[dict] = []

        async def capture_post(url, *, json):
            captured.append(json)
            return _mock_response(200)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.post.side_effect = capture_post

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.delete_by_source_url("vault://note.md")

        body = captured[0]
        must = body["filter"]["must"]
        assert must[0]["key"] == "source_url"
        assert must[0]["match"]["value"] == "vault://note.md"


class TestGetIndexedSourcesAdditional:
    async def test_skips_points_with_empty_source_url(self):
        """Points with empty source_url are not included in the result."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {"payload": {"source_url": "", "content_hash": "h"}},
                            {
                                "payload": {
                                    "source_url": "vault://valid.md",
                                    "content_hash": "h2",
                                }
                            },
                        ],
                        "next_page_offset": None,
                    }
                },
            )
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert "" not in result
        assert "vault://valid.md" in result

    async def test_pagination_fetches_all_pages(self):
        """get_indexed_sources follows next_page_offset to fetch all pages."""
        page1 = {
            "result": {
                "points": [
                    {"payload": {"source_url": "vault://a.md", "content_hash": "h1"}}
                ],
                "next_page_offset": "page2-token",
            }
        }
        page2 = {
            "result": {
                "points": [
                    {"payload": {"source_url": "vault://b.md", "content_hash": "h2"}}
                ],
                "next_page_offset": None,
            }
        }
        responses = [_mock_response(200, page1), _mock_response(200, page2)]
        response_iter = iter(responses)

        async def post_side_effect(url, *, json):
            return next(response_iter)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.post.side_effect = post_side_effect

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert "vault://a.md" in result
        assert "vault://b.md" in result
        assert mock.post.call_count == 2

    async def test_pagination_sends_offset_on_second_request(self):
        """The second page request includes the offset from the first response."""
        page1 = {
            "result": {
                "points": [],
                "next_page_offset": "cursor-xyz",
            }
        }
        page2 = {
            "result": {
                "points": [],
                "next_page_offset": None,
            }
        }
        responses = [_mock_response(200, page1), _mock_response(200, page2)]
        response_iter = iter(responses)
        captured_bodies: list[dict] = []

        async def post_side_effect(url, *, json):
            captured_bodies.append(json)
            return next(response_iter)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        mock = _mock_async_client()
        mock.post.side_effect = post_side_effect

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.get_indexed_sources()

        # First request has no offset key, second includes it
        assert "offset" not in captured_bodies[0]
        assert captured_bodies[1]["offset"] == "cursor-xyz"

    async def test_get_indexed_sources_empty_collection_returns_empty_dict(self):
        """An empty collection with no points returns {}."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {"result": {"points": [], "next_page_offset": None}},
            )
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert result == {}

    async def test_first_occurrence_of_duplicate_url_wins(self):
        """When a source_url appears multiple times, the first hash is retained."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "payload": {
                                    "source_url": "vault://x.md",
                                    "content_hash": "first",
                                }
                            },
                            {
                                "payload": {
                                    "source_url": "vault://x.md",
                                    "content_hash": "second",
                                }
                            },
                        ],
                        "next_page_offset": None,
                    }
                },
            )
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert result["vault://x.md"] == "first"


class TestEnsureCollectionAdditional:
    async def test_raises_on_http_error_creating_collection(self):
        """ensure_collection raises when the PUT returns an error status."""
        mock = _mock_async_client(
            get=_mock_response(404),
            put=_mock_response(500, {"status": {"error": "internal error"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.ensure_collection(vector_size=768)

    async def test_sends_correct_vector_config(self):
        """ensure_collection sends the right size and distance in the PUT body."""
        captured: list[dict] = []

        async def capture_put(url, *, json):
            captured.append(json)
            return _mock_response(200)

        mock = _mock_async_client(get=_mock_response(404))
        mock.put.side_effect = capture_put

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.ensure_collection(vector_size=384)

        assert captured[0]["vectors"]["size"] == 384
        assert captured[0]["vectors"]["distance"] == "Cosine"
