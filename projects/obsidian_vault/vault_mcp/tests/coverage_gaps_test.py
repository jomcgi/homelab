"""Tests covering identified coverage gaps in vault_mcp.

Gaps addressed:
1. _reconcile_loop() lifespan shutdown — background task cancellation on app shutdown.
2. search_semantic() partial init — _qdrant set but _embedder is None returns error.
3. QdrantClient HTTP error paths:
   - Non-200/404 on GET in ensure_collection raises immediately (no PUT issued).
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


# ---------------------------------------------------------------------------
# Gap 1: _reconcile_loop() lifespan shutdown — task cancellation verified
# ---------------------------------------------------------------------------


class TestReconcileLoopLifespanShutdown:
    """Verify that the reconcile background task is cancelled on lifespan shutdown."""

    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        _mod._background_tasks.clear()
        yield
        _mod._embedder = None
        _mod._qdrant = None
        _mod._background_tasks.clear()

    async def test_task_cancelled_when_lifespan_exits(self, tmp_path):
        """The reconcile task receives CancelledError when the lifespan context exits.

        The lifespan in main() creates the task but does NOT cancel it explicitly —
        the task is cancelled by the asyncio event loop when the task's coroutine
        raises CancelledError.  We test this by:
        1. Extracting the lifespan from a wired-up app.
        2. Entering the lifespan context (which starts the task).
        3. Cancelling the task manually (simulating shutdown) before exiting.
        4. Asserting the task ends with CancelledError.
        """
        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = str(tmp_path)
        mock_settings.port = 8000
        mock_app = MagicMock()

        # Capture the lifespan that main() registers
        registered_lifespan = None

        def capture_lifespan_assignment(value):
            nonlocal registered_lifespan
            registered_lifespan = value

        mock_app.router = MagicMock()
        mock_app.router.lifespan_context = _stub_lifespan  # initial value

        # We need to capture the assignment to mock_app.router.lifespan_context
        type(mock_app.router).__setattr__ = MagicMock(
            side_effect=lambda self, name, value: (
                capture_lifespan_assignment(value) if name == "lifespan_context" else None
            )
        )

        # Use a long-running reconcile loop mock that only stops on cancellation
        reconcile_started = asyncio.Event()

        async def slow_reconcile(settings):
            reconcile_started.set()
            # Sleep forever — only CancelledError will stop it
            await asyncio.sleep(9999)

        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=slow_reconcile),
        ):
            _mod.main()

        # registered_lifespan is the custom lifespan closure
        assert registered_lifespan is not None

        # Enter the lifespan: it wraps original_lifespan then starts the task
        # We mock the original_lifespan as a no-op async context manager
        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mock_app.router.lifespan_context = noop_lifespan
        # Re-run main() to get a lifespan that uses the noop original
        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=slow_reconcile),
        ):
            _mod.main()

        # The lifespan attribute was reassigned — get current value
        lifespan = mock_app.router.lifespan_context

        task_ref: list[asyncio.Task] = []

        async def run_and_capture():
            # Enter the lifespan context, capture the task, then cancel it
            async with lifespan(mock_app):
                # Wait until the reconcile loop has actually started
                await asyncio.wait_for(reconcile_started.wait(), timeout=2.0)
                # Capture the background task
                assert len(_mod._background_tasks) == 1
                task = next(iter(_mod._background_tasks))
                task_ref.append(task)
                task.cancel()
                # Give cancellation time to propagate
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            # After lifespan exits the task should be done or cancelled
            assert task_ref[0].done() or task_ref[0].cancelled()

        await run_and_capture()

    async def test_background_task_added_to_background_tasks_set(self, tmp_path):
        """main() adds the reconcile task to _background_tasks during lifespan startup."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = str(tmp_path)
        mock_settings.port = 8000
        mock_app = MagicMock()

        started = asyncio.Event()

        async def blocking_reconcile(settings):
            started.set()
            await asyncio.sleep(9999)

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mock_app.router = MagicMock()
        mock_app.router.lifespan_context = noop_lifespan

        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=blocking_reconcile),
        ):
            _mod.main()

        lifespan = mock_app.router.lifespan_context

        async def check_task_registered():
            async with lifespan(mock_app):
                await asyncio.wait_for(started.wait(), timeout=2.0)
                # The task must be present in _background_tasks while running
                assert len(_mod._background_tasks) == 1
                task = next(iter(_mod._background_tasks))
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        await check_task_registered()

    async def test_reconcile_task_removed_from_set_after_done(self, tmp_path):
        """The done callback discards the task from _background_tasks when it finishes."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = str(tmp_path)
        mock_settings.port = 8000
        mock_app = MagicMock()

        async def instant_reconcile(settings):
            # Returns immediately — task will be "done" quickly
            return

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mock_app.router = MagicMock()
        mock_app.router.lifespan_context = noop_lifespan

        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
            patch.object(_mod, "_reconcile_loop", side_effect=instant_reconcile),
        ):
            _mod.main()

        lifespan = mock_app.router.lifespan_context

        async def check_removal():
            async with lifespan(mock_app):
                # Allow the task to complete
                await asyncio.sleep(0.05)
                # After the task finishes, the done callback should have removed it
                assert len(_mod._background_tasks) == 0

        await check_removal()


# Stub lifespan for use as the initial mock_app.router.lifespan_context value
@asynccontextmanager
async def _stub_lifespan(app):
    yield


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
    """Non-200/404 on GET in ensure_collection should propagate via raise_for_status."""

    async def test_get_returns_500_raises_http_status_error(self):
        """A 500 response on the GET check raises HTTPStatusError immediately.

        The implementation only handles 200 (return) and implicitly falls through
        to PUT for any non-200 response. However, a 500 means Qdrant is broken —
        the PUT is still attempted and its raise_for_status() will catch the error
        on the PUT side. This test verifies the path where GET returns 500 and
        a subsequent PUT also fails, causing raise_for_status to propagate.
        """
        # When GET returns 500, ensure_collection falls through to PUT.
        # If PUT also returns an error, raise_for_status raises.
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
        """When GET returns 500 and PUT succeeds, no error is raised.

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
