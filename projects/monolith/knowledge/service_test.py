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
        """on_startup registers both knowledge.garden and knowledge.reconcile."""
        session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(session)
        names = [call.kwargs["name"] for call in mock_register.call_args_list]
        assert "knowledge.garden" in names
        assert "knowledge.reconcile" in names

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
    async def test_skips_when_api_key_unset(self, monkeypatch):
        """garden_handler returns None and constructs neither an Anthropic
        client nor a Gardener when ANTHROPIC_AUTH_TOKEN is unset."""
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        session = MagicMock()
        with (
            patch("anthropic.Anthropic") as mock_anthropic,
            patch("knowledge.gardener.Gardener") as mock_gardener,
        ):
            result = await garden_handler(session)
        assert result is None
        mock_anthropic.assert_not_called()
        mock_gardener.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_gardener_when_api_key_set(self, monkeypatch, tmp_path):
        """garden_handler constructs Gardener with the expected wiring and
        awaits run() when ANTHROPIC_AUTH_TOKEN is present."""
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=2, failed=0, ttl_cleaned=1)
        )
        with (
            patch("anthropic.Anthropic") as mock_anthropic,
            patch(
                "knowledge.gardener.Gardener", return_value=gardener_instance
            ) as mock_gardener,
            patch("knowledge.service.KnowledgeStore") as mock_store,
            patch("knowledge.service.EmbeddingClient") as mock_embed,
        ):
            result = await garden_handler(session)
        assert result is None
        mock_anthropic.assert_called_once_with(auth_token="sk-test")
        mock_store.assert_called_once_with(session=session)
        mock_embed.assert_called_once_with()
        mock_gardener.assert_called_once()
        kwargs = mock_gardener.call_args.kwargs
        assert kwargs["vault_root"] == tmp_path
        assert kwargs["anthropic_client"] is mock_anthropic.return_value
        assert kwargs["store"] is mock_store.return_value
        assert kwargs["embed_client"] is mock_embed.return_value
        assert kwargs["max_files_per_run"] == 10
        gardener_instance.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_when_all_ingests_failed(
        self, monkeypatch, tmp_path, caplog
    ):
        """When every ingest attempt failed, the completion log is promoted
        to ERROR so log-level alerting surfaces the outage."""
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=3, ttl_cleaned=0)
        )
        with (
            patch("anthropic.Anthropic"),
            patch("knowledge.gardener.Gardener", return_value=gardener_instance),
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
            caplog.at_level(logging.ERROR, logger="knowledge.service"),
        ):
            await garden_handler(session)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert "all failed" in error_records[0].message

    @pytest.mark.asyncio
    async def test_honors_max_files_env_override(self, monkeypatch, tmp_path):
        """GARDENER_MAX_FILES_PER_RUN env var overrides the default cap."""
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GARDENER_MAX_FILES_PER_RUN", "25")
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=0, ttl_cleaned=0)
        )
        with (
            patch("anthropic.Anthropic"),
            patch(
                "knowledge.gardener.Gardener", return_value=gardener_instance
            ) as mock_gardener,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            await garden_handler(session)
        assert mock_gardener.call_args.kwargs["max_files_per_run"] == 25

    @pytest.mark.asyncio
    async def test_invalid_max_files_env_falls_back_to_default(
        self, monkeypatch, tmp_path
    ):
        """GARDENER_MAX_FILES_PER_RUN set to a non-integer falls back to the default of 10."""
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GARDENER_MAX_FILES_PER_RUN", "notanumber")
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=0, ttl_cleaned=0)
        )
        with (
            patch("anthropic.Anthropic"),
            patch(
                "knowledge.gardener.Gardener", return_value=gardener_instance
            ) as mock_gardener,
            patch("knowledge.service.KnowledgeStore"),
            patch("knowledge.service.EmbeddingClient"),
        ):
            await garden_handler(session)
        assert mock_gardener.call_args.kwargs["max_files_per_run"] == 10
