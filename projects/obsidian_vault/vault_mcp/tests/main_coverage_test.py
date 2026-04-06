"""Coverage gap tests for Obsidian Vault MCP server — main.py."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    _validate_path,
    configure,
    delete_note,
    get_history,
    search_semantic,
)


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
# _validate_path — direct function tests
# ---------------------------------------------------------------------------


class TestValidatePath:
    def test_returns_path_for_valid_relative_path(self, tmp_path):
        """A simple relative filename resolves to a Path inside the vault."""
        result = _validate_path("note.md")
        assert result is not None
        assert isinstance(result, Path)
        assert str(result).startswith(str(tmp_path))

    def test_returns_path_for_nested_valid_path(self, tmp_path):
        """A nested relative path is also accepted."""
        result = _validate_path("daily/2026-01-01.md")
        assert result is not None
        assert str(result) == str(tmp_path / "daily" / "2026-01-01.md")

    def test_returns_none_for_absolute_path(self, tmp_path):
        """Absolute paths are always rejected."""
        assert _validate_path("/etc/passwd") is None

    def test_returns_none_for_path_traversal(self, tmp_path):
        """Path traversal sequences are rejected after resolution."""
        assert _validate_path("../../etc/shadow") is None

    def test_returns_none_for_single_dotdot(self, tmp_path):
        """A single `..` escaping the vault is rejected."""
        assert _validate_path("../escape.md") is None


# ---------------------------------------------------------------------------
# Settings — additional fields
# ---------------------------------------------------------------------------


class TestSettingsAdditional:
    def test_embed_cache_dir_default(self):
        """embed_cache_dir defaults to /vault/.cache/fastembed."""
        s = Settings()
        assert s.embed_cache_dir == "/vault/.cache/fastembed"

    def test_embed_cache_dir_custom(self):
        s = Settings(embed_cache_dir="/tmp/mymodel")
        assert s.embed_cache_dir == "/tmp/mymodel"

    def test_embed_model_env_override(self, monkeypatch):
        monkeypatch.setenv(
            "VAULT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        s = Settings()
        assert s.embed_model == "sentence-transformers/all-MiniLM-L6-v2"

    def test_qdrant_collection_env_override(self, monkeypatch):
        monkeypatch.setenv("VAULT_QDRANT_COLLECTION", "my_collection")
        s = Settings()
        assert s.qdrant_collection == "my_collection"

    def test_reconcile_interval_env_override(self, monkeypatch):
        monkeypatch.setenv("VAULT_RECONCILE_INTERVAL_SECONDS", "60")
        s = Settings()
        assert s.reconcile_interval_seconds == 60


# ---------------------------------------------------------------------------
# search_semantic — edge cases not covered by main_test.py
# ---------------------------------------------------------------------------


class TestSearchSemanticEdgeCases:
    async def test_result_without_source_url_passes_through_unchanged(self, tmp_path):
        """Results lacking source_url are returned as-is (no KeyError)."""
        mock_qdrant = AsyncMock()
        mock_qdrant.search.return_value = [{"score": 0.8, "chunk_text": "some text"}]
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.0] * 768

        with (
            patch.object(_mod, "_qdrant", mock_qdrant),
            patch.object(_mod, "_embedder", mock_embedder),
        ):
            result = await search_semantic(query="test")

        assert len(result["results"]) == 1
        assert "path" not in result["results"][0]
        assert result["results"][0]["score"] == 0.8

    async def test_source_url_without_vault_prefix_kept_unchanged(self, tmp_path):
        """source_url that doesn't start with vault:// is kept as path unchanged."""
        mock_qdrant = AsyncMock()
        mock_qdrant.search.return_value = [
            {"score": 0.75, "source_url": "http://example.com/note.md"}
        ]
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.0] * 768

        with (
            patch.object(_mod, "_qdrant", mock_qdrant),
            patch.object(_mod, "_embedder", mock_embedder),
        ):
            result = await search_semantic(query="test")

        # removeprefix("vault://") on a non-matching URL returns it unchanged
        assert result["results"][0]["path"] == "http://example.com/note.md"

    async def test_mixed_results_with_and_without_source_url(self, tmp_path):
        """Mixed results: source_url gets path added, missing source_url is left alone."""
        mock_qdrant = AsyncMock()
        mock_qdrant.search.return_value = [
            {"score": 0.9, "source_url": "vault://notes/a.md"},
            {"score": 0.7, "chunk_text": "no url here"},
        ]
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.0] * 768

        with (
            patch.object(_mod, "_qdrant", mock_qdrant),
            patch.object(_mod, "_embedder", mock_embedder),
        ):
            result = await search_semantic(query="test")

        assert result["results"][0]["path"] == "notes/a.md"
        assert "path" not in result["results"][1]

    async def test_limit_forwarded_to_qdrant(self, tmp_path):
        """The limit parameter is passed through to qdrant.search."""
        mock_qdrant = AsyncMock()
        mock_qdrant.search.return_value = []
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.0] * 768

        with (
            patch.object(_mod, "_qdrant", mock_qdrant),
            patch.object(_mod, "_embedder", mock_embedder),
        ):
            await search_semantic(query="test", limit=10)

        mock_qdrant.search.assert_called_once_with(vector=[0.0] * 768, limit=10)


# ---------------------------------------------------------------------------
# get_history — commit log parsing
# ---------------------------------------------------------------------------


class TestGetHistoryParsing:
    async def test_commit_message_parsed_correctly(self, tmp_path):
        """The git log --format=%H|%s|%an|%ai output is split correctly into fields."""
        (tmp_path / "note.md").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add some content"],
            cwd=tmp_path,
            capture_output=True,
        )
        result = await get_history(path="note.md")
        assert len(result["commits"]) == 1
        commit = result["commits"][0]
        assert commit["message"] == "feat: add some content"
        assert commit["author"] == "Test"
        assert "2026" in commit["date"]  # ISO date contains the year

    async def test_all_commit_fields_present(self, tmp_path):
        """Each commit dict has hash, message, author, date keys."""
        (tmp_path / "a.md").write_text("a")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True
        )
        result = await get_history()
        assert len(result["commits"]) == 1
        commit = result["commits"][0]
        assert "hash" in commit
        assert "message" in commit
        assert "author" in commit
        assert "date" in commit

    async def test_hash_is_40_character_hex(self, tmp_path):
        """The hash field should be a full 40-char git SHA."""
        (tmp_path / "b.md").write_text("b")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True
        )
        result = await get_history()
        h = result["commits"][0]["hash"]
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    async def test_empty_repo_returns_empty_commits(self, tmp_path):
        """An empty repo (no commits) returns {'commits': []} without error."""
        result = await get_history()
        assert result == {"commits": []}


# ---------------------------------------------------------------------------
# delete_note — git failure propagation
# ---------------------------------------------------------------------------


class TestDeleteNoteGitFailure:
    async def test_git_add_failure_propagates(self, tmp_path):
        """delete_note calls _git directly (not _git_commit); CalledProcessError propagates."""
        (tmp_path / "note.md").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )

        exc = subprocess.CalledProcessError(128, "git", stderr="git error")
        with patch.object(_mod, "_git", side_effect=exc):
            with pytest.raises(subprocess.CalledProcessError):
                await delete_note(path="note.md", reason="test")

    async def test_path_validation_happens_before_file_ops(self, tmp_path):
        """Path traversal is rejected before any file move or git call."""
        with patch.object(_mod, "_git") as mock_git:
            result = await delete_note(path="../escape.md", reason="delete it")
        assert "error" in result
        mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# _reconcile_loop — inner reconciler error handling
# ---------------------------------------------------------------------------


class TestReconcileLoopReconcilerError:
    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    async def test_reconciler_error_is_caught_and_loop_continues(self, tmp_path):
        """When reconciler.run() raises a non-CancelledError, the loop logs and sleeps."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=5,
        )
        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()

        call_count = 0

        async def run_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("reconciler failed")
            raise asyncio.CancelledError

        mock_reconciler.run.side_effect = run_side_effect

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # run() was called twice: once errored, once raised CancelledError
        assert call_count == 2
        # sleep was called after the error (with reconcile_interval_seconds=5)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert 5 in sleep_calls

    async def test_cancelled_error_propagates_through_reconciler_error_handler(
        self, tmp_path
    ):
        """CancelledError is NOT caught by the except Exception block; it propagates."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=5,
        )
        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # run() was only called once (CancelledError propagated immediately)
        assert mock_reconciler.run.call_count == 1

    async def test_reconciler_loop_sleep_called_after_successful_run(self, tmp_path):
        """After a successful reconciler run, sleep(reconcile_interval_seconds) is called."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=42,
        )
        mock_embedder = MagicMock()
        mock_embedder.dimension = 768
        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()

        call_count = 0

        async def run_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        mock_reconciler.run.side_effect = run_side_effect

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # After the first successful run(), sleep(42) should have been called
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert 42 in sleep_calls


# ---------------------------------------------------------------------------
# _reconcile_loop — cache clearing on init failure
# ---------------------------------------------------------------------------


class TestReconcileLoopCacheClearing:
    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    async def test_cache_cleared_when_init_fails_and_cache_exists(self, tmp_path):
        """When init fails and embed_cache_dir exists, shutil.rmtree is called on it."""
        cache_dir = tmp_path / ".cache" / "fastembed"
        cache_dir.mkdir(parents=True)
        (cache_dir / "model.bin").write_bytes(b"fake model")

        settings = Settings(
            path=str(tmp_path),
            embed_cache_dir=str(cache_dir),
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

        # rmtree should have been called with the cache dir on the first failure
        mock_rmtree.assert_called_once_with(cache_dir, ignore_errors=True)

    async def test_globals_reset_to_none_on_init_failure(self, tmp_path):
        """When init fails, _embedder and _qdrant are both set back to None."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=1,
        )

        call_count = 0

        def failing_then_succeeding(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("init failed")
            mock = MagicMock()
            mock.dimension = 768
            return mock

        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        # Capture state inside _reconcile_loop during the sleep (after failure)
        captured_state = {}

        async def capture_sleep(duration):
            if call_count == 1:
                captured_state["embedder"] = _mod._embedder
                captured_state["qdrant"] = _mod._qdrant

        with (
            patch.object(_mod, "VaultEmbedder", side_effect=failing_then_succeeding),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", side_effect=capture_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        assert captured_state.get("embedder") is None
        assert captured_state.get("qdrant") is None


# ---------------------------------------------------------------------------
# _git function — direct behavior
# ---------------------------------------------------------------------------


class TestGitFunction:
    def test_git_runs_command_in_vault_dir(self, tmp_path):
        """_git runs git with list-mode subprocess in the vault directory."""
        # The vault is a git repo (from _init_git fixture), so git status works
        result = _mod._git("status")
        assert result.returncode == 0

    def test_git_raises_on_failure(self, tmp_path):
        """_git raises CalledProcessError when the command fails (check=True)."""
        with pytest.raises(subprocess.CalledProcessError):
            _mod._git("log", "nonexistent-branch-xyz-abc")

    def test_git_uses_provided_cwd(self, tmp_path):
        """_git respects an explicit cwd override."""
        other_dir = tmp_path / "subdir"
        other_dir.mkdir()
        subprocess.run(["git", "init", str(other_dir)], capture_output=True)
        result = _mod._git("status", cwd=other_dir)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# configure + _vault_path
# ---------------------------------------------------------------------------


class TestConfigureAndVaultPath:
    def test_vault_path_matches_settings_path(self, tmp_path):
        """_vault_path() returns Path(settings.path)."""
        configure(Settings(path=str(tmp_path)))
        assert _mod._vault_path() == Path(str(tmp_path))

    def test_configure_creates_new_lock(self, tmp_path):
        """configure() creates a fresh asyncio.Lock each time it is called."""
        configure(Settings(path=str(tmp_path)))
        lock1 = _mod._lock
        configure(Settings(path=str(tmp_path)))
        lock2 = _mod._lock
        assert lock1 is not lock2
        assert isinstance(lock2, asyncio.Lock)

    def test_configure_updates_settings_reference(self, tmp_path):
        """configure() updates the _settings global."""
        s = Settings(path=str(tmp_path))
        configure(s)
        assert _mod._settings is s


# ---------------------------------------------------------------------------
# main() lifespan wiring
# ---------------------------------------------------------------------------


class TestMainLifespanWiring:
    def test_lifespan_context_is_replaced(self):
        """main() replaces app.router.lifespan_context with a new async CM."""
        import inspect

        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = "/tmp/test-vault"
        mock_settings.port = 8000
        mock_app = MagicMock()
        fake_original_lifespan = MagicMock()
        mock_app.router.lifespan_context = fake_original_lifespan

        with (
            patch.object(_mod, "Settings", return_value=mock_settings),
            patch.object(_mod, "configure"),
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run"),
        ):
            _mod.main()

        # lifespan_context was replaced (it's now a new callable, not the original)
        new_lifespan = mock_app.router.lifespan_context
        assert new_lifespan is not fake_original_lifespan
        assert callable(new_lifespan)
