"""Unit tests for knowledge/mcp.py — MCP tools for knowledge search and retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.mcp import get_note, mcp, search_knowledge

FAKE_EMBEDDING = [0.1] * 1024

CANNED_RESULTS = [
    {
        "note_id": "n1",
        "title": "Attention Is All You Need",
        "path": "papers/attention.md",
        "type": "paper",
        "tags": ["ml", "transformers"],
        "score": 0.95,
        "section": "## Architecture",
        "snippet": "The transformer replaces recurrence entirely with attention.",
        "edges": [],
    },
]

SAMPLE_NOTE = {
    "note_id": "n1",
    "title": "Attention Is All You Need",
    "path": "papers/attention.md",
    "type": "paper",
    "tags": ["ml", "transformers"],
}


class TestSearchKnowledge:
    """Tests for the search_knowledge MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_results(self):
        mock_session = MagicMock()
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = FAKE_EMBEDDING

        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.EmbeddingClient", return_value=mock_embed),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.search_notes_with_context.return_value = (
                CANNED_RESULTS
            )
            result = await search_knowledge("attention")

        assert len(result["results"]) == 1
        assert result["results"][0]["note_id"] == "n1"
        mock_embed.embed.assert_awaited_once_with("attention")

    @pytest.mark.asyncio
    async def test_short_query_returns_empty(self):
        result = await search_knowledge("a")
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        result = await search_knowledge("")
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_limit_and_type_forwarded(self):
        mock_session = MagicMock()
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = FAKE_EMBEDDING

        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.EmbeddingClient", return_value=mock_embed),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.search_notes_with_context.return_value = []
            await search_knowledge("attention", limit=5, type="paper")

            MockStore.return_value.search_notes_with_context.assert_called_once_with(
                query_embedding=FAKE_EMBEDDING,
                limit=5,
                type_filter="paper",
            )

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_error(self):
        mock_embed = AsyncMock()
        mock_embed.embed.side_effect = RuntimeError("boom")

        with (
            patch("knowledge.mcp.Session"),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.EmbeddingClient", return_value=mock_embed),
        ):
            result = await search_knowledge("hello")

        assert "error" in result


class TestGetNote:
    """Tests for the get_note MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_note_with_content(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "papers" / "attention.md"
        note_file.parent.mkdir(parents=True)
        note_file.write_text("# Attention\n\nSelf-attention mechanism.")

        monkeypatch.setenv("VAULT_ROOT", str(vault_dir))

        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = SAMPLE_NOTE
            MockStore.return_value.get_note_links.return_value = []
            result = await get_note("n1")

        assert result["note_id"] == "n1"
        assert result["content"] == "# Attention\n\nSelf-attention mechanism."
        assert result["edges"] == []

    @pytest.mark.asyncio
    async def test_missing_note_returns_error(self):
        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = None
            result = await get_note("nonexistent")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_vault_file_returns_error(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setenv("VAULT_ROOT", str(vault_dir))

        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = {
                **SAMPLE_NOTE,
                "path": "nonexistent/missing.md",
            }
            result = await get_note("n1")

        assert "error" in result
