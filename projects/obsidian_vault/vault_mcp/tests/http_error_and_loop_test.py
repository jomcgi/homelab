"""
Tests for coverage gaps in vault_mcp:

1. QdrantClient HTTP error paths:
   - upsert_chunks: 4xx/5xx response raises HTTPStatusError
   - search: 4xx/5xx response raises HTTPStatusError
   - get_indexed_sources: 4xx/5xx response raises HTTPStatusError

2. Multi-page pagination branch in get_indexed_sources:
   - Three pages (tests that more than two pages are handled correctly)
   - Offset from last page with data correctly stops the loop when None

3. Background _reconcile_loop exception-handler continuation:
   - reconciler.run() exception is caught, loop sleeps, then continues
   - Multiple consecutive reconciler errors do not terminate the loop
   - CancelledError in reconciler.run() propagates (is not caught by Exception handler)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import Settings
from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PATCH_TARGET = "projects.obsidian_vault.vault_mcp.app.qdrant_client.httpx.AsyncClient"


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
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
) -> dict:
    return {
        "content_hash": content_hash,
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
        "section_header": "# Title",
        "source_url": "vault://note.md",
        "title": "note.md",
    }


# ---------------------------------------------------------------------------
# 1a. upsert_chunks HTTP error paths
# ---------------------------------------------------------------------------


class TestUpsertChunksHttpErrors:
    """upsert_chunks raises HTTPStatusError on non-2xx responses."""

    @pytest.mark.asyncio
    async def test_upsert_chunks_500_raises(self):
        """A 500 response from the upsert endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            put=_mock_response(500, {"status": {"error": "internal error"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        chunk = _make_chunk()

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.upsert_chunks([chunk], [[0.1] * 768])

    @pytest.mark.asyncio
    async def test_upsert_chunks_400_raises(self):
        """A 400 Bad Request from the upsert endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            put=_mock_response(400, {"status": {"error": "bad request"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        chunk = _make_chunk()

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.upsert_chunks([chunk], [[0.1] * 768])

    @pytest.mark.asyncio
    async def test_upsert_chunks_503_raises(self):
        """A 503 Service Unavailable response raises HTTPStatusError."""
        mock = _mock_async_client(
            put=_mock_response(503, {"status": "unavailable"}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        chunk = _make_chunk()

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.upsert_chunks([chunk], [[0.1] * 768])

    @pytest.mark.asyncio
    async def test_upsert_chunks_422_raises(self):
        """A 422 Unprocessable Entity response raises HTTPStatusError."""
        mock = _mock_async_client(
            put=_mock_response(422, {"status": {"error": "validation failed"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        chunk = _make_chunk()

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.upsert_chunks([chunk], [[0.1] * 768])

    @pytest.mark.asyncio
    async def test_upsert_chunks_error_is_not_silently_swallowed(self):
        """upsert_chunks never silently swallows HTTP errors."""
        mock = _mock_async_client(
            put=_mock_response(502, {"status": "bad gateway"}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        chunk = _make_chunk()

        raised = False
        with patch(_PATCH_TARGET, return_value=mock):
            try:
                await qdrant.upsert_chunks([chunk], [[0.1] * 768])
            except httpx.HTTPStatusError:
                raised = True

        assert raised, "Expected HTTPStatusError to be raised on 502 response"

    @pytest.mark.asyncio
    async def test_upsert_chunks_200_does_not_raise(self):
        """A 200 OK response does not raise any exception."""
        mock = _mock_async_client(
            put=_mock_response(200, {"result": {"status": "completed"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        chunk = _make_chunk()

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks([chunk], [[0.1] * 768])  # Should not raise


# ---------------------------------------------------------------------------
# 1b. search HTTP error paths
# ---------------------------------------------------------------------------


class TestSearchHttpErrors:
    """search raises HTTPStatusError on non-2xx responses."""

    @pytest.mark.asyncio
    async def test_search_500_raises(self):
        """A 500 response from the search endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(500, {"status": {"error": "internal error"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.search(vector=[0.1] * 768)

    @pytest.mark.asyncio
    async def test_search_400_raises(self):
        """A 400 Bad Request from the search endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(400, {"status": {"error": "bad request"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.search(vector=[0.1] * 768)

    @pytest.mark.asyncio
    async def test_search_403_raises(self):
        """A 403 Forbidden from the search endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(403, {"status": "forbidden"}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.search(vector=[0.1] * 768)

    @pytest.mark.asyncio
    async def test_search_error_not_silently_swallowed(self):
        """search never silently swallows HTTP errors."""
        mock = _mock_async_client(
            post=_mock_response(503, {"status": "service unavailable"}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        raised = False
        with patch(_PATCH_TARGET, return_value=mock):
            try:
                await qdrant.search(vector=[0.1] * 768)
            except httpx.HTTPStatusError:
                raised = True

        assert raised, "Expected HTTPStatusError on 503 response"

    @pytest.mark.asyncio
    async def test_search_200_returns_results(self):
        """A 200 OK response returns parsed results (no error)."""
        points = [
            {
                "score": 0.9,
                "payload": {
                    "source_url": "vault://note.md",
                    "chunk_text": "hello",
                    "section_header": "# H",
                    "title": "note.md",
                    "content_hash": "abc",
                    "chunk_index": 0,
                },
            }
        ]
        mock = _mock_async_client(
            post=_mock_response(200, {"result": {"points": points}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)

        assert len(results) == 1
        assert results[0]["score"] == 0.9


# ---------------------------------------------------------------------------
# 1c. get_indexed_sources HTTP error paths
# ---------------------------------------------------------------------------


class TestGetIndexedSourcesHttpErrors:
    """get_indexed_sources raises HTTPStatusError on non-2xx responses."""

    @pytest.mark.asyncio
    async def test_get_indexed_sources_500_raises(self):
        """A 500 response from the scroll endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(500, {"status": {"error": "internal error"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.get_indexed_sources()

    @pytest.mark.asyncio
    async def test_get_indexed_sources_400_raises(self):
        """A 400 Bad Request from the scroll endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(400, {"status": {"error": "bad request"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.get_indexed_sources()

    @pytest.mark.asyncio
    async def test_get_indexed_sources_error_not_silently_swallowed(self):
        """get_indexed_sources never silently swallows HTTP errors."""
        mock = _mock_async_client(
            post=_mock_response(503, {"status": "service unavailable"}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        raised = False
        with patch(_PATCH_TARGET, return_value=mock):
            try:
                await qdrant.get_indexed_sources()
            except httpx.HTTPStatusError:
                raised = True

        assert raised, "Expected HTTPStatusError on 503 response"

    @pytest.mark.asyncio
    async def test_get_indexed_sources_error_on_second_page_raises(self):
        """An error on the second page scroll raises HTTPStatusError."""
        page1 = _mock_response(
            200,
            {
                "result": {
                    "points": [
                        {
                            "payload": {
                                "source_url": "vault://a.md",
                                "content_hash": "h1",
                            }
                        }
                    ],
                    "next_page_offset": "cursor-123",
                }
            },
        )
        page2_error = _mock_response(500, {"status": {"error": "timeout"}})

        mock = _mock_async_client()
        mock.post.side_effect = [page1, page2_error]
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.get_indexed_sources()


# ---------------------------------------------------------------------------
# 2. Multi-page pagination (more than two pages)
# ---------------------------------------------------------------------------


class TestGetIndexedSourcesMultiPagePagination:
    """get_indexed_sources follows next_page_offset for more than two pages."""

    @pytest.mark.asyncio
    async def test_three_pages_all_fetched(self):
        """get_indexed_sources fetches all three pages and merges results."""
        pages = [
            _mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "payload": {
                                    "source_url": "vault://page1.md",
                                    "content_hash": "h1",
                                }
                            }
                        ],
                        "next_page_offset": "cursor-1",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "payload": {
                                    "source_url": "vault://page2.md",
                                    "content_hash": "h2",
                                }
                            }
                        ],
                        "next_page_offset": "cursor-2",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "payload": {
                                    "source_url": "vault://page3.md",
                                    "content_hash": "h3",
                                }
                            }
                        ],
                        "next_page_offset": None,
                    }
                },
            ),
        ]

        mock = _mock_async_client()
        mock.post.side_effect = pages
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert "vault://page1.md" in result
        assert "vault://page2.md" in result
        assert "vault://page3.md" in result
        assert result["vault://page1.md"] == "h1"
        assert result["vault://page2.md"] == "h2"
        assert result["vault://page3.md"] == "h3"
        assert mock.post.call_count == 3

    @pytest.mark.asyncio
    async def test_three_pages_correct_offsets_sent(self):
        """Each subsequent page request includes the correct offset from the previous response."""
        pages = [
            _mock_response(
                200,
                {
                    "result": {
                        "points": [],
                        "next_page_offset": "cursor-first",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": [],
                        "next_page_offset": "cursor-second",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": [],
                        "next_page_offset": None,
                    }
                },
            ),
        ]

        captured_bodies: list[dict] = []
        response_iter = iter(pages)

        async def post_side_effect(url, *, json):
            captured_bodies.append(json)
            return next(response_iter)

        mock = _mock_async_client()
        mock.post.side_effect = post_side_effect
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.get_indexed_sources()

        assert len(captured_bodies) == 3
        # First request has no offset
        assert "offset" not in captured_bodies[0]
        # Second request uses cursor-first
        assert captured_bodies[1]["offset"] == "cursor-first"
        # Third request uses cursor-second
        assert captured_bodies[2]["offset"] == "cursor-second"

    @pytest.mark.asyncio
    async def test_pagination_stops_immediately_when_no_offset(self):
        """A response with next_page_offset=None stops the loop after one page."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "payload": {
                                    "source_url": "vault://only.md",
                                    "content_hash": "ho",
                                }
                            }
                        ],
                        "next_page_offset": None,
                    }
                },
            )
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert mock.post.call_count == 1
        assert result == {"vault://only.md": "ho"}

    @pytest.mark.asyncio
    async def test_four_pages_all_results_merged(self):
        """Results from four pages are all merged into the final dict."""
        pages = []
        for i in range(1, 5):
            next_offset = f"cursor-{i}" if i < 4 else None
            pages.append(
                _mock_response(
                    200,
                    {
                        "result": {
                            "points": [
                                {
                                    "payload": {
                                        "source_url": f"vault://page{i}.md",
                                        "content_hash": f"hash{i}",
                                    }
                                }
                            ],
                            "next_page_offset": next_offset,
                        }
                    },
                )
            )

        response_iter = iter(pages)

        async def post_side_effect(url, *, json):
            return next(response_iter)

        mock = _mock_async_client()
        mock.post.side_effect = post_side_effect
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert mock.post.call_count == 4
        for i in range(1, 5):
            assert f"vault://page{i}.md" in result
            assert result[f"vault://page{i}.md"] == f"hash{i}"


# ---------------------------------------------------------------------------
# 3. _reconcile_loop exception-handler continuation
# ---------------------------------------------------------------------------


class TestReconcileLoopExceptionContinuation:
    """The reconcile loop continues after reconciler.run() raises an Exception."""

    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    @pytest.mark.asyncio
    async def test_reconciler_exception_does_not_terminate_loop(self, tmp_path):
        """An Exception from reconciler.run() is caught; the loop sleeps and continues."""
        settings = Settings(
            path=str(tmp_path),
            reconcile_interval_seconds=1,
        )

        run_count = [0]
        sleep_count = [0]

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        # reconciler.run() fails twice, then succeeds, then we cancel
        async def run_side_effect():
            run_count[0] += 1
            if run_count[0] <= 2:
                raise RuntimeError(f"reconciler error #{run_count[0]}")
            raise asyncio.CancelledError  # stop after third call

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_side_effect

        async def fake_sleep(delay):
            sleep_count[0] += 1

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # reconciler.run() should have been called 3 times (2 errors + 1 cancel)
        assert run_count[0] == 3, (
            f"Expected 3 run() calls (2 errors + 1 cancel), got {run_count[0]}"
        )

    @pytest.mark.asyncio
    async def test_sleep_called_after_each_reconciler_exception(self, tmp_path):
        """asyncio.sleep is called after each Exception from reconciler.run()."""
        settings = Settings(
            path=str(tmp_path),
            reconcile_interval_seconds=42,
        )

        run_count = [0]
        sleep_delays: list[float] = []

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        async def run_side_effect():
            run_count[0] += 1
            if run_count[0] <= 2:
                raise ValueError(f"transient error #{run_count[0]}")
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_side_effect

        async def fake_sleep(delay):
            sleep_delays.append(delay)

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # Two errors → two sleeps (one after each error); the CancelledError propagates
        assert len(sleep_delays) == 2, (
            f"Expected 2 sleep calls (one per exception), got {sleep_delays}"
        )
        # Sleep duration matches reconcile_interval_seconds
        assert all(d == 42 for d in sleep_delays), (
            f"Expected all sleeps to be 42s (reconcile_interval), got {sleep_delays}"
        )

    @pytest.mark.asyncio
    async def test_cancelled_error_from_reconciler_propagates(self, tmp_path):
        """CancelledError from reconciler.run() is NOT caught by the Exception handler."""
        settings = Settings(
            path=str(tmp_path),
            reconcile_interval_seconds=1,
        )

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        async def run_raises_cancelled():
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_raises_cancelled

        async def fake_sleep(delay):
            pass

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

    @pytest.mark.asyncio
    async def test_loop_continues_after_multiple_consecutive_errors(self, tmp_path):
        """The loop handles many consecutive exceptions without terminating."""
        settings = Settings(
            path=str(tmp_path),
            reconcile_interval_seconds=1,
        )

        run_count = [0]

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        async def run_many_errors():
            run_count[0] += 1
            if run_count[0] < 5:
                raise ConnectionError(f"Qdrant unreachable (attempt {run_count[0]})")
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_many_errors

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        assert run_count[0] == 5, (
            f"Expected 5 run() calls (4 errors + 1 cancel), got {run_count[0]}"
        )

    @pytest.mark.asyncio
    async def test_reconciler_exception_does_not_reset_embedder_or_qdrant(
        self, tmp_path
    ):
        """An Exception from reconciler.run() does NOT reset _embedder or _qdrant.

        Only the init-phase exception handler (while _embedder is None) resets these.
        The reconcile loop's exception handler only logs and sleeps.
        """
        settings = Settings(
            path=str(tmp_path),
            reconcile_interval_seconds=1,
        )

        run_count = [0]

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        embedder_after_error = []
        qdrant_after_error = []

        async def run_and_check():
            run_count[0] += 1
            if run_count[0] == 1:
                raise RuntimeError("first run failed")
            # After the exception handler, capture the global state
            embedder_after_error.append(_mod._embedder)
            qdrant_after_error.append(_mod._qdrant)
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_and_check

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # _embedder and _qdrant should NOT have been reset to None after the exception
        assert len(embedder_after_error) >= 1
        assert embedder_after_error[0] is not None, (
            "_embedder should not be reset to None after a reconciler error"
        )
        assert len(qdrant_after_error) >= 1
        assert qdrant_after_error[0] is not None, (
            "_qdrant should not be reset to None after a reconciler error"
        )
