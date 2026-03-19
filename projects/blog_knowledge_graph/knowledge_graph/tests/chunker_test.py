"""Tests for markdown-aware chunking."""

from projects.blog_knowledge_graph.knowledge_graph.app.chunker import (
    chunk_markdown,
    _estimate_tokens,
    _split_by_headers,
    _split_paragraphs,
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

    def test_empty_content_returns_no_chunks(self):
        """chunk_markdown on empty string returns an empty list."""
        chunks = chunk_markdown(
            content="",
            content_hash="abc",
            source_url="https://example.com",
            source_type="html",
            title="Empty",
        )
        assert chunks == []

    def test_section_header_stored_in_chunk(self):
        """Each chunk carries the section_header from the markdown heading."""
        content = "## Overview\n\nSome overview text."
        chunks = chunk_markdown(
            content=content,
            content_hash="h1",
            source_url="https://example.com",
            source_type="html",
            title="T",
        )
        assert len(chunks) >= 1
        assert chunks[0]["section_header"] == "## Overview"

    def test_content_without_any_headers(self):
        """Content with no headers is treated as a single unlabelled section."""
        content = "Just plain prose with no headings at all."
        chunks = chunk_markdown(
            content=content,
            content_hash="nohdr",
            source_url="https://example.com",
            source_type="html",
            title="T",
        )
        assert len(chunks) == 1
        assert chunks[0]["section_header"] == ""
        assert "plain prose" in chunks[0]["chunk_text"]

    def test_large_section_splits_into_multiple_chunks(self):
        """A section whose body exceeds max_tokens is split at paragraph boundaries."""
        # Build a body with two well-separated paragraphs, each > 30 tokens
        para1 = "Alpha " * 40  # ~52 tokens
        para2 = "Beta " * 40  # ~52 tokens
        content = f"# Big Section\n\n{para1}\n\n{para2}"
        chunks = chunk_markdown(
            content=content,
            content_hash="big",
            source_url="https://example.com",
            source_type="html",
            title="T",
            max_tokens=60,
            min_tokens=1,
        )
        # Both paragraphs together exceed max_tokens=60, so they should end up
        # in separate chunks.
        assert len(chunks) >= 2

    def test_author_none_by_default(self):
        """author defaults to None when not provided."""
        chunks = chunk_markdown(
            content="# H\n\nText.",
            content_hash="x",
            source_url="https://example.com",
            source_type="html",
            title="T",
        )
        assert chunks[0]["author"] is None

    def test_published_at_none_by_default(self):
        """published_at defaults to None when not provided."""
        chunks = chunk_markdown(
            content="# H\n\nText.",
            content_hash="x",
            source_url="https://example.com",
            source_type="html",
            title="T",
        )
        assert chunks[0]["published_at"] is None


class TestSplitParagraphs:
    """Direct tests for the _split_paragraphs helper."""

    def test_empty_text_returns_empty_list(self):
        result = _split_paragraphs("", max_tokens=512)
        assert result == []

    def test_single_paragraph_under_limit(self):
        result = _split_paragraphs("Hello world.", max_tokens=512)
        assert len(result) == 1
        assert "Hello world." in result[0]

    def test_two_paragraphs_under_limit_kept_together(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _split_paragraphs(text, max_tokens=512)
        assert len(result) == 1
        assert "First paragraph." in result[0]
        assert "Second paragraph." in result[0]

    def test_two_large_paragraphs_split(self):
        """Two paragraphs that together exceed max_tokens become separate chunks."""
        para1 = "Word " * 50  # ~65 tokens
        para2 = "Thing " * 50  # ~65 tokens
        text = f"{para1}\n\n{para2}"
        result = _split_paragraphs(text, max_tokens=70)
        assert len(result) >= 2

    def test_code_block_kept_as_single_part(self):
        """A fenced code block is emitted as a single atomic paragraph."""
        text = "Intro text.\n\n```python\ndef foo():\n    pass\n```\n\nAfter."
        result = _split_paragraphs(text, max_tokens=512)
        # The code block must not be split
        code_results = [r for r in result if "def foo" in r]
        assert len(code_results) == 1
        assert "pass" in code_results[0]

    def test_unclosed_code_block_treated_as_single_part(self):
        """An unclosed ``` block is kept together rather than discarded."""
        text = "Preamble.\n\n```bash\necho hello\nno closing fence"
        result = _split_paragraphs(text, max_tokens=512)
        # All content should appear somewhere in the output
        combined = "\n".join(result)
        assert "echo hello" in combined

    def test_blank_lines_do_not_create_empty_chunks(self):
        """Multiple consecutive blank lines produce no spurious empty chunks."""
        text = "Para one.\n\n\n\nPara two."
        result = _split_paragraphs(text, max_tokens=512)
        for chunk in result:
            assert chunk.strip() != ""
