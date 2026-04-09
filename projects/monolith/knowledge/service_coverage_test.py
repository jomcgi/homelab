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
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            side_effect=RuntimeError("gardener exploded")
        )

        with (
            patch("anthropic.Anthropic"),
            patch("knowledge.gardener.Gardener", return_value=gardener_instance),
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            with pytest.raises(RuntimeError, match="gardener exploded"):
                await service.garden_handler(MagicMock())

    @pytest.mark.asyncio
    async def test_propagates_exception_from_anthropic_client_creation(
        self, monkeypatch, tmp_path
    ):
        """If anthropic.Anthropic() raises during construction (e.g. bad auth
        token format, import-time initialisation failure), the exception
        propagates out of garden_handler()."""
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-bad-token")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        with patch("anthropic.Anthropic", side_effect=ValueError("bad auth token")):
            with pytest.raises(ValueError, match="bad auth token"):
                await service.garden_handler(MagicMock())

    @pytest.mark.asyncio
    async def test_propagates_os_error_from_gardener_run(self, monkeypatch, tmp_path):
        """OSError (e.g. vault filesystem gone) propagates from Gardener.run()."""
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            side_effect=OSError("vault mount gone")
        )

        with (
            patch("anthropic.Anthropic"),
            patch("knowledge.gardener.Gardener", return_value=gardener_instance),
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
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
    async def test_propagates_os_error_from_reconciler_run(
        self, monkeypatch, tmp_path
    ):
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
