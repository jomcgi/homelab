"""Tests for knowledge service startup registration and handlers."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge import service
from knowledge.gardener import GardenStats
from knowledge.reconciler import ReconcileStats
from knowledge.service import garden_handler, on_startup


class TestOnStartup:
    def test_registers_garden_and_reconcile_jobs(self):
        """on_startup registers garden, reconcile, and vault-backup jobs."""
        session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(session)
        names = [call.kwargs["name"] for call in mock_register.call_args_list]
        assert "knowledge.garden" in names
        assert "knowledge.reconcile" in names
        assert "knowledge.vault-backup" in names

    def test_garden_registered_before_reconcile(self):
        """Documentary convention: knowledge.garden is registered first.

        The scheduler claims one job per tick and polls every 30s, so
        registration order has no runtime effect — the two jobs always
        run in separate ticks. This test encodes the team convention of
        listing producers before consumers in on_startup so that reading
        the code top-to-bottom follows the data flow.
        """
        session = MagicMock()
        order: list[str] = []
        with patch(
            "shared.scheduler.register_job",
            side_effect=lambda *a, **kw: order.append(kw["name"]),
        ):
            on_startup(session)
        assert order.index("knowledge.garden") < order.index("knowledge.reconcile")


class TestReconcileHandler:
    """reconcile_handler constructs a Reconciler from the env and calls run()."""

    @pytest.mark.asyncio
    async def test_uses_vault_root_env_var(self, monkeypatch, tmp_path):
        """VAULT_ROOT env var determines the vault_root passed to Reconciler."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        mock_stats = ReconcileStats(
            upserted=0, deleted=0, unchanged=0, failed=0, skipped_locked=0
        )
        mock_reconciler = AsyncMock()
        mock_reconciler.run.return_value = mock_stats

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            await service.reconcile_handler(MagicMock())

        MockReconciler.assert_called_once()
        _, call_kwargs = MockReconciler.call_args
        assert call_kwargs["vault_root"] == tmp_path

    @pytest.mark.asyncio
    async def test_uses_default_vault_root_when_env_unset(self, monkeypatch):
        """When VAULT_ROOT is not set the default /vault path is used."""
        monkeypatch.delenv("VAULT_ROOT", raising=False)

        mock_stats = ReconcileStats(
            upserted=0, deleted=0, unchanged=0, failed=0, skipped_locked=0
        )
        mock_reconciler = AsyncMock()
        mock_reconciler.run.return_value = mock_stats

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            await service.reconcile_handler(MagicMock())

        _, call_kwargs = MockReconciler.call_args
        assert call_kwargs["vault_root"] == Path("/vault")

    @pytest.mark.asyncio
    async def test_calls_reconciler_run(self, monkeypatch, tmp_path):
        """reconcile_handler always calls reconciler.run() exactly once."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        mock_stats = ReconcileStats(
            upserted=3, deleted=1, unchanged=2, failed=0, skipped_locked=0
        )
        mock_reconciler = AsyncMock()
        mock_reconciler.run.return_value = mock_stats

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            await service.reconcile_handler(MagicMock())

        mock_reconciler.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none(self, monkeypatch, tmp_path):
        """reconcile_handler returns None (scheduler uses this as a sentinel)."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        mock_stats = ReconcileStats(
            upserted=0, deleted=0, unchanged=0, failed=0, skipped_locked=0
        )
        mock_reconciler = AsyncMock()
        mock_reconciler.run.return_value = mock_stats

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            result = await service.reconcile_handler(MagicMock())

        assert result is None

    @pytest.mark.asyncio
    async def test_constructs_store_from_session(self, monkeypatch, tmp_path):
        """KnowledgeStore is constructed with the session passed to reconcile_handler."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        session = MagicMock()
        mock_stats = ReconcileStats(
            upserted=0, deleted=0, unchanged=0, failed=0, skipped_locked=0
        )
        mock_reconciler = AsyncMock()
        mock_reconciler.run.return_value = mock_stats

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore") as MockStore,
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            await service.reconcile_handler(session)

        MockStore.assert_called_once_with(session=session)


class TestGardenHandler:
    @pytest.mark.asyncio
    async def test_skips_when_oauth_token_unset(self, monkeypatch, caplog):
        """garden_handler returns None and logs a warning when token is absent.

        When CLAUDE_CODE_OAUTH_TOKEN is not set, garden_handler returns None
        immediately before the deferred `from knowledge.gardener import Gardener`
        is ever reached.  The observable effects are the return value and the
        warning log entry.
        """
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        session = MagicMock()
        with caplog.at_level(logging.WARNING, logger="knowledge.service"):
            result = await garden_handler(session)
        assert result is None
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any("CLAUDE_CODE_OAUTH_TOKEN" in msg for msg in warning_messages)

    @pytest.mark.asyncio
    async def test_runs_gardener_when_token_set(self, monkeypatch, tmp_path):
        """garden_handler constructs Gardener(vault_root, max_files_per_run) and awaits run()."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ot-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=2, failed=0, ttl_cleaned=1)
        )
        with patch(
            "knowledge.gardener.Gardener", return_value=gardener_instance
        ) as mock_gardener:
            result = await garden_handler(session)
        assert result is None
        mock_gardener.assert_called_once()
        kwargs = mock_gardener.call_args.kwargs
        assert kwargs["vault_root"] == tmp_path
        assert kwargs["max_files_per_run"] == 10
        assert "anthropic_client" not in kwargs
        assert "store" not in kwargs
        assert "embed_client" not in kwargs
        gardener_instance.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_when_all_ingests_failed(
        self, monkeypatch, tmp_path, caplog
    ):
        """When every ingest failed, the completion log is promoted to ERROR."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ot-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=3, ttl_cleaned=0)
        )
        with (
            patch("knowledge.gardener.Gardener", return_value=gardener_instance),
            caplog.at_level(logging.ERROR, logger="knowledge.service"),
        ):
            await garden_handler(session)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert "all failed" in error_records[0].message

    @pytest.mark.asyncio
    async def test_honors_max_files_env_override(self, monkeypatch, tmp_path):
        """GARDENER_MAX_FILES_PER_RUN env var overrides the default cap."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ot-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GARDENER_MAX_FILES_PER_RUN", "25")
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=0, ttl_cleaned=0)
        )
        with patch(
            "knowledge.gardener.Gardener", return_value=gardener_instance
        ) as mock_gardener:
            await garden_handler(session)
        assert mock_gardener.call_args.kwargs["max_files_per_run"] == 25

    @pytest.mark.asyncio
    async def test_invalid_max_files_env_falls_back_to_default(
        self, monkeypatch, tmp_path
    ):
        """GARDENER_MAX_FILES_PER_RUN set to a non-integer falls back to the default of 10."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GARDENER_MAX_FILES_PER_RUN", "notanumber")
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=0, ttl_cleaned=0)
        )
        with patch(
            "knowledge.gardener.Gardener", return_value=gardener_instance
        ) as mock_gardener:
            await garden_handler(session)
        assert mock_gardener.call_args.kwargs["max_files_per_run"] == 10


class TestCloneVault:
    @pytest.mark.asyncio
    async def test_skips_when_git_remote_unset(self, monkeypatch, tmp_path, caplog):
        """clone_vault skips clone and writes sentinel when VAULT_GIT_REMOTE is empty."""
        monkeypatch.delenv("VAULT_GIT_REMOTE", raising=False)
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with caplog.at_level(logging.INFO, logger="knowledge.service"):
            await service.clone_vault()
        assert any("VAULT_GIT_REMOTE not set" in r.message for r in caplog.records)
        assert (tmp_path / ".git-ready").exists()

    @pytest.mark.asyncio
    async def test_skips_when_already_cloned(self, monkeypatch, tmp_path, caplog):
        """clone_vault skips clone and writes sentinel when .git already exists."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with caplog.at_level(logging.INFO, logger="knowledge.service"):
            await service.clone_vault()
        assert any("already initialised" in r.message for r in caplog.records)
        assert (tmp_path / ".git-ready").exists()

    @pytest.mark.asyncio
    async def test_clones_repo_with_dulwich(self, monkeypatch, tmp_path):
        """clone_vault calls porcelain.clone with correct args and writes sentinel."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.porcelain.clone") as mock_clone:
            await service.clone_vault()
        mock_clone.assert_called_once_with(
            source="https://github.com/test/repo.git",
            target=str(tmp_path),
            depth=1,
            username="x-access-token",
            password="ghp_test",
        )
        assert (tmp_path / ".git-ready").exists()

    @pytest.mark.asyncio
    async def test_clones_without_token(self, monkeypatch, tmp_path):
        """clone_vault omits credentials when GITHUB_TOKEN is unset."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.porcelain.clone") as mock_clone:
            await service.clone_vault()
        mock_clone.assert_called_once_with(
            source="https://github.com/test/repo.git",
            target=str(tmp_path),
            depth=1,
        )

    @pytest.mark.asyncio
    async def test_clone_failure_logs_warning_and_writes_sentinel(
        self, monkeypatch, tmp_path, caplog
    ):
        """clone_vault logs warning on failure and still writes sentinel."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch(
            "knowledge.service.porcelain.clone",
            side_effect=Exception("network error"),
        ):
            with caplog.at_level(logging.WARNING, logger="knowledge.service"):
                await service.clone_vault()
        assert any("clone failed" in r.message.lower() for r in caplog.records)
        assert (tmp_path / ".git-ready").exists()


def _empty_status():
    """Create a mock porcelain.status result with no changes."""
    status = MagicMock()
    status.staged = {"add": [], "delete": [], "modify": []}
    status.unstaged = []
    status.untracked = []
    return status


def _dirty_status(unstaged=None, untracked=None, staged_add=None):
    """Create a mock porcelain.status result with changes."""
    status = MagicMock()
    status.staged = {
        "add": staged_add or [],
        "delete": [],
        "modify": [],
    }
    status.unstaged = unstaged or []
    status.untracked = untracked or []
    return status


class TestVaultBackupHandler:
    @pytest.mark.asyncio
    async def test_skips_when_no_git_dir(self, monkeypatch, tmp_path):
        """vault_backup_handler skips when vault has no .git directory."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        result = await service.vault_backup_handler(MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_no_changes(self, monkeypatch, tmp_path):
        """vault_backup_handler does nothing when status reports no changes."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.porcelain.status", return_value=_empty_status()):
            result = await service.vault_backup_handler(MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_commits_and_pushes_when_changes_exist(self, monkeypatch, tmp_path):
        """vault_backup_handler commits and pushes when there are unstaged changes."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        (tmp_path / ".git").mkdir()
        with (
            patch(
                "knowledge.service.porcelain.status",
                return_value=_dirty_status(unstaged=[b"file.md"]),
            ),
            patch("knowledge.service.porcelain.add") as mock_add,
            patch("knowledge.service.porcelain.commit") as mock_commit,
            patch("knowledge.service.porcelain.push") as mock_push,
        ):
            result = await service.vault_backup_handler(MagicMock())
        assert result is None
        mock_add.assert_called_once_with(str(tmp_path))
        mock_commit.assert_called_once_with(
            str(tmp_path),
            message=b"sync: vault backup",
            author=b"vault-backup <vault-backup@monolith.local>",
            committer=b"vault-backup <vault-backup@monolith.local>",
        )
        mock_push.assert_called_once_with(
            path=str(tmp_path), username="x-access-token", password="ghp_test"
        )

    @pytest.mark.asyncio
    async def test_includes_untracked_as_changes(self, monkeypatch, tmp_path):
        """vault_backup_handler treats untracked files as changes."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        (tmp_path / ".git").mkdir()
        with (
            patch(
                "knowledge.service.porcelain.status",
                return_value=_dirty_status(untracked=["new-file.md"]),
            ),
            patch("knowledge.service.porcelain.add") as mock_add,
            patch("knowledge.service.porcelain.commit"),
            patch("knowledge.service.porcelain.push"),
        ):
            await service.vault_backup_handler(MagicMock())
        mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_failure_logs_warning(self, monkeypatch, tmp_path, caplog):
        """vault_backup_handler logs a warning when push fails."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        (tmp_path / ".git").mkdir()
        with (
            patch(
                "knowledge.service.porcelain.status",
                return_value=_dirty_status(unstaged=[b"file.md"]),
            ),
            patch("knowledge.service.porcelain.add"),
            patch("knowledge.service.porcelain.commit"),
            patch(
                "knowledge.service.porcelain.push",
                side_effect=Exception("rejected"),
            ),
            caplog.at_level(logging.WARNING, logger="knowledge.service"),
        ):
            await service.vault_backup_handler(MagicMock())
        assert any("push failed" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_push_uses_token_auth(self, monkeypatch, tmp_path):
        """vault_backup_handler passes token credentials to push."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
        (tmp_path / ".git").mkdir()
        with (
            patch(
                "knowledge.service.porcelain.status",
                return_value=_dirty_status(unstaged=[b"file.md"]),
            ),
            patch("knowledge.service.porcelain.add"),
            patch("knowledge.service.porcelain.commit"),
            patch("knowledge.service.porcelain.push") as mock_push,
        ):
            await service.vault_backup_handler(MagicMock())
        mock_push.assert_called_once_with(
            path=str(tmp_path), username="x-access-token", password="ghp_secret"
        )
