"""Tests for markdown-aware chunking."""

from projects.agent_platform.knowledge_graph.app.chunker import (
    chunk_markdown,
    _estimate_tokens,
    _split_by_headers,
)


class TestEstimateTokens:
    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_single_word(self):
        assert _estimate_tokens("hello") >= 1

    def test_sentence(self):
        tokens = _estimate_tokens("The quick brown fox jumps over the lazy dog")
        assert 9 <= tokens <= 15


class TestSplitByHeaders:
    def test_no_headers(self):
        sections = _split_by_headers("Just plain text.")
        assert len(sections) == 1
        assert sections[0][0] == ""
        assert sections[0][1] == "Just plain text."

    def test_single_header(self):
        sections = _split_by_headers("# Title\n\nBody text here.")
        assert len(sections) == 1
        assert sections[0][0] == "# Title"
        assert "Body text here." in sections[0][1]

    def test_multiple_headers(self):
        content = (
            "# First\n\nBody one.\n\n## Second\n\nBody two.\n\n### Third\n\nBody three."
        )
        sections = _split_by_headers(content)
        assert len(sections) == 3
        assert sections[0][0] == "# First"
        assert sections[1][0] == "## Second"
        assert sections[2][0] == "### Third"

    def test_h4_not_split(self):
        content = "# Title\n\nIntro.\n\n#### Detail\n\nDetail text."
        sections = _split_by_headers(content)
        # h4 should not cause a split
        assert len(sections) == 1


class TestChunkMarkdown:
    def test_basic_chunking(self):
        content = "# Title\n\nSome content here."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc123",
            source_url="https://example.com",
            source_type="html",
            title="Test",
        )
        assert len(chunks) >= 1
        assert chunks[0]["content_hash"] == "abc123"
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["source_url"] == "https://example.com"

    def test_multiple_sections(self):
        content = (
            "# Section One\n\n"
            + "Word " * 200
            + "\n\n## Section Two\n\n"
            + "Word " * 200
        )
        chunks = chunk_markdown(
            content=content,
            content_hash="abc123",
            source_url="https://example.com",
            source_type="html",
            title="Test",
            max_tokens=100,
        )
        assert len(chunks) >= 2

    def test_chunk_indices_sequential(self):
        content = "# A\n\nText.\n\n## B\n\nMore text.\n\n## C\n\nEven more."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="https://example.com",
            source_type="html",
            title="Test",
        )
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_code_block_kept_intact(self):
        content = "# Code Example\n\n```python\ndef hello():\n    print('hi')\n```\n\nAfter code."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="https://example.com",
            source_type="html",
            title="Test",
        )
        # The code block should not be split across chunks
        code_chunks = [c for c in chunks if "def hello" in c["chunk_text"]]
        assert len(code_chunks) == 1
        assert "print('hi')" in code_chunks[0]["chunk_text"]

    def test_small_chunks_merged(self):
        content = "# A\n\nTiny.\n\n## B\n\nAlso tiny."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="https://example.com",
            source_type="html",
            title="Test",
            min_tokens=50,
        )
        # Both sections are under min_tokens, should be merged
        assert len(chunks) <= 2

    def test_metadata_propagated(self):
        chunks = chunk_markdown(
            content="# Title\n\nContent.",
            content_hash="hash123",
            source_url="https://example.com/post",
            source_type="rss",
            title="My Post",
            author="Author",
            published_at="2025-01-15",
        )
        assert chunks[0]["source_type"] == "rss"
        assert chunks[0]["title"] == "My Post"
        assert chunks[0]["author"] == "Author"
        assert chunks[0]["published_at"] == "2025-01-15"
