"""Coverage tests for gardener.py exception and dispatch paths."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.gardener import Gardener


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _make_mock_anthropic(tool_use_responses):
    """Create a mock anthropic client that returns canned tool-use responses."""
    client = MagicMock()
    call_idx = {"n": 0}

    def create(**kwargs):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(tool_use_responses):
            return tool_use_responses[idx]
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = []
        return resp

    client.messages.create = create
    return client


class TestIngestOneApiFailure:
    @pytest.mark.asyncio
    async def test_raises_when_messages_create_throws(self, tmp_path):
        """If the Anthropic API raises during messages.create, the exception
        propagates out of _ingest_one() so run() can count it as a failure."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("API connection failed")

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=None,
            embed_client=None,
        )
        with pytest.raises(RuntimeError, match="API connection failed"):
            await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        # Raw file must survive — it was not soft-deleted
        assert (tmp_path / "inbox" / "raw.md").exists()

    @pytest.mark.asyncio
    async def test_run_counts_api_failure_as_failed(self, tmp_path):
        """When messages.create raises, run() increments failed, leaves ingested=0."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        client = MagicMock()
        client.messages.create.side_effect = Exception("API outage")

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=None,
            embed_client=None,
        )
        stats = await gardener.run()

        assert stats.failed == 1
        assert stats.ingested == 0

    @pytest.mark.asyncio
    async def test_api_exception_with_custom_exception_type(self, tmp_path):
        """Any exception type from the Anthropic API propagates correctly."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        client = MagicMock()
        client.messages.create.side_effect = ValueError("rate limit exceeded")

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=None,
            embed_client=None,
        )
        with pytest.raises(ValueError, match="rate limit exceeded"):
            await gardener._ingest_one(tmp_path / "inbox" / "raw.md")


class TestIngestOneFileIOError:
    @pytest.mark.asyncio
    async def test_raises_when_file_does_not_exist(self, tmp_path):
        """If the raw file doesn't exist, path.read_text() raises FileNotFoundError
        which propagates out of _ingest_one()."""
        nonexistent = tmp_path / "inbox" / "ghost.md"
        nonexistent.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately do NOT create the file

        client = MagicMock()
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=None,
            embed_client=None,
        )
        with pytest.raises(FileNotFoundError):
            await gardener._ingest_one(nonexistent)

    @pytest.mark.asyncio
    async def test_run_counts_io_error_as_failed(self, tmp_path):
        """A missing file discovered between _discover_raw_files() and _ingest_one()
        is counted as a failure, not an unhandled crash."""
        nonexistent = tmp_path / "inbox" / "ghost.md"
        nonexistent.parent.mkdir(parents=True, exist_ok=True)

        client = MagicMock()
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=None,
            embed_client=None,
        )
        # Inject the nonexistent path directly so run() tries to ingest it
        original_discover = gardener._discover_raw_files

        def patched_discover():
            return [nonexistent]

        gardener._discover_raw_files = patched_discover  # type: ignore[method-assign]
        stats = await gardener.run()

        assert stats.failed == 1
        assert stats.ingested == 0


class TestRunWithoutEmbedClient:
    @pytest.mark.asyncio
    async def test_run_succeeds_when_embed_client_is_none(self, tmp_path):
        """run() with embed_client=None still works if Claude doesn't call
        search_notes — the missing embed client is not a fatal error for
        the gardening cycle."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        create_block = MagicMock()
        create_block.type = "tool_use"
        create_block.id = "c1"
        create_block.name = "create_note"
        create_block.input = {"type": "atom", "title": "Test fact", "body": "A body."}
        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [create_block]

        client = _make_mock_anthropic([resp])

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=None,
            embed_client=None,  # No embed client — must not crash
        )
        stats = await gardener.run()

        assert stats.ingested == 1
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_search_returns_error_json_when_embed_client_none(self, tmp_path):
        """When embed_client is None, _handle_search_notes returns an error JSON
        rather than raising — the tool-use loop can continue after a search failure."""
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=None,
            embed_client=None,
        )
        result = await gardener._handle_search_notes({"query": "anything"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "unavailable" in parsed["error"]


class TestHandleToolDispatch:
    @pytest.mark.asyncio
    async def test_search_notes_tool_dispatches_to_handler(self, tmp_path):
        """_handle_tool('search_notes', ...) routes to _handle_search_notes
        and returns a JSON result (either results list or error dict)."""
        mock_store = MagicMock()
        mock_store.search_notes.return_value = []
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.0] * 1024

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=mock_embed,
        )
        result = await gardener._handle_tool("search_notes", {"query": "test query"})

        # Must be valid JSON
        parsed = json.loads(result)
        # embed was called, confirming dispatch reached the real handler
        mock_embed.embed.assert_called_once_with("test query")
        assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_get_note_tool_dispatches_to_handler(self, tmp_path):
        """_handle_tool('get_note', ...) routes to _handle_get_note.
        When the note doesn't exist in the store, it returns an error JSON."""
        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = None

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = await gardener._handle_tool("get_note", {"note_id": "nonexistent-id"})

        parsed = json.loads(result)
        assert "error" in parsed
        assert "nonexistent-id" in parsed["error"]

    @pytest.mark.asyncio
    async def test_create_note_tool_dispatches_to_handler(self, tmp_path):
        """_handle_tool('create_note', ...) routes to _handle_create_note,
        creating a file in _processed/ and returning a success JSON."""
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=None,
            embed_client=None,
        )
        result = await gardener._handle_tool(
            "create_note",
            {"type": "fact", "title": "A Dispatched Fact", "body": "Some body text."},
        )

        parsed = json.loads(result)
        assert "created" in parsed
        assert "note_id" in parsed
        # File should exist on disk
        created_files = list((tmp_path / "_processed").rglob("*.md"))
        assert len(created_files) == 1

    @pytest.mark.asyncio
    async def test_patch_edges_tool_dispatches_to_handler(self, tmp_path):
        """_handle_tool('patch_edges', ...) routes to _handle_patch_edges.
        When the note doesn't exist, it returns an error JSON."""
        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = None

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = await gardener._handle_tool(
            "patch_edges",
            {"note_id": "missing-note", "edges": {"related": ["other-note"]}},
        )

        parsed = json.loads(result)
        assert "error" in parsed
        assert "missing-note" in parsed["error"]

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_json(self, tmp_path):
        """_handle_tool returns an error JSON for unrecognised tool names
        rather than raising an exception."""
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=None,
            embed_client=None,
        )
        result = await gardener._handle_tool("frobnicate", {"key": "value"})

        parsed = json.loads(result)
        assert "error" in parsed
        assert "unknown tool" in parsed["error"]
        assert "frobnicate" in parsed["error"]

    @pytest.mark.asyncio
    async def test_handle_tool_catches_handler_exception_and_returns_error_json(
        self, tmp_path
    ):
        """If a tool handler raises internally, _handle_tool catches it and
        returns an error JSON — the tool-use loop can continue."""
        mock_store = MagicMock()
        mock_store.session.execute.side_effect = RuntimeError("DB is down")

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = await gardener._handle_tool("get_note", {"note_id": "any"})

        parsed = json.loads(result)
        assert "error" in parsed
