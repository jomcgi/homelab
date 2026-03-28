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
