import pytest
from note_parser import NoteParser
from models import Note


@pytest.fixture
def parser():
    """Create a NoteParser instance."""
    return NoteParser()


def test_parse_simple_note(parser):
    """Test parsing a simple note without frontmatter."""
    content = """# Simple Note

This is a simple note with some content.

It has #tag1 and #tag2 hashtags.

And links to [[Other Note]] and [[Another Note|Display Text]].
"""
    
    note = parser.parse_note("simple.md", content)
    
    assert note.path == "simple.md"
    assert note.title == "Simple Note"
    assert note.content == content
    assert "tag1" in note.tags
    assert "tag2" in note.tags
    assert "Other Note" in note.wikilinks
    assert "Another Note|Display Text" in note.wikilinks
    assert not note.is_index_page


def test_parse_note_with_frontmatter(parser):
    """Test parsing a note with YAML frontmatter."""
    content = """---
title: Custom Title
tags: [python, testing, markdown]
type: content
---

# Header in Content

This note has frontmatter with explicit title and tags.
"""
    
    note = parser.parse_note("frontmatter.md", content)
    
    assert note.title == "Custom Title"
    assert "python" in note.tags
    assert "testing" in note.tags
    assert "markdown" in note.tags


def test_parse_index_page(parser):
    """Test identification of index pages."""
    # Test filename-based detection
    index_note = parser.parse_note("index.md", "# Index Page\n\nThis is an index.")
    assert index_note.is_index_page
    
    # Test frontmatter-based detection
    content = """---
index: true
---

# Regular Title

This is marked as an index in frontmatter.
"""
    frontmatter_index = parser.parse_note("regular.md", content)
    assert frontmatter_index.is_index_page
    
    # Test title-based detection
    title_index = parser.parse_note("guide.md", "# Contents Index\n\nTable of contents.")
    assert title_index.is_index_page


def test_title_extraction_fallback(parser):
    """Test title extraction with various fallback methods."""
    # No frontmatter, no H1 - should use filename
    note = parser.parse_note("my-cool-note.md", "Just some content without a title.")
    assert note.title == "My Cool Note"
    
    # H1 should take precedence over filename
    content = "# Actual Title\n\nContent here."
    note = parser.parse_note("different-filename.md", content)
    assert note.title == "Actual Title"


def test_tag_extraction_methods(parser):
    """Test different methods of tag extraction."""
    content = """---
tags: yaml, frontmatter, tags
---

# Note with Mixed Tags

This has #inline and #hashtags in the content.

It also has frontmatter tags.
"""
    
    note = parser.parse_note("mixed-tags.md", content)
    
    # Should include both frontmatter and inline tags
    assert "yaml" in note.tags
    assert "frontmatter" in note.tags
    assert "tags" in note.tags
    assert "inline" in note.tags
    assert "hashtags" in note.tags


def test_wikilink_resolution(parser):
    """Test wikilink resolution functionality."""
    # Create some test notes
    notes = [
        Note(path="target.md", title="Target Note", content="Target content"),
        Note(path="folder/exact-match.md", title="Different Title", content="Content"),
        Note(path="index.md", title="Index", content="Index content", is_index_page=True),
    ]
    
    # Test exact path resolution
    result = parser.resolve_wikilink("target.md", notes)
    assert result is not None
    assert result.path == "target.md"
    
    # Test title-based resolution
    result = parser.resolve_wikilink("Target Note", notes)
    assert result is not None
    assert result.path == "target.md"
    
    # Test filename resolution
    result = parser.resolve_wikilink("exact-match", notes)
    assert result is not None
    assert result.path == "folder/exact-match.md"
    
    # Test filtering of index pages
    result = parser.resolve_wikilink("Index", notes)
    assert result is None  # Should be filtered out because it's an index page
    
    # Test non-existent link
    result = parser.resolve_wikilink("Non-existent", notes)
    assert result is None