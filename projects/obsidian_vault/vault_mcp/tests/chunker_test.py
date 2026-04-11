"""Tests for markdown-aware chunker."""

from __future__ import annotations

from projects.obsidian_vault.vault_mcp.app.chunker import chunk_markdown


class TestChunkMarkdown:
    def test_single_paragraph_returns_one_chunk(self):
        chunks = chunk_markdown(
            content="Hello world, this is a short note.",
            content_hash="abc123",
            source_url="vault://note.md",
            title="note.md",
        )
        assert len(chunks) == 1
        assert chunks[0]["chunk_text"] == "Hello world, this is a short note."
        assert chunks[0]["source_url"] == "vault://note.md"
        assert chunks[0]["content_hash"] == "abc123"
        assert chunks[0]["chunk_index"] == 0

    def test_splits_on_headers(self):
        content = "# Section 1\n\nFirst body.\n\n## Section 2\n\nSecond body."
        chunks = chunk_markdown(
            content=content,
            content_hash="def456",
            source_url="vault://doc.md",
            title="doc.md",
        )
        assert len(chunks) == 2
        assert chunks[0]["section_header"] == "# Section 1"
        assert "First body" in chunks[0]["chunk_text"]
        assert chunks[1]["section_header"] == "## Section 2"
        assert "Second body" in chunks[1]["chunk_text"]

    def test_preserves_code_blocks(self):
        content = "# Code\n\n```python\ndef foo():\n    return 42\n```\n\nAfter code."
        chunks = chunk_markdown(
            content=content,
            content_hash="ghi789",
            source_url="vault://code.md",
            title="code.md",
        )
        full_text = " ".join(c["chunk_text"] for c in chunks)
        assert "def foo():" in full_text
        assert "return 42" in full_text

    def test_merges_small_chunks(self):
        content = "# A\n\nTiny.\n\nAlso tiny."
        chunks = chunk_markdown(
            content=content,
            content_hash="jkl012",
            source_url="vault://small.md",
            title="small.md",
            min_tokens=100,
        )
        assert len(chunks) == 1

    def test_respects_max_tokens(self):
        long_body = "word " * 600
        content = f"# Long\n\n{long_body}"
        chunks = chunk_markdown(
            content=content,
            content_hash="mno345",
            source_url="vault://long.md",
            title="long.md",
            max_tokens=512,
        )
        assert len(chunks) >= 2

    def test_empty_content(self):
        chunks = chunk_markdown(
            content="",
            content_hash="empty",
            source_url="vault://empty.md",
            title="empty.md",
        )
        assert chunks == []

    def test_title_field_set(self):
        chunks = chunk_markdown(
            content="# Hello\n\nWorld",
            content_hash="abc",
            source_url="vault://hello.md",
            title="hello.md",
        )
        assert chunks[0]["title"] == "hello.md"

    def test_h4_header_not_a_split_boundary(self):
        """H4+ headers are NOT section boundaries — they stay in the parent body."""
        content = "# Main\n\nIntro body.\n\n#### Detail\n\nDetail body."
        chunks = chunk_markdown(
            content=content,
            content_hash="h4test",
            source_url="vault://h4.md",
            title="h4.md",
        )
        # h4 never splits; everything under "# Main" is one section
        assert len(chunks) == 1
        assert chunks[0]["section_header"] == "# Main"
        assert "#### Detail" in chunks[0]["chunk_text"]
        assert "Detail body." in chunks[0]["chunk_text"]

    def test_chunk_indices_are_sequential_starting_at_zero(self):
        """chunk_index is sequential, starting at 0, across all output chunks."""
        content = "# A\n\nSection A.\n\n## B\n\nSection B.\n\n### C\n\nSection C."
        chunks = chunk_markdown(
            content=content,
            content_hash="seq",
            source_url="vault://seq.md",
            title="seq.md",
        )
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_whitespace_only_content_returns_empty(self):
        """Content that is only whitespace/newlines returns an empty list."""
        chunks = chunk_markdown(
            content="   \n\n\t  \n",
            content_hash="ws",
            source_url="vault://ws.md",
            title="ws.md",
        )
        assert chunks == []

    def test_all_chunk_payload_keys_present(self):
        """Every returned chunk contains all six required ChunkPayload keys."""
        chunks = chunk_markdown(
            content="# Key Test\n\nBody text for key coverage.",
            content_hash="keys",
            source_url="vault://keys.md",
            title="keys.md",
        )
        assert len(chunks) >= 1
        required = {"content_hash", "chunk_index", "chunk_text", "section_header", "source_url", "title"}
        for chunk in chunks:
            assert required == set(chunk.keys())
