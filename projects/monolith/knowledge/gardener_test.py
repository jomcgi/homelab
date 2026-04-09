"""Tests for the knowledge gardener."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.gardener import (
    Gardener,
    GardenStats,
    _is_error_result,
    _slugify,
    _split_frontmatter,
)


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestDiscoverRawFiles:
    def test_finds_md_files_outside_processed_and_deleted(self, tmp_path):
        _write(tmp_path, "inbox/new-note.md", "---\ntitle: New\n---\nBody.")
        _write(tmp_path, "_processed/existing.md", "---\nid: e\ntitle: E\n---\nBody.")
        _write(
            tmp_path,
            "_deleted_with_ttl/old.md",
            "---\nttl: 2026-01-01T00:00:00Z\n---\nBody.",
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        raw = gardener._discover_raw_files()
        assert len(raw) == 1
        assert raw[0].name == "new-note.md"

    def test_ignores_non_md_files(self, tmp_path):
        _write(tmp_path, "inbox/image.png", "not markdown")
        _write(tmp_path, "inbox/note.md", "---\ntitle: Note\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        raw = gardener._discover_raw_files()
        assert len(raw) == 1

    def test_ignores_dotfiles_and_dot_directories(self, tmp_path):
        _write(tmp_path, ".obsidian/config.md", "config")
        _write(tmp_path, "inbox/.hidden.md", "hidden")
        _write(tmp_path, "inbox/visible.md", "---\ntitle: V\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        raw = gardener._discover_raw_files()
        assert len(raw) == 1


class TestMaxFilesPerRun:
    @pytest.mark.asyncio
    async def test_cap_limits_ingest_to_max_files(self, tmp_path):
        """run() processes at most max_files_per_run raw files per cycle,
        leaving the remainder for a future tick."""
        for i in range(5):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody {i}.")
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=None,
            embed_client=None,
            max_files_per_run=2,
        )
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()
        assert len(calls) == 2
        assert stats.ingested == 2
        assert stats.failed == 0
        # The remaining 3 files must still be on disk waiting for the next tick.
        remaining = sorted(
            p.name for p in (tmp_path / "inbox").glob("*.md") if p.is_file()
        )
        assert len(remaining) == 5  # fake ingest doesn't soft-delete

    @pytest.mark.asyncio
    async def test_cap_disabled_when_zero_or_negative(self, tmp_path):
        """max_files_per_run <= 0 disables the cap."""
        for i in range(3):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=None,
            embed_client=None,
            max_files_per_run=0,
        )
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()
        assert len(calls) == 3
        assert stats.ingested == 3


class TestTtlCleanup:
    def test_deletes_expired_files(self, tmp_path):
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _write(
            tmp_path, "_deleted_with_ttl/old.md", f'---\nttl: "{expired}"\n---\nBody.'
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "old.md").exists()

    def test_keeps_non_expired_files(self, tmp_path):
        future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
        _write(
            tmp_path, "_deleted_with_ttl/recent.md", f'---\nttl: "{future}"\n---\nBody.'
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0
        assert (tmp_path / "_deleted_with_ttl" / "recent.md").exists()

    def test_handles_missing_ttl_frontmatter(self, tmp_path):
        _write(tmp_path, "_deleted_with_ttl/no-ttl.md", "---\ntitle: Oops\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        # No ttl = don't delete (conservative)
        assert cleaned == 0

    def test_handles_empty_deleted_dir(self, tmp_path):
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0

    def test_treats_naive_expired_datetime_as_utc(self, tmp_path):
        # Naive ISO datetime in the past (no tz suffix)
        expired_naive = (
            (datetime.now(timezone.utc) - timedelta(hours=1))
            .replace(tzinfo=None)
            .isoformat()
        )
        _write(
            tmp_path,
            "_deleted_with_ttl/naive.md",
            f'---\nttl: "{expired_naive}"\n---\nBody.',
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "naive.md").exists()

    def test_skips_corrupt_ttl_but_cleans_expired_sibling(self, tmp_path):
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _write(
            tmp_path,
            "_deleted_with_ttl/valid.md",
            f'---\nttl: "{expired}"\n---\nValid.',
        )
        _write(
            tmp_path,
            "_deleted_with_ttl/corrupt.md",
            "---\nttl: not-a-datetime\n---\nCorrupt.",
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "valid.md").exists()
        assert (tmp_path / "_deleted_with_ttl" / "corrupt.md").exists()


class TestSoftDelete:
    def test_moves_file_with_existing_frontmatter_and_injects_ttl(self, tmp_path):
        _write(
            tmp_path,
            "inbox/note.md",
            "---\ntitle: Hello\ntags: [a, b]\n---\nBody text.\n",
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        source = tmp_path / "inbox" / "note.md"
        gardener._soft_delete(source)

        assert not source.exists()
        dest = tmp_path / "_deleted_with_ttl" / "inbox" / "note.md"
        assert dest.exists()
        content = dest.read_text()
        assert "ttl:" in content
        assert "title: Hello" in content
        # Body preserved
        assert "Body text." in content

    def test_adds_frontmatter_to_file_without_any(self, tmp_path):
        _write(tmp_path, "inbox/plain.md", "Just body, no frontmatter.\n")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        source = tmp_path / "inbox" / "plain.md"
        gardener._soft_delete(source)

        dest = tmp_path / "_deleted_with_ttl" / "inbox" / "plain.md"
        assert dest.exists()
        content = dest.read_text()
        assert content.startswith("---\n")
        assert "ttl:" in content
        assert "Just body, no frontmatter." in content

    def test_overwrites_existing_ttl(self, tmp_path):
        """If the file already has a ttl (e.g. already soft-deleted), new ttl wins."""
        old_ttl = "2020-01-01T00:00:00+00:00"
        _write(
            tmp_path,
            "inbox/retry.md",
            f'---\nttl: "{old_ttl}"\ntitle: X\n---\nBody.\n',
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        source = tmp_path / "inbox" / "retry.md"
        gardener._soft_delete(source)

        dest = tmp_path / "_deleted_with_ttl" / "inbox" / "retry.md"
        content = dest.read_text()
        # Old ttl must not be present
        assert old_ttl not in content
        assert "ttl:" in content
        assert content.count("ttl:") == 1


def _make_mock_anthropic(tool_use_responses):
    """Create a mock anthropic client that returns canned tool-use responses.

    tool_use_responses is a list of responses. The gardener loop calls the API
    repeatedly until it gets a response with stop_reason='end_turn'.
    """
    client = MagicMock()
    call_idx = {"n": 0}

    def create(**kwargs):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(tool_use_responses):
            return tool_use_responses[idx]
        # Final response — no more tool use
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = []
        return resp

    client.messages.create = create
    return client


class TestIngestOne:
    @pytest.mark.asyncio
    async def test_creates_note_files_from_tool_calls(self, tmp_path):
        """Sonnet tool-use creates typed notes in _processed/."""
        _write(
            tmp_path,
            "inbox/raw.md",
            "---\ntitle: Kubernetes Networking\n---\nCNI plugins handle pod networking.",
        )

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "call_1"
        tool_block.name = "create_note"
        tool_block.input = {
            "type": "atom",
            "title": "CNI plugins handle pod networking",
            "tags": ["kubernetes", "networking"],
            "edges": {},
            "body": "In Kubernetes, Container Network Interface (CNI) plugins are responsible for pod-to-pod networking.",
        }
        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [tool_block]

        mock_client = _make_mock_anthropic([resp])

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=mock_client,
            store=None,
            embed_client=None,
        )
        await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        created = list((tmp_path / "_processed").rglob("*.md"))
        assert len(created) == 1
        content = created[0].read_text()
        assert "type: atom" in content
        assert "CNI plugins handle pod networking" in content

    @pytest.mark.asyncio
    async def test_soft_deletes_raw_file_after_successful_ingest(self, tmp_path):
        """After successful ingest (at least one create_note), raw file moves to _deleted_with_ttl/."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        create_block = MagicMock()
        create_block.type = "tool_use"
        create_block.id = "c1"
        create_block.name = "create_note"
        create_block.input = {"type": "atom", "title": "Test", "body": "Body."}
        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [create_block]

        mock_client = _make_mock_anthropic([resp])
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=mock_client,
            store=None,
            embed_client=None,
        )
        await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        assert not (tmp_path / "inbox" / "raw.md").exists()
        deleted = list((tmp_path / "_deleted_with_ttl").rglob("*.md"))
        assert len(deleted) == 1
        content = deleted[0].read_text()
        assert "ttl:" in content

    @pytest.mark.asyncio
    async def test_does_not_soft_delete_when_no_notes_created(self, tmp_path):
        """If Sonnet returns end_turn without calling create_note, keep the raw file."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = []

        mock_client = _make_mock_anthropic([resp])
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=mock_client,
            store=None,
            embed_client=None,
        )
        await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        assert (tmp_path / "inbox" / "raw.md").exists()  # still there
        assert not (tmp_path / "_deleted_with_ttl").exists() or not list(
            (tmp_path / "_deleted_with_ttl").rglob("*.md")
        )

    @pytest.mark.asyncio
    async def test_raises_on_max_turns_exhaustion(self, tmp_path):
        """If the tool-use loop runs forever, raise and leave the raw file in place."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        # A mock that ALWAYS returns tool_use — infinite loop until max_turns.
        loop_block = MagicMock()
        loop_block.type = "tool_use"
        loop_block.id = "call_loop"
        loop_block.name = "search_notes"
        loop_block.input = {"query": "anything"}
        loop_resp = MagicMock()
        loop_resp.stop_reason = "tool_use"
        loop_resp.content = [loop_block]

        client = MagicMock()
        client.messages.create = MagicMock(return_value=loop_resp)

        mock_store = MagicMock()
        mock_store.search_notes.return_value = []
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.0] * 1024

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=client,
            store=mock_store,
            embed_client=mock_embed,
        )
        with pytest.raises(RuntimeError, match="max_turns"):
            await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        # Raw file survives
        assert (tmp_path / "inbox" / "raw.md").exists()

    @pytest.mark.asyncio
    async def test_multi_turn_loop_accumulates_messages(self, tmp_path):
        """Verify messages append correctly across multiple tool-use turns."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody content.")

        # Turn 1: search_notes
        search_block = MagicMock()
        search_block.type = "tool_use"
        search_block.id = "c1"
        search_block.name = "search_notes"
        search_block.input = {"query": "test"}
        turn1 = MagicMock()
        turn1.stop_reason = "tool_use"
        turn1.content = [search_block]

        # Turn 2: create_note
        create_block = MagicMock()
        create_block.type = "tool_use"
        create_block.id = "c2"
        create_block.name = "create_note"
        create_block.input = {
            "type": "fact",
            "title": "Body content",
            "body": "Body content.",
        }
        turn2 = MagicMock()
        turn2.stop_reason = "tool_use"
        turn2.content = [create_block]

        mock_client = _make_mock_anthropic([turn1, turn2])

        mock_store = MagicMock()
        mock_store.search_notes.return_value = []
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.0] * 1024

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=mock_client,
            store=mock_store,
            embed_client=mock_embed,
        )
        await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        # Note was created, raw was soft-deleted
        assert len(list((tmp_path / "_processed").rglob("*.md"))) == 1
        assert not (tmp_path / "inbox" / "raw.md").exists()

    @pytest.mark.asyncio
    async def test_handles_missing_anthropic_client(self, tmp_path):
        """Running the ingest without a configured client raises."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: T\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        with pytest.raises(RuntimeError, match="anthropic_client"):
            await gardener._ingest_one(tmp_path / "inbox" / "raw.md")


class TestSearchNotesTool:
    @pytest.mark.asyncio
    async def test_search_tool_returns_results(self, tmp_path):
        """The search_notes tool handler queries the store and returns results."""
        mock_store = MagicMock()
        mock_store.search_notes.return_value = [
            {
                "note_id": "a",
                "title": "Existing Note",
                "path": "_processed/a.md",
                "score": 0.92,
            }
        ]
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.1] * 1024

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=mock_embed,
        )
        result = await gardener._handle_search_notes({"query": "some query"})
        assert "Existing Note" in result
        mock_embed.embed.assert_called_once_with("some query")

    @pytest.mark.asyncio
    async def test_search_tool_returns_error_when_unavailable(self, tmp_path):
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        result = await gardener._handle_search_notes({"query": "x"})
        assert "error" in result
        assert "unavailable" in result


class TestCreateNoteTool:
    def test_creates_file_with_frontmatter(self, tmp_path):
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        result = gardener._handle_create_note(
            {
                "type": "atom",
                "title": "Pod Networking",
                "tags": ["k8s"],
                "edges": {"related": ["abc123"]},
                "body": "CNI plugins handle it.",
            }
        )
        assert "created" in result
        files = list((tmp_path / "_processed").rglob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "type: atom" in content
        assert "title: Pod Networking" in content
        assert "id: pod-networking" in content
        assert "CNI plugins handle it." in content

    def test_collision_appends_counter(self, tmp_path):
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        gardener._handle_create_note({"type": "atom", "title": "Same", "body": "first"})
        gardener._handle_create_note(
            {"type": "atom", "title": "Same", "body": "second"}
        )
        files = sorted((tmp_path / "_processed").rglob("*.md"))
        assert len(files) == 2
        assert files[0].name == "same-1.md"
        assert files[1].name == "same.md"


class TestPatchEdgesTool:
    def test_preserves_created_and_updated_timestamps(self, tmp_path):
        """Regression test: patch_edges must not drop created/updated frontmatter."""
        note_path = tmp_path / "_processed" / "target.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text(
            "---\n"
            "id: target\n"
            "title: Target Note\n"
            "type: atom\n"
            "created: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-02-01T00:00:00+00:00\n"
            "---\n"
            "Original body.\n"
        )

        # Mock the store lookup
        mock_note = MagicMock()
        mock_note.note_id = "target"
        mock_note.path = "_processed/target.md"
        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = (
            mock_note
        )

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = gardener._handle_patch_edges(
            {
                "note_id": "target",
                "edges": {"related": ["other-note"]},
            }
        )
        assert "patched" in result

        updated_content = note_path.read_text()
        assert (
            "created: '2026-01-01T00:00:00+00:00'" in updated_content
            or "created: 2026-01-01T00:00:00+00:00" in updated_content
        )
        assert "updated:" in updated_content
        assert "related:" in updated_content
        assert "other-note" in updated_content

    def test_rejects_unknown_edge_types(self, tmp_path):
        """patch_edges should return an error for unknown edge type names."""
        mock_store = MagicMock()
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = gardener._handle_patch_edges(
            {
                "note_id": "target",
                "edges": {"nonsense_edge_type": ["x"]},
            }
        )
        assert "error" in result
        assert "unknown edge types" in result
        # Store should not even have been queried
        mock_store.session.execute.assert_not_called()

    def test_merges_edges_with_existing(self, tmp_path):
        """patch_edges dedupes and preserves order when merging edges."""
        note_path = tmp_path / "_processed" / "target.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text(
            "---\n"
            "id: target\n"
            "title: Target\n"
            "type: atom\n"
            "edges:\n"
            "  related:\n"
            "    - existing-a\n"
            "    - existing-b\n"
            "---\n"
            "Body.\n"
        )
        mock_note = MagicMock()
        mock_note.note_id = "target"
        mock_note.path = "_processed/target.md"
        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = (
            mock_note
        )

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        gardener._handle_patch_edges(
            {
                "note_id": "target",
                "edges": {"related": ["existing-b", "new-c"]},  # b is dup, c is new
            }
        )

        updated = note_path.read_text()
        # Expect order: existing-a, existing-b, new-c (dedupe preserves order)
        assert "existing-a" in updated
        assert "existing-b" in updated
        assert "new-c" in updated
        # Count occurrences of existing-b to ensure no dupe
        assert updated.count("existing-b") == 1


class TestIsErrorResult:
    def test_valid_error_json_returns_true(self):
        """_is_error_result returns True for JSON with an 'error' key."""
        import json

        assert _is_error_result(json.dumps({"error": "something went wrong"})) is True

    def test_valid_non_error_json_returns_false(self):
        """_is_error_result returns False for JSON without an 'error' key."""
        import json

        assert (
            _is_error_result(json.dumps({"created": "note.md", "note_id": "test"}))
            is False
        )

    def test_invalid_json_returns_false(self):
        """_is_error_result returns False when the input is not valid JSON."""
        assert _is_error_result("this is not json {{{") is False

    def test_none_input_returns_false(self):
        """_is_error_result returns False when the input is None (TypeError is swallowed)."""
        assert _is_error_result(None) is False  # type: ignore[arg-type]


class TestSlugify:
    def test_ascii_text(self):
        """_slugify converts plain ASCII text to a lowercased hyphen-separated slug."""
        assert _slugify("Hello World") == "hello-world"

    def test_unicode_text(self):
        """_slugify strips non-ASCII characters after NFKD decomposition."""
        # 'é' decomposes to 'e' + combining accent; the accent is dropped by ascii encode.
        assert _slugify("Café Notes") == "cafe-notes"

    def test_empty_string_returns_note(self):
        """_slugify returns the sentinel value 'note' when the slug would be empty."""
        assert _slugify("") == "note"

    def test_special_characters_become_single_hyphens(self):
        """_slugify collapses runs of non-alphanumeric characters into a single hyphen."""
        assert _slugify("foo: bar/baz!qux") == "foo-bar-baz-qux"


class TestSplitFrontmatter:
    def test_valid_frontmatter_splits_correctly(self):
        """_split_frontmatter returns parsed meta dict and body for a well-formed file."""
        raw = "---\ntitle: My Note\ntype: atom\n---\nBody text.\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {"title": "My Note", "type": "atom"}
        assert body == "Body text.\n"

    def test_no_frontmatter_returns_empty_dict_and_full_raw(self):
        """_split_frontmatter returns ({}, raw) when there is no opening '---'."""
        raw = "Just a plain body with no frontmatter.\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_unclosed_frontmatter_returns_empty_dict_and_full_raw(self):
        """_split_frontmatter returns ({}, raw) when the closing '---' is missing."""
        raw = "---\ntitle: Broken\nno closing delimiter\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_non_dict_yaml_returns_empty_dict_and_full_raw(self):
        """_split_frontmatter returns ({}, raw) when the YAML block is a list, not a dict."""
        raw = "---\n- item1\n- item2\n---\nBody.\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_invalid_yaml_returns_empty_dict_and_full_raw(self):
        """_split_frontmatter returns ({}, raw) when the YAML block is syntactically invalid."""
        raw = "---\n}\n---\nBody.\n"  # '}' outside a flow mapping is a parse error
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw


class TestGetNoteTool:
    def test_happy_path_returns_file_content(self, tmp_path):
        """_handle_get_note returns the raw file content when note and file both exist."""
        note_path = tmp_path / "_processed" / "my-note.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text(
            "---\nid: my-note\ntitle: My Note\n---\nBody content.", encoding="utf-8"
        )

        mock_note = MagicMock()
        mock_note.note_id = "my-note"
        mock_note.path = "_processed/my-note.md"
        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = (
            mock_note
        )

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = gardener._handle_get_note({"note_id": "my-note"})
        # Raw file content is returned directly (not wrapped in JSON).
        assert "Body content." in result
        assert "My Note" in result

    def test_note_not_found_returns_error_json(self, tmp_path):
        """_handle_get_note returns an error JSON when no Note row matches the note_id."""
        import json

        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = None

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = gardener._handle_get_note({"note_id": "missing-id"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "missing-id" in parsed["error"]
        assert "not found" in parsed["error"]

    def test_file_not_found_returns_error_json(self, tmp_path):
        """_handle_get_note returns an error JSON when the DB row exists but the file is gone."""
        import json

        mock_note = MagicMock()
        mock_note.note_id = "orphan"
        mock_note.path = "_processed/orphan.md"  # file does NOT exist on disk
        mock_store = MagicMock()
        mock_store.session.execute.return_value.scalar_one_or_none.return_value = (
            mock_note
        )

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=None,
        )
        result = gardener._handle_get_note({"note_id": "orphan"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "file not found" in parsed["error"]

    def test_store_unavailable_returns_error_json(self, tmp_path):
        """_handle_get_note returns an error JSON when the store is None."""
        import json

        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        result = gardener._handle_get_note({"note_id": "any"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "store unavailable" in parsed["error"]


class TestHandleTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_json(self, tmp_path):
        """_handle_tool returns a JSON error string for an unrecognised tool name."""
        import json

        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        result = await gardener._handle_tool("does_not_exist", {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "unknown tool" in parsed["error"]
        assert "does_not_exist" in parsed["error"]

    @pytest.mark.asyncio
    async def test_exception_in_handler_caught_and_returned_as_error(self, tmp_path):
        """_handle_tool catches exceptions from a handler and returns an error JSON string."""
        import json

        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        # _handle_create_note raises KeyError for missing required keys.
        result = await gardener._handle_tool("create_note", {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "create_note" in parsed["error"]


class TestRunFailurePath:
    @pytest.mark.asyncio
    async def test_failed_ingest_increments_failed_and_continues(self, tmp_path):
        """run() increments failed when _ingest_one raises and continues with remaining files."""
        for i in range(3):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody {i}.")

        call_order: list[str] = []

        async def fake_ingest(path: Path) -> None:
            call_order.append(path.name)
            if path.name == "note-1.md":
                raise RuntimeError("simulated ingest failure")

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=None,
            embed_client=None,
        )
        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()

        # All three files must have been attempted regardless of the failure.
        assert len(call_order) == 3
        assert stats.failed == 1
        assert stats.ingested == 2
