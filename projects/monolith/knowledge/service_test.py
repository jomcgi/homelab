"""Unit tests for knowledge.service — on_startup and reconcile_handler."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge import service
from knowledge.reconciler import ReconcileStats


class TestOnStartup:
    """on_startup registers the knowledge.reconcile job with the scheduler."""

    def test_registers_job_with_correct_args(self):
        """on_startup calls register_job with name, interval_secs, ttl_secs, and handler."""
        session = MagicMock()

        with patch("shared.scheduler.register_job") as mock_register:
            service.on_startup(session)

        mock_register.assert_called_once_with(
            session,
            name="knowledge.reconcile",
            interval_secs=300,
            handler=service.reconcile_handler,
            ttl_secs=600,
        )

    def test_passes_session_as_first_positional_arg(self):
        """The session object is forwarded as the first argument to register_job."""
        session = MagicMock()

        with patch("shared.scheduler.register_job") as mock_register:
            service.on_startup(session)

        call_args = mock_register.call_args
        # First positional arg must be the session
        assert call_args.args[0] is session


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

        with patch("knowledge.service.Reconciler") as MockReconciler, patch(
            "knowledge.service.KnowledgeStore"
        ), patch("knowledge.service.EmbeddingClient"):
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

        with patch("knowledge.service.Reconciler") as MockReconciler, patch(
            "knowledge.service.KnowledgeStore"
        ), patch("knowledge.service.EmbeddingClient"):
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

        with patch("knowledge.service.Reconciler") as MockReconciler, patch(
            "knowledge.service.KnowledgeStore"
        ), patch("knowledge.service.EmbeddingClient"):
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

        with patch("knowledge.service.Reconciler") as MockReconciler, patch(
            "knowledge.service.KnowledgeStore"
        ), patch("knowledge.service.EmbeddingClient"):
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

        with patch("knowledge.service.Reconciler") as MockReconciler, patch(
            "knowledge.service.KnowledgeStore"
        ) as MockStore, patch("knowledge.service.EmbeddingClient"):
            MockReconciler.return_value = mock_reconciler
            await service.reconcile_handler(session)

        MockStore.assert_called_once_with(session=session)
