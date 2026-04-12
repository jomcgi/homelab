"""Targeted tests for the three specific coverage gaps identified in vault_mcp.

Gaps addressed:
1. delete_note() git subprocess failure propagation — specifically the git commit
   step (after the file has been physically moved to _archive/).
2. _reconcile_loop() non-CancelledError recovery — verifying the error is logged
   before the loop continues.
3. Qdrant pagination with 100+ points per page — testing the continuation token
   logic when pages contain the maximum batch size (limit=100).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    configure,
    delete_note,
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
# Gap 1: delete_note() git commit failure after file is moved
# ---------------------------------------------------------------------------


class TestDeleteNoteGitCommitFailure:
    """Verify that git subprocess failures in delete_note() propagate correctly.

    delete_note() calls _git() directly (not _git_commit()) — there is no
    try/except around the git calls, so subprocess.CalledProcessError
    propagates up to the caller.

    These tests verify:
    - When git commit fails after file move, CalledProcessError propagates.
    - When the second git add (archive path) fails, CalledProcessError propagates.
    - When git fails, the exception is not swallowed.
    """

    async def test_git_commit_failure_propagates_after_file_move(self, tmp_path):
        """CalledProcessError from git commit propagates even after file was moved."""
        (tmp_path / "target.md").write_text("# Target")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )

        # Track which git subcommand was called
        calls: list[str] = []

        def git_side_effect(*args, **kwargs):
            calls.append(args[0])
            if args[0] == "commit":
                exc = subprocess.CalledProcessError(1, ["git", "commit"])
                exc.stderr = "nothing to commit"
                raise exc
            # add calls succeed (return a mock CompletedProcess)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(_mod, "_git", side_effect=git_side_effect):
            with pytest.raises(subprocess.CalledProcessError):
                await delete_note(path="target.md", reason="cleanup")

        # Verify that both add calls were made before the commit failed
        assert "add" in calls
        assert "commit" in calls

    async def test_git_add_archive_path_failure_propagates(self, tmp_path):
        """CalledProcessError from the second git add (archive path) propagates."""
        (tmp_path / "doc.md").write_text("# Doc")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )

        add_call_count = [0]

        def git_side_effect(*args, **kwargs):
            if args[0] == "add":
                add_call_count[0] += 1
                if add_call_count[0] == 2:
                    # Second add (for archive_rel path) fails
                    exc = subprocess.CalledProcessError(128, ["git", "add"])
                    exc.stderr = "fatal: pathspec not found"
                    raise exc
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(_mod, "_git", side_effect=git_side_effect):
            with pytest.raises(subprocess.CalledProcessError):
                await delete_note(path="doc.md", reason="archive it")

        # First add succeeded, second add failed
        assert add_call_count[0] == 2

    async def test_delete_note_git_failure_not_swallowed(self, tmp_path):
        """delete_note() does not swallow CalledProcessError — it must raise."""
        (tmp_path / "note.md").write_text("# Note")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )

        exc = subprocess.CalledProcessError(128, "git", stderr="git error")
        raised = False
        with patch.object(_mod, "_git", side_effect=exc):
            try:
                await delete_note(path="note.md", reason="cleanup")
            except subprocess.CalledProcessError:
                raised = True

        assert raised, "Expected CalledProcessError to propagate from delete_note()"


# ---------------------------------------------------------------------------
# Gap 2: _reconcile_loop() non-CancelledError recovery — error is logged
# ---------------------------------------------------------------------------


class TestReconcileLoopNonCancelledErrorLogging:
    """Verify that unexpected exceptions in the reconcile loop are logged.

    The loop has:
        except Exception:
            log.exception("Reconciler error")
        await asyncio.sleep(settings.reconcile_interval_seconds)

    This tests that the exception logging path is exercised: the logger is
    called with an appropriate message when a non-CancelledError exception occurs.
    """

    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    async def test_non_cancelled_error_is_logged(self, tmp_path, caplog):
        """An unexpected Exception from reconciler.run() is logged at ERROR level."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=1,
        )

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        call_count = [0]

        async def run_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("unexpected reconciler failure")
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_side_effect

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.ERROR),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # The exception should have been logged with "Reconciler error" message
        error_records = [r for r in caplog.records if "Reconciler error" in r.message]
        assert len(error_records) >= 1, (
            f"Expected 'Reconciler error' log message, got: {[r.message for r in caplog.records]}"
        )

    async def test_various_exception_types_are_caught_and_loop_continues(
        self, tmp_path
    ):
        """Different exception types (ValueError, IOError, RuntimeError) are all caught."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=1,
        )

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        exception_types = [
            ValueError("val error"),
            IOError("io error"),
            RuntimeError("rt error"),
        ]
        call_count = [0]

        async def run_side_effect():
            if call_count[0] < len(exception_types):
                exc = exception_types[call_count[0]]
                call_count[0] += 1
                raise exc
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_side_effect

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # All 3 exception types were caught (loop ran 4 times: 3 errors + 1 cancel)
        assert call_count[0] == len(exception_types), (
            f"Expected loop to run {len(exception_types)} times for errors, got {call_count[0]}"
        )

    async def test_exception_in_loop_does_not_reset_embedder_qdrant(self, tmp_path):
        """A runtime exception in the reconcile loop does NOT reset _embedder or _qdrant."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=1,
        )

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()

        call_count = [0]
        state_after_error = {}

        async def run_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("qdrant temporarily down")
            # On second run, capture global state before cancelling
            state_after_error["embedder"] = _mod._embedder
            state_after_error["qdrant"] = _mod._qdrant
            raise asyncio.CancelledError

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = run_side_effect

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # After the error, embedder and qdrant should still be set (not reset to None)
        assert state_after_error.get("embedder") is not None, (
            "_embedder should not be None after a reconcile loop exception"
        )
        assert state_after_error.get("qdrant") is not None, (
            "_qdrant should not be None after a reconcile loop exception"
        )


# ---------------------------------------------------------------------------
# Gap 3: Qdrant pagination with exactly 100 points per page
# ---------------------------------------------------------------------------


class TestQdrantPaginationMaxBatchSize:
    """Verify pagination continues correctly when pages contain exactly 100 points.

    The scroll API uses limit=100 per request. When a response returns exactly
    100 points AND next_page_offset is set, the client must continue fetching.
    This tests the boundary condition at the pagination limit.
    """

    def _make_points(self, count: int, page_num: int) -> list[dict]:
        """Generate `count` mock Qdrant points for page `page_num`."""
        return [
            {
                "payload": {
                    "source_url": f"vault://page{page_num}/note{i}.md",
                    "content_hash": f"hash-p{page_num}-{i}",
                }
            }
            for i in range(count)
        ]

    async def test_exactly_100_points_first_page_fetches_second(self):
        """When page 1 returns exactly 100 points with next_page_offset, page 2 is fetched."""
        page1_points = self._make_points(100, 1)
        page2_points = self._make_points(25, 2)

        pages = [
            _mock_response(
                200,
                {
                    "result": {
                        "points": page1_points,
                        "next_page_offset": "cursor-after-100",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": page2_points,
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

        # All 125 notes (100 + 25) should be in the result
        assert mock.post.call_count == 2
        assert len(result) == 125
        # Spot-check some entries
        assert "vault://page1/note0.md" in result
        assert "vault://page1/note99.md" in result
        assert "vault://page2/note0.md" in result
        assert "vault://page2/note24.md" in result

    async def test_two_full_pages_of_100_then_partial_third(self):
        """Two full pages (100 each) followed by a partial third page all get merged."""
        page1_points = self._make_points(100, 1)
        page2_points = self._make_points(100, 2)
        page3_points = self._make_points(50, 3)

        pages = [
            _mock_response(
                200,
                {
                    "result": {
                        "points": page1_points,
                        "next_page_offset": "cursor-1",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": page2_points,
                        "next_page_offset": "cursor-2",
                    }
                },
            ),
            _mock_response(
                200,
                {
                    "result": {
                        "points": page3_points,
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

        assert mock.post.call_count == 3
        assert len(result) == 250  # 100 + 100 + 50

    async def test_pagination_request_includes_limit_100(self):
        """Each scroll request must include limit=100 in the request body."""
        captured_bodies: list[dict] = []

        page1 = _mock_response(
            200,
            {
                "result": {
                    "points": self._make_points(10, 1),
                    "next_page_offset": "cursor-x",
                }
            },
        )
        page2 = _mock_response(
            200,
            {
                "result": {
                    "points": self._make_points(5, 2),
                    "next_page_offset": None,
                }
            },
        )

        responses = iter([page1, page2])

        async def post_capture(url, *, json):
            captured_bodies.append(json)
            return next(responses)

        mock = _mock_async_client()
        mock.post.side_effect = post_capture
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.get_indexed_sources()

        assert len(captured_bodies) == 2
        # Every request must use limit=100
        for i, body in enumerate(captured_bodies):
            assert body.get("limit") == 100, (
                f"Request {i + 1} should have limit=100, got {body.get('limit')}"
            )

    async def test_offset_correctly_passed_between_100_point_pages(self):
        """The continuation offset from each full page is passed in the next request."""
        page1 = _mock_response(
            200,
            {
                "result": {
                    "points": self._make_points(100, 1),
                    "next_page_offset": "offset-after-100",
                }
            },
        )
        page2 = _mock_response(
            200,
            {
                "result": {
                    "points": self._make_points(100, 2),
                    "next_page_offset": "offset-after-200",
                }
            },
        )
        page3 = _mock_response(
            200,
            {
                "result": {
                    "points": [],
                    "next_page_offset": None,
                }
            },
        )

        captured_bodies: list[dict] = []
        responses = iter([page1, page2, page3])

        async def post_capture(url, *, json):
            captured_bodies.append(json)
            return next(responses)

        mock = _mock_async_client()
        mock.post.side_effect = post_capture
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.get_indexed_sources()

        assert len(captured_bodies) == 3
        # First request has no offset
        assert "offset" not in captured_bodies[0]
        # Second request uses the offset from page 1
        assert captured_bodies[1]["offset"] == "offset-after-100"
        # Third request uses the offset from page 2
        assert captured_bodies[2]["offset"] == "offset-after-200"
