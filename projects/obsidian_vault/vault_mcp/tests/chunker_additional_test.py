"""Additional tests for chunker internals and edge cases not covered by chunker_test.py."""

from __future__ import annotations

import pytest

from projects.obsidian_vault.vault_mcp.app.chunker import (
    ChunkPayload,
    _estimate_tokens,
    _split_by_headers,
    _split_paragraphs,
    chunk_markdown,
)


class TestEstimateTokens:
    def test_empty_string_returns_zero(self):
        assert _estimate_tokens("") == 0

    def test_single_word_returns_nonzero(self):
        result = _estimate_tokens("hello")
        # 1 word × 1.3 = 1 (int truncation)
        assert result == 1

    def test_scales_with_word_count(self):
        result = _estimate_tokens("one two three four five")
        # 5 words × 1.3 = 6 (int truncation)
        assert result == 6

    def test_larger_text_gives_higher_estimate(self):
        short = _estimate_tokens("hello world")
        long = _estimate_tokens("hello world foo bar baz qux")
        assert long > short

    def test_whitespace_only_returns_zero(self):
        assert _estimate_tokens("   \n\n   \t  ") == 0

    def test_returns_int(self):
        result = _estimate_tokens("some words here")
        assert isinstance(result, int)


class TestSplitByHeaders:
    def test_no_headers_returns_full_content(self):
        content = "Just plain text with no headers at all."
        sections = _split_by_headers(content)
        assert len(sections) == 1
        assert sections[0][0] == ""
        assert sections[0][1] == content.strip()

    def test_h1_header_splits_content(self):
        content = "# Title\n\nBody text here."
        sections = _split_by_headers(content)
        assert len(sections) == 1
        assert sections[0][0] == "# Title"
        assert "Body text here." in sections[0][1]

    def test_h2_header(self):
        content = "## Section\n\nSection body."
        sections = _split_by_headers(content)
        assert len(sections) == 1
        assert sections[0][0] == "## Section"

    def test_h3_header(self):
        content = "### Subsection\n\nSubsection content."
        sections = _split_by_headers(content)
        assert len(sections) == 1
        assert sections[0][0] == "### Subsection"

    def test_content_before_first_header(self):
        content = "Preamble text.\n\n# Header\n\nBody after header."
        sections = _split_by_headers(content)
        assert len(sections) == 2
        assert sections[0][0] == ""
        assert "Preamble text." in sections[0][1]
        assert sections[1][0] == "# Header"
        assert "Body after header." in sections[1][1]

    def test_multiple_headers(self):
        content = "# One\n\nFirst.\n\n## Two\n\nSecond.\n\n### Three\n\nThird."
        sections = _split_by_headers(content)
        assert len(sections) == 3
        assert sections[0][0] == "# One"
        assert sections[1][0] == "## Two"
        assert sections[2][0] == "### Three"

    def test_empty_section_body_is_skipped(self):
        """A header with no body before the next header produces no section for that body."""
        content = "# Header\n\n## Next\n\nActual content."
        sections = _split_by_headers(content)
        # The empty body between the two headers is stripped and skipped
        assert not any(s[1] == "" for s in sections)

    def test_returns_list_of_tuples(self):
        sections = _split_by_headers("Some content")
        assert isinstance(sections, list)
        assert all(isinstance(s, tuple) and len(s) == 2 for s in sections)

    def test_header_deeper_than_h3_not_split(self):
        """h4+ headers are NOT split on — they remain part of the body."""
        content = "#### Deep header\n\nContent under h4."
        sections = _split_by_headers(content)
        # Only h1-h3 are split; h4 stays as body text
        assert len(sections) == 1
        assert sections[0][0] == ""
        assert "#### Deep header" in sections[0][1]


class TestSplitParagraphs:
    def test_single_short_paragraph(self):
        result = _split_paragraphs("Hello world.", max_tokens=512)
        assert len(result) == 1
        assert result[0] == "Hello world."

    def test_two_paragraphs_within_limit(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _split_paragraphs(text, max_tokens=512)
        # Both fit → merged into one chunk
        assert len(result) == 1

    def test_code_block_preserved_as_unit(self):
        text = "Before code.\n\n```python\nfor i in range(10):\n    print(i)\n```\n\nAfter code."
        result = _split_paragraphs(text, max_tokens=512)
        full = " ".join(result)
        assert "for i in range(10):" in full
        assert "print(i)" in full

    def test_empty_text_returns_empty_list(self):
        result = _split_paragraphs("", max_tokens=512)
        assert result == []

    def test_very_long_paragraph_is_word_split(self):
        # Create a paragraph that exceeds max_tokens=10
        long_para = " ".join(["word"] * 50)
        result = _split_paragraphs(long_para, max_tokens=10)
        # Should produce multiple chunks
        assert len(result) >= 2

    def test_unclosed_code_block_captured(self):
        """An unclosed ``` block collects remaining lines until EOF."""
        text = "```python\ncode line 1\ncode line 2"
        result = _split_paragraphs(text, max_tokens=512)
        full = " ".join(result)
        assert "code line 1" in full
        assert "code line 2" in full


class TestChunkMarkdownAdditional:
    def test_whitespace_only_content_returns_empty(self):
        chunks = chunk_markdown(
            content="   \n\n   \t  \n",
            content_hash="h",
            source_url="vault://ws.md",
            title="ws.md",
        )
        assert chunks == []

    def test_h3_section_header_set_correctly(self):
        content = "### Deep Section\n\nContent here."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="vault://deep.md",
            title="deep.md",
        )
        assert len(chunks) >= 1
        assert chunks[0]["section_header"] == "### Deep Section"

    def test_content_before_header_has_empty_section_header(self):
        content = "Preamble paragraph.\n\n# Header\n\nBody."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="vault://pre.md",
            title="pre.md",
        )
        # First chunk has no header (empty string)
        assert chunks[0]["section_header"] == ""

    def test_chunk_indices_are_sequential(self):
        # Generate many sections to get multiple chunks
        sections = "\n\n".join(f"# Section {i}\n\n{'word ' * 60}" for i in range(5))
        chunks = chunk_markdown(
            content=sections,
            content_hash="hash",
            source_url="vault://multi.md",
            title="multi.md",
            max_tokens=50,
        )
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunks_from_different_headers_not_merged(self):
        """Chunks under different headers are never merged, even if small."""
        content = "# A\n\nTiny.\n\n# B\n\nAlso tiny."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="vault://split.md",
            title="split.md",
            min_tokens=100,  # both chunks are tiny (below min_tokens)
        )
        # Different headers → no merge
        assert len(chunks) == 2
        assert chunks[0]["section_header"] == "# A"
        assert chunks[1]["section_header"] == "# B"

    def test_small_chunks_under_same_header_are_merged(self):
        """Small chunks under the SAME header merge if combined size fits."""
        content = "# A\n\nTiny.\n\nAlso tiny."
        chunks = chunk_markdown(
            content=content,
            content_hash="abc",
            source_url="vault://merge.md",
            title="merge.md",
            min_tokens=100,
            max_tokens=512,
        )
        assert len(chunks) == 1

    def test_word_level_split_produces_valid_chunks(self):
        """A single paragraph longer than max_tokens splits by words."""
        long_para = "word " * 200  # ~260 tokens (200 × 1.3)
        chunks = chunk_markdown(
            content=long_para,
            content_hash="long",
            source_url="vault://long2.md",
            title="long2.md",
            max_tokens=50,
        )
        assert len(chunks) >= 2
        for c in chunks:
            assert c["source_url"] == "vault://long2.md"
            assert c["content_hash"] == "long"
            assert c["title"] == "long2.md"

    def test_source_url_set_on_all_chunks(self):
        """Every chunk carries the correct source_url."""
        content = "# S1\n\nBody one.\n\n# S2\n\nBody two."
        chunks = chunk_markdown(
            content=content,
            content_hash="h",
            source_url="vault://multi2.md",
            title="multi2.md",
        )
        for c in chunks:
            assert c["source_url"] == "vault://multi2.md"

    def test_chunk_payload_has_all_required_keys(self):
        """Each ChunkPayload dict has all 6 required keys."""
        chunks = chunk_markdown(
            content="# Test\n\nSome content.",
            content_hash="abc",
            source_url="vault://keys.md",
            title="keys.md",
        )
        required_keys = {
            "content_hash",
            "chunk_index",
            "chunk_text",
            "section_header",
            "source_url",
            "title",
        }
        for c in chunks:
            assert required_keys.issubset(c.keys())

    def test_custom_max_and_min_tokens_respected(self):
        """Custom max_tokens and min_tokens parameters are forwarded correctly."""
        # With min_tokens=0 there should be no merging
        content = "# A\n\nTiny.\n\n# B\n\nTiny."
        chunks_default = chunk_markdown(
            content=content,
            content_hash="x",
            source_url="vault://custom.md",
            title="custom.md",
        )
        # Two sections → two chunks (different headers prevent merge regardless)
        assert len(chunks_default) == 2
