"""Tests for specific untested code paths in vault_mcp."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.chunker import (
    _split_paragraphs,
    chunk_markdown,
)
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    _git_commit,
    configure,
    edit_note,
    read_note,
    write_note,
)
from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient


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
# chunker._split_paragraphs — word-level split residual path
# ---------------------------------------------------------------------------


class TestSplitParagraphsWordSplitResidue:
    def test_oversized_para_residue_appended_to_current(self):
        """After an oversized paragraph's words flush, leftover words go into current[]
        (not a separate chunk immediately) — they are part of the next flush.
        """
        # max_tokens=5 → a 12-word paragraph splits; trailing words land in current
        long_para = "a b c d e f g h i j k l"
        result = _split_paragraphs(long_para, max_tokens=5)
        # Ensure all words are present in the combined output
        combined = " ".join(result)
        for word in long_para.split():
            assert word in combined

    def test_oversized_para_final_buf_flushed_into_current(self):
        """The tail of a word-split paragraph (in buf) is added to current[], not lost."""
        # A paragraph of 20 words with max_tokens=8 will split into multiple word-chunks.
        # The final partial buf goes to current, and since no more paragraphs follow,
        # current is flushed into chunks at the end.
        para = " ".join(["word"] * 20)
        result = _split_paragraphs(para, max_tokens=8)
        total_words = sum(len(chunk.split()) for chunk in result)
        assert total_words == 20

    def test_code_block_after_oversized_para_starts_new_chunk(self):
        """A code block following an oversized paragraph is a separate paragraph unit."""
        long_text = " ".join(["word"] * 30)
        text = f"{long_text}\n\n```python\ncode here\n```"
        result = _split_paragraphs(text, max_tokens=10)
        combined = " ".join(result)
        assert "code here" in combined


# ---------------------------------------------------------------------------
# chunker — indented/nested code fence not treated as code block boundary
# ---------------------------------------------------------------------------


class TestSplitParagraphsIndentedFence:
    def test_indented_code_fence_not_treated_as_fence_boundary(self):
        """A line with leading spaces before ``` is NOT a code block delimiter
        (startswith checks for the exact ``` prefix without leading whitespace).
        """
        text = "Normal line.\n\n    ```python\n    code\n    ```\n\nAfter."
        result = _split_paragraphs(text, max_tokens=512)
        # The indented fences are not treated as code block delimiters —
        # they are plain text lines.
        combined = " ".join(result)
        assert "Normal line." in combined
        assert "After." in combined


# ---------------------------------------------------------------------------
# qdrant_client — missing top-level 'result' key in search response
# ---------------------------------------------------------------------------

_PATCH_TARGET = "projects.obsidian_vault.vault_mcp.app.qdrant_client.httpx.AsyncClient"


def _mock_response(status_code: int = 200, json_data: dict | None = None):
    import httpx

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


class TestQdrantSearchMissingPoints:
    async def test_search_result_missing_points_key_returns_empty(self):
        """search() handles result dict that has no 'points' key."""
        mock = _mock_async_client(
            post=_mock_response(200, {"result": {}}),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)
        assert results == []

    async def test_search_point_missing_score_defaults_to_zero(self):
        """A point with no 'score' key gets score=0 in the result."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {"payload": {"source_url": "vault://x.md", "chunk_text": "t"}}
                        ]
                    }
                },
            ),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)
        assert results[0]["score"] == 0

    async def test_search_point_missing_payload_returns_score_only(self):
        """A point with no 'payload' key returns just the score."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {"result": {"points": [{"score": 0.5}]}},
            ),
        )
        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            results = await qdrant.search(vector=[0.1] * 768)
        assert results[0]["score"] == 0.5


# ---------------------------------------------------------------------------
# qdrant_client — get_indexed_sources: missing payload keys
# ---------------------------------------------------------------------------


class TestGetIndexedSourcesMissingKeys:
    async def test_point_with_missing_payload_key_skipped(self):
        """A point whose payload has no source_url or content_hash is skipped."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {"payload": {}},  # no source_url, no content_hash
                            {
                                "payload": {
                                    "source_url": "vault://ok.md",
                                    "content_hash": "h",
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
        assert list(result.keys()) == ["vault://ok.md"]

    async def test_point_with_no_payload_key_skipped(self):
        """A point with no 'payload' key at all is gracefully skipped."""
        mock = _mock_async_client(
            post=_mock_response(
                200,
                {
                    "result": {
                        "points": [
                            {},  # no payload key
                            {
                                "payload": {
                                    "source_url": "vault://note.md",
                                    "content_hash": "abc",
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
        assert result == {"vault://note.md": "abc"}


# ---------------------------------------------------------------------------
# main — _git_commit with empty file list
# ---------------------------------------------------------------------------


class TestGitCommitEmptyFileList:
    def test_empty_file_list_only_calls_commit(self):
        """_git_commit([]) skips git add calls and only commits."""
        with patch.object(_mod, "_git") as mock_git:
            _git_commit([], "empty commit")
        add_calls = [c for c in mock_git.call_args_list if c.args[0] == "add"]
        assert add_calls == []
        commit_calls = [c for c in mock_git.call_args_list if c.args[0] == "commit"]
        assert len(commit_calls) == 1

    def test_commit_message_in_git_call(self):
        """The commit message is passed verbatim to git commit."""
        with patch.object(_mod, "_git") as mock_git:
            _git_commit([], "my commit message")
        commit_call = [c for c in mock_git.call_args_list if c.args[0] == "commit"][0]
        assert "my commit message" in commit_call.args


# ---------------------------------------------------------------------------
# main — write_note and edit_note validation order
# ---------------------------------------------------------------------------


class TestWriteNoteValidationOrder:
    async def test_absolute_path_returns_error_not_exception(self, tmp_path):
        """write_note with an absolute path returns error dict (not raises)."""
        result = await write_note(path="/etc/passwd", content="bad", reason="test")
        assert "error" in result
        assert "Invalid path" in result["error"]

    async def test_reason_checked_before_path(self, tmp_path):
        """Empty reason is rejected before path validation."""
        # Even with a traversal path, empty reason triggers the reason error first
        result = await write_note(path="../escape.md", content="bad", reason="")
        assert result == {"error": "reason is required"}


class TestEditNoteValidationOrder:
    async def test_reason_checked_before_path(self, tmp_path):
        """Empty reason is rejected before path validation in edit_note."""
        result = await edit_note(
            path="../escape.md", old_text="a", new_text="b", reason=""
        )
        assert result == {"error": "reason is required"}

    async def test_reason_checked_before_file_exists(self, tmp_path):
        """Empty reason is rejected before checking if the file exists."""
        result = await edit_note(
            path="nonexistent.md", old_text="a", new_text="b", reason=""
        )
        assert result == {"error": "reason is required"}


# ---------------------------------------------------------------------------
# main — read_note error message format
# ---------------------------------------------------------------------------


class TestReadNoteErrorMessages:
    async def test_invalid_path_error_includes_path(self, tmp_path):
        """read_note error for invalid path includes the offending path string."""
        result = await read_note(path="/etc/passwd")
        assert result["error"] == "Invalid path: /etc/passwd"

    async def test_not_found_error_includes_path(self, tmp_path):
        """read_note error for missing file includes the path."""
        result = await read_note(path="missing.md")
        assert result["error"] == "Note not found: missing.md"


# ---------------------------------------------------------------------------
# main — _reconcile_loop: cache dir doesn't exist on init failure
# ---------------------------------------------------------------------------


class TestReconcileLoopNoCacheDir:
    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    async def test_no_rmtree_when_cache_dir_missing(self, tmp_path):
        """If the cache dir doesn't exist on init failure, shutil.rmtree is NOT called."""
        nonexistent_cache = tmp_path / "does_not_exist"
        assert not nonexistent_cache.exists()

        settings = Settings(
            path=str(tmp_path),
            embed_cache_dir=str(nonexistent_cache),
            reconcile_interval_seconds=1,
        )

        call_count = 0

        def failing_then_succeeding(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("download failed")
            mock = MagicMock()
            mock.dimension = 768
            return mock

        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        with (
            patch.object(_mod, "VaultEmbedder", side_effect=failing_then_succeeding),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # rmtree should NOT be called since the cache dir doesn't exist
        mock_rmtree.assert_not_called()


# ---------------------------------------------------------------------------
# main — chunk_markdown empty result skips embed/upsert in reconciler context
# ---------------------------------------------------------------------------


class TestChunkMarkdownEmptyContent:
    def test_whitespace_only_returns_empty(self):
        """chunk_markdown with purely whitespace returns []."""
        result = chunk_markdown(
            content="\n\n\t   \n",
            content_hash="h",
            source_url="vault://empty.md",
            title="empty.md",
        )
        assert result == []

    def test_only_header_no_body_returns_one_chunk(self):
        """A header with no body text after it still produces content."""
        # The header line itself is captured as the body of that section
        # when there's content between it and the next section/EOF
        content = "# Just a Title\n\nSome body."
        result = chunk_markdown(
            content=content,
            content_hash="h",
            source_url="vault://title.md",
            title="title.md",
        )
        assert len(result) >= 1
        assert result[0]["section_header"] == "# Just a Title"


# ---------------------------------------------------------------------------
# reconciler — gc.collect is invoked during embed loop
# ---------------------------------------------------------------------------


class TestReconcilerGcCollect:
    async def test_gc_collect_called_after_each_embed(self, tmp_path):
        """gc.collect() is called once for each file embedded."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from projects.obsidian_vault.vault_mcp.app.reconciler import VaultReconciler

        (tmp_path / "a.md").write_text("# A\n\nContent.")
        (tmp_path / "b.md").write_text("# B\n\nContent.")

        mock_qdrant = AsyncMock()
        mock_qdrant.get_indexed_sources.return_value = {}
        mock_qdrant.upsert_chunks = AsyncMock()
        mock_qdrant.delete_by_source_url = AsyncMock()

        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = lambda texts: [[0.1] * 768] * len(texts)

        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )

        with patch("projects.obsidian_vault.vault_mcp.app.reconciler.gc.collect") as mock_gc:
            await reconciler.run()

        # gc.collect() should be called once per embedded file (2 files)
        assert mock_gc.call_count == 2
