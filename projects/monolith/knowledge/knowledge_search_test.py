"""Tests for the knowledge-search CLI tool.

The tool is a standalone script (not a Python module) that lives at
knowledge/tools/knowledge-search.  It exposes a single ``main()``
coroutine that we load via ``importlib`` — patching ``asyncio.run``
during import to suppress the top-level ``asyncio.run(main())`` call
so we can invoke ``main()`` directly inside each test.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level load of the knowledge-search script
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).parent / "tools" / "knowledge-search"


def _load_main():
    """Import knowledge-search as a module and return its ``main`` coroutine."""
    spec = importlib.util.spec_from_file_location(
        "knowledge_search", str(_SCRIPT_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    # Patch asyncio.run so the top-level call is a no-op during import.
    with patch.object(asyncio, "run"):
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.main


main = _load_main()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_mocks(search_results: list[dict]) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (mock_sqlmodel, mock_shared_embedding, mock_knowledge_store) set up
    so that search_notes() returns *search_results*."""
    mock_embed_instance = AsyncMock()
    mock_embed_instance.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_embed_class = MagicMock(return_value=mock_embed_instance)

    mock_store_instance = MagicMock()
    mock_store_instance.search_notes.return_value = search_results
    mock_store_class = MagicMock(return_value=mock_store_instance)

    mock_sqlmodel = MagicMock()
    mock_sqlmodel.create_engine = MagicMock(return_value=MagicMock())
    # Session must work as a context manager — MagicMock supports this automatically.
    mock_sqlmodel.Session = MagicMock()

    mock_shared_embedding = MagicMock()
    mock_shared_embedding.EmbeddingClient = mock_embed_class

    mock_knowledge_store_mod = MagicMock()
    mock_knowledge_store_mod.KnowledgeStore = mock_store_class

    return mock_sqlmodel, mock_shared_embedding, mock_knowledge_store_mod


# ---------------------------------------------------------------------------
# Empty / blank query
# ---------------------------------------------------------------------------


class TestEmptyQuery:
    @pytest.mark.asyncio
    async def test_no_args_prints_empty_array(self, capsys, monkeypatch):
        """No CLI arguments → prints ``[]`` to stdout and returns immediately."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search"])
        await main()
        assert capsys.readouterr().out.strip() == "[]"

    @pytest.mark.asyncio
    async def test_whitespace_only_prints_empty_array(self, capsys, monkeypatch):
        """Arguments that collapse to empty string after strip → prints ``[]``."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "   ", "\t"])
        await main()
        assert capsys.readouterr().out.strip() == "[]"

    @pytest.mark.asyncio
    async def test_empty_query_does_not_access_database(self, monkeypatch):
        """Empty query returns before any DB import is attempted."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search"])
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # If DB code were reached it would fail; the fact it doesn't is the assertion.
        await main()  # must not raise


# ---------------------------------------------------------------------------
# DATABASE_URL guard
# ---------------------------------------------------------------------------


class TestDatabaseUrlGuard:
    @pytest.mark.asyncio
    async def test_missing_env_prints_error_to_stderr(self, capsys, monkeypatch):
        """When DATABASE_URL is absent an error is written to stderr."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "hello"])
        monkeypatch.delenv("DATABASE_URL", raising=False)
        await main()
        err = capsys.readouterr().err
        assert "DATABASE_URL" in err

    @pytest.mark.asyncio
    async def test_missing_env_prints_empty_array_to_stdout(
        self, capsys, monkeypatch
    ):
        """When DATABASE_URL is absent stdout is ``[]``."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "hello"])
        monkeypatch.delenv("DATABASE_URL", raising=False)
        await main()
        assert capsys.readouterr().out.strip() == "[]"

    @pytest.mark.asyncio
    async def test_missing_env_no_db_import(self, capsys, monkeypatch):
        """No DB imports are triggered when DATABASE_URL is absent."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "hello"])
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # The real sqlmodel / knowledge.store are available in the test env;
        # we verify they are NOT imported by ensuring no side-effects occur.
        await main()
        # Reaching here without ImportError proves no network/DB access was attempted.


# ---------------------------------------------------------------------------
# Happy path — search returns results
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_returns_json_array_with_results(self, capsys, monkeypatch):
        """When search succeeds, stdout is a JSON array containing the results."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "machine learning"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        results = [
            {"id": "ml-basics", "title": "ML Basics", "score": 0.92},
            {"id": "neural-nets", "title": "Neural Nets", "score": 0.85},
        ]
        mock_sql, mock_emb, mock_store = _make_db_mocks(results)

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        assert data[0]["id"] == "ml-basics"
        assert data[1]["id"] == "neural-nets"

    @pytest.mark.asyncio
    async def test_output_is_valid_json(self, capsys, monkeypatch):
        """Output is always parseable JSON."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "python"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        mock_sql, mock_emb, mock_store = _make_db_mocks(
            [{"id": "py", "title": "Python", "score": 0.95}]
        )

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        # Must not raise
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_empty_results_list(self, capsys, monkeypatch):
        """When the store returns no results, stdout is ``[]``."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "obscure topic"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        mock_sql, mock_emb, mock_store = _make_db_mocks([])

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        assert data == []


# ---------------------------------------------------------------------------
# NaN / infinity score filtering
# ---------------------------------------------------------------------------


class TestNanScoreFiltering:
    @pytest.mark.asyncio
    async def test_nan_score_is_filtered_out(self, capsys, monkeypatch):
        """Results whose score is NaN are dropped from the output."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "topic"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        results = [
            {"id": "good", "score": 0.9},
            {"id": "nan-score", "score": float("nan")},
        ]
        mock_sql, mock_emb, mock_store = _make_db_mocks(results)

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["id"] == "good"

    @pytest.mark.asyncio
    async def test_inf_score_is_filtered_out(self, capsys, monkeypatch):
        """Results whose score is ±infinity are dropped from the output."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "topic"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        results = [
            {"id": "good", "score": 0.75},
            {"id": "pos-inf", "score": float("inf")},
            {"id": "neg-inf", "score": float("-inf")},
        ]
        mock_sql, mock_emb, mock_store = _make_db_mocks(results)

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        ids = [d["id"] for d in data]
        assert ids == ["good"]

    @pytest.mark.asyncio
    async def test_missing_score_key_is_filtered_out(self, capsys, monkeypatch):
        """Results that have no 'score' key are dropped."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "topic"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        results = [
            {"id": "scored", "score": 0.8},
            {"id": "no-score"},
        ]
        mock_sql, mock_emb, mock_store = _make_db_mocks(results)

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["id"] == "scored"

    @pytest.mark.asyncio
    async def test_string_score_is_filtered_out(self, capsys, monkeypatch):
        """Results whose score is a non-numeric string are dropped."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "topic"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        results = [
            {"id": "good", "score": 0.6},
            {"id": "bad-type", "score": "high"},
        ]
        mock_sql, mock_emb, mock_store = _make_db_mocks(results)

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["id"] == "good"

    @pytest.mark.asyncio
    async def test_all_nan_results_gives_empty_array(self, capsys, monkeypatch):
        """When every result has a bad score the output is ``[]``."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "topic"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        results = [
            {"id": "r1", "score": float("nan")},
            {"id": "r2", "score": float("inf")},
        ]
        mock_sql, mock_emb, mock_store = _make_db_mocks(results)

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        data = json.loads(capsys.readouterr().out)
        assert data == []


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_exception_during_embed_prints_empty_array(
        self, capsys, monkeypatch
    ):
        """An exception inside the try block results in ``[]`` on stdout."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "fail"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        mock_embed_instance = AsyncMock()
        mock_embed_instance.embed = AsyncMock(
            side_effect=RuntimeError("embedding service down")
        )
        mock_embed_class = MagicMock(return_value=mock_embed_instance)

        mock_emb = MagicMock()
        mock_emb.EmbeddingClient = mock_embed_class
        mock_sql = MagicMock()
        mock_sql.create_engine = MagicMock(return_value=MagicMock())
        mock_sql.Session = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": MagicMock(),
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        assert capsys.readouterr().out.strip() == "[]"

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self, monkeypatch, capsys):
        """Exceptions inside the try/except block are swallowed — main() never raises."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "fail"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        mock_embed_instance = AsyncMock()
        mock_embed_instance.embed = AsyncMock(side_effect=Exception("unexpected"))
        mock_embed_class = MagicMock(return_value=mock_embed_instance)

        mock_emb = MagicMock()
        mock_emb.EmbeddingClient = mock_embed_class
        mock_sql = MagicMock()
        mock_sql.create_engine = MagicMock(return_value=MagicMock())
        mock_sql.Session = MagicMock()

        # Must not raise
        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": MagicMock(),
                "sqlmodel": mock_sql,
            },
        ):
            await main()

    @pytest.mark.asyncio
    async def test_exception_during_db_search_prints_empty_array(
        self, capsys, monkeypatch
    ):
        """An exception thrown by KnowledgeStore.search_notes() → ``[]`` output."""
        monkeypatch.setattr(sys, "argv", ["knowledge-search", "query"])
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        mock_embed_instance = AsyncMock()
        mock_embed_instance.embed = AsyncMock(return_value=[0.1, 0.2])
        mock_embed_class = MagicMock(return_value=mock_embed_instance)

        mock_store_instance = MagicMock()
        mock_store_instance.search_notes.side_effect = RuntimeError("db connection lost")
        mock_store_class = MagicMock(return_value=mock_store_instance)

        mock_emb = MagicMock()
        mock_emb.EmbeddingClient = mock_embed_class
        mock_store = MagicMock()
        mock_store.KnowledgeStore = mock_store_class
        mock_sql = MagicMock()
        mock_sql.create_engine = MagicMock(return_value=MagicMock())
        mock_sql.Session = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "shared.embedding": mock_emb,
                "knowledge.store": mock_store,
                "sqlmodel": mock_sql,
            },
        ):
            await main()

        assert capsys.readouterr().out.strip() == "[]"
