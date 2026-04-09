"""Coverage tests for service.py exception-propagation paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge import service


class TestGardenHandlerExceptionPropagation:
    @pytest.mark.asyncio
    async def test_propagates_exception_from_gardener_run(self, monkeypatch, tmp_path):
        """Unhandled exceptions from Gardener.run() propagate out of
        garden_handler() — the scheduler can then mark the job as failed
        and the outage is surfaced through the normal error path."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(side_effect=RuntimeError("gardener exploded"))

        with patch("knowledge.gardener.Gardener", return_value=gardener_instance):
            with pytest.raises(RuntimeError, match="gardener exploded"):
                await service.garden_handler(MagicMock())

    @pytest.mark.asyncio
    async def test_propagates_exception_from_gardener_construction(
        self, monkeypatch, tmp_path
    ):
        """If Gardener() raises during construction the exception propagates
        out of garden_handler()."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        with patch("knowledge.gardener.Gardener", side_effect=ValueError("bad vault")):
            with pytest.raises(ValueError, match="bad vault"):
                await service.garden_handler(MagicMock())

    @pytest.mark.asyncio
    async def test_propagates_os_error_from_gardener_run(self, monkeypatch, tmp_path):
        """OSError (e.g. vault filesystem gone) propagates from Gardener.run()."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(side_effect=OSError("vault mount gone"))

        with patch("knowledge.gardener.Gardener", return_value=gardener_instance):
            with pytest.raises(OSError, match="vault mount gone"):
                await service.garden_handler(MagicMock())


class TestReconcileHandlerExceptionPropagation:
    @pytest.mark.asyncio
    async def test_propagates_exception_from_reconciler_run(
        self, monkeypatch, tmp_path
    ):
        """Unhandled exceptions from Reconciler.run() propagate out of
        reconcile_handler() so the scheduler can handle the failure."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = RuntimeError("database gone")

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            with pytest.raises(RuntimeError, match="database gone"):
                await service.reconcile_handler(MagicMock())

    @pytest.mark.asyncio
    async def test_propagates_os_error_from_reconciler_run(self, monkeypatch, tmp_path):
        """OSError from Reconciler.run() (e.g. vault is unmounted mid-run)
        propagates out of reconcile_handler()."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = OSError("vault read-only")

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            with pytest.raises(OSError, match="vault read-only"):
                await service.reconcile_handler(MagicMock())

    @pytest.mark.asyncio
    async def test_propagates_value_error_from_reconciler_run(
        self, monkeypatch, tmp_path
    ):
        """ValueError from Reconciler.run() propagates correctly."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = ValueError("schema mismatch")

        with (
            patch("knowledge.service.Reconciler") as MockReconciler,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            MockReconciler.return_value = mock_reconciler
            with pytest.raises(ValueError, match="schema mismatch"):
                await service.reconcile_handler(MagicMock())
