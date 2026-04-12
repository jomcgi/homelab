"""Tests covering identified coverage gaps in vault_mcp.

Gaps addressed:
1. _reconcile_loop() lifespan shutdown — background task cancellation on app shutdown.
2. search_semantic() partial init — _qdrant set but _embedder is None returns error.
3. QdrantClient HTTP error paths:
   - Non-200/404 on GET in ensure_collection raises on subsequent PUT (5xx).
   - Error response (5xx) on DELETE filter in delete_by_source_url raises.
"""

from __future__ import annotations

import asyncio
import subprocess
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    configure,
    search_semantic,
)
from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _configure_vault(tmp_path):
    """Configure vault to use a temporary directory for each test."""
    configure(Settings(path=str(tmp_path)))


@pytest.fixture(autouse=True)
def _init_git(tmp_path):
    """Initialize a git repo in the tmp vault so commits work."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Helpers for Qdrant HTTP mocking
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Gap 1: _reconcile_loop() lifespan — background task lifecycle verified
# ---------------------------------------------------------------------------


class TestReconcileLoopLifespanTask:
    """Verify the background task lifecycle during lifespan startup and shutdown.

    The lifespan closure in main() creates an asyncio task for _reconcile_loop
    and registers a done callback to remove it from _background_tasks.
    These tests verify:
    - The task is added to _background_tasks on lifespan entry.
    - The done callback removes it when the task finishes.
    - Cancelling the task raises CancelledError.

    IMPORTANT: The lifespan closure captures _reconcile_loop by name from the
    module namespace (late binding). The patch on _mod._reconcile_loop must
    remain active while the lifespan context is entered and the task is running.
    Therefore all async assertions run *inside* the patch context.
    """

    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        _mod._background_tasks.clear()
        yield
        _mod._embedder = None
        _mod._qdrant = None
        _mod._background_tasks.clear()

    async def test_task_added_to_background_tasks_on_startup(self, tmp_path):
        """main() registers the reconcile task in _background_tasks during lifespan entry."""
        started = asyncio.Event()

        async def blocking_reconcile(settings):
            started.set()
            # Block until cancelled
            await asyncio.sleep(9999)

        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = str(tmp_path)
        mock_settings.port = 8000

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mock_app = MagicMock()
        mock_app.router = MagicMock()
        mock_app.router.lifespan_context = noop_lifespan

        task_count_during_run = []

        # The patch must be active while the lifespan (and thus the task) runs
        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=blocking_reconcile),
        ):
            _mod.main()
            lifespan = mock_app.router.lifespan_context

            async def run_lifespan():
                async with lifespan(mock_app):
                    await asyncio.wait_for(started.wait(), timeout=2.0)
                    # While inside the lifespan context, the task should be registered
                    task_count_during_run.append(len(_mod._background_tasks))
                    # Cancel the task so we can exit cleanly
                    for t in list(_mod._background_tasks):
                        t.cancel()
                        try:
                            await asyncio.shield(t)
                        except (asyncio.CancelledError, Exception):
                            pass

            await run_lifespan()

        assert task_count_during_run[0] == 1, (
            f"Expected 1 task in _background_tasks, got {task_count_during_run[0]}"
        )

    async def test_done_callback_removes_task_from_set(self, tmp_path):
        """The done callback registered by main() removes the task from _background_tasks."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = str(tmp_path)
        mock_settings.port = 8000

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mock_app = MagicMock()
        mock_app.router = MagicMock()
        mock_app.router.lifespan_context = noop_lifespan

        async def instant_reconcile(settings):
            # Returns immediately — task finishes quickly
            return

        task_count_after_done = []

        # The patch must be active while the lifespan runs and the task completes
        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=instant_reconcile),
        ):
            _mod.main()
            lifespan = mock_app.router.lifespan_context

            async def run_and_check():
                async with lifespan(mock_app):
                    # Wait for the task to complete and the done callback to fire
                    await asyncio.sleep(0.1)
                    task_count_after_done.append(len(_mod._background_tasks))

            await run_and_check()

        assert task_count_after_done[0] == 0, (
            f"Expected 0 tasks after reconcile finished, "
            f"got {task_count_after_done[0]}"
        )

    async def test_task_cancelled_on_shutdown_propagates_cancelled_error(
        self, tmp_path
    ):
        """When the reconcile task is cancelled, CancelledError propagates correctly."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = str(tmp_path)
        mock_settings.port = 8000

        started = asyncio.Event()
        cancel_errors_caught = []

        async def long_running_reconcile(settings):
            started.set()
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                cancel_errors_caught.append(True)
                raise

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mock_app = MagicMock()
        mock_app.router = MagicMock()
        mock_app.router.lifespan_context = noop_lifespan

        # The patch must be active while the lifespan runs and the task is cancelled
        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=long_running_reconcile),
        ):
            _mod.main()
            lifespan = mock_app.router.lifespan_context

            async def run_and_cancel():
                async with lifespan(mock_app):
                    await asyncio.wait_for(started.wait(), timeout=2.0)
                    # Simulate shutdown: cancel the background task
                    for t in list(_mod._background_tasks):
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass  # expected
                        except Exception:
                            pass

            await run_and_cancel()

        assert len(cancel_errors_caught) == 1, (
            "Expected the reconcile task to catch CancelledError when cancelled"
        )


# ---------------------------------------------------------------------------
# Gap 2: search_semantic() partial init — _qdrant set, _embedder is None
# ---------------------------------------------------------------------------


class TestSearchSemanticPartialInit:
    """Verify search_semantic() handles partial initialisation gracefully."""

    async def test_returns_error_when_qdrant_set_but_embedder_none(self, tmp_path):
        """search_semantic returns error dict when _qdrant is set but _embedder is None.

        The condition `if _embedder is None or _qdrant is None` should catch
        the case where _qdrant is populated but _embedder is not.
        Without this guard, _embedder.embed_query() would raise AttributeError.
        """
        mock_qdrant = AsyncMock()

        with (
            patch.object(_mod, "_qdrant", mock_qdrant),
            patch.object(_mod, "_embedder", None),
        ):
            result = await search_semantic(query="some query")

        assert "error" in result
        assert result["error"] == "Semantic search not configured"
        # qdrant.search must NOT have been called
        mock_qdrant.search.assert_not_called()

    async def test_returns_error_when_embedder_set_but_qdrant_none(self, tmp_path):
        """search_semantic returns error dict when _embedder is set but _qdrant is None."""
        mock_embedder = MagicMock()

        with (
            patch.object(_mod, "_embedder", mock_embedder),
            patch.object(_mod, "_qdrant", None),
        ):
            result = await search_semantic(query="some query")

        assert "error" in result
        assert result["error"] == "Semantic search not configured"
        # embed_query must NOT have been called
        mock_embedder.embed_query.assert_not_called()

    async def test_no_attribute_error_when_qdrant_set_embedder_none(self, tmp_path):
        """Calling search_semantic with _qdrant set and _embedder=None must not raise.

        If the guard `if _embedder is None or _qdrant is None` were absent,
        calling `_embedder.embed_query(query)` on None would raise AttributeError.
        """
        mock_qdrant = AsyncMock()

        with (
            patch.object(_mod, "_qdrant", mock_qdrant),
            patch.object(_mod, "_embedder", None),
        ):
            # Must not raise AttributeError
            try:
                result = await search_semantic(query="test")
            except AttributeError as exc:
                pytest.fail(
                    f"search_semantic raised AttributeError with partial init: {exc}"
                )

        assert "error" in result


# ---------------------------------------------------------------------------
# Gap 3: QdrantClient HTTP error paths
# ---------------------------------------------------------------------------


class TestEnsureCollectionHttpErrorPaths:
    """Non-200/404 on GET in ensure_collection should trigger PUT; 5xx on PUT raises."""

    async def test_get_returns_500_then_put_500_raises_http_status_error(self):
        """A 500 GET + 500 PUT causes raise_for_status to propagate HTTPStatusError.

        When GET returns non-200, the implementation falls through to PUT.
        If PUT also returns an error status, raise_for_status raises.
        """
        mock = _mock_async_client(
            get=_mock_response(500, {"status": "error"}),
            put=_mock_response(500, {"status": {"error": "internal server error"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.ensure_collection(vector_size=768)

        # PUT was called because GET did not return 200
        mock.put.assert_called_once()

    async def test_get_returns_500_put_succeeds_no_error(self):
        """When GET returns 500 and PUT succeeds (200), no error is raised.

        The implementation treats any non-200 GET response as 'collection absent'
        and attempts to create it via PUT. If PUT returns 200, the method succeeds.
        """
        mock = _mock_async_client(
            get=_mock_response(500, {"status": "error"}),
            put=_mock_response(200, {"result": True}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            # Should not raise — GET 500 falls through to PUT, which succeeds
            await qdrant.ensure_collection(vector_size=768)

        mock.put.assert_called_once()

    async def test_get_returns_403_triggers_put(self):
        """A 403 on GET causes ensure_collection to attempt PUT (non-200, non-skip path)."""
        mock = _mock_async_client(
            get=_mock_response(403, {"status": "forbidden"}),
            put=_mock_response(200, {"result": True}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.ensure_collection(vector_size=768)

        mock.put.assert_called_once()


class TestDeleteBySourceUrlHttpErrorPaths:
    """Error responses on delete_by_source_url should propagate via raise_for_status."""

    async def test_delete_500_raises_http_status_error(self):
        """A 500 response from the delete endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(500, {"status": {"error": "internal server error"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.delete_by_source_url("vault://note.md")

    async def test_delete_400_raises_http_status_error(self):
        """A 400 Bad Request from the delete endpoint raises HTTPStatusError."""
        mock = _mock_async_client(
            post=_mock_response(400, {"status": {"error": "bad request"}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            with pytest.raises(httpx.HTTPStatusError):
                await qdrant.delete_by_source_url("vault://note.md")

    async def test_delete_error_does_not_swallow_exception(self):
        """delete_by_source_url never silently swallows HTTP errors."""
        mock = _mock_async_client(
            post=_mock_response(503, {"status": "unavailable"}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        raised = False
        with patch(_PATCH_TARGET, return_value=mock):
            try:
                await qdrant.delete_by_source_url("vault://some.md")
            except httpx.HTTPStatusError:
                raised = True

        assert raised, "Expected HTTPStatusError to be raised on 503 response"
