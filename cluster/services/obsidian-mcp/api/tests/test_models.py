import pytest
from models import Note, SearchResult, WikiLink, SearchNotesInput, GetNoteInput, FollowWikiLinkInput


def test_note_creation():
    """Test Note model creation and validation."""
    note = Note(
        path="notes/test.md",
        title="Test Note",
        content="# Test Note\n\nThis is a test note with #tag1 and #tag2.",
        tags=["tag1", "tag2"],
        wikilinks=["[[Other Note]]"],
        is_index_page=False
    )
    
    assert note.path == "notes/test.md"
    assert note.title == "Test Note"
    assert note.tags == ["tag1", "tag2"]
    assert note.wikilinks == ["[[Other Note]]"]
    assert not note.is_index_page


def test_note_defaults():
    """Test Note model with default values."""
    note = Note(
        path="test.md",
        title="Test",
        content="Content"
    )
    
    assert note.tags == []
    assert note.wikilinks == []
    assert not note.is_index_page
    assert note.last_modified is None


def test_search_result_validation():
    """Test SearchResult validation."""
    note = Note(path="test.md", title="Test", content="Content")
    
    result = SearchResult(
        note=note,
        relevance_score=5.0,
        matched_content="Test content snippet"
    )
    
    assert result.relevance_score == 5.0
    assert result.matched_content == "Test content snippet"
    
    # Test negative score validation
    with pytest.raises(ValueError):
        SearchResult(
            note=note,
            relevance_score=-1.0,
            matched_content="Test"
        )


def test_wikilink_parsing():
    """Test WikiLink parsing functionality."""
    # Simple wikilink
    simple_link = WikiLink.parse("[[Target Note]]")
    assert simple_link.target_path == "Target Note"
    assert simple_link.display_text is None
    
    # Wikilink with display text
    display_link = WikiLink.parse("[[Target Note|Display Text]]")
    assert display_link.target_path == "Target Note"
    assert display_link.display_text == "Display Text"


def test_input_models():
    """Test input model validation."""
    # SearchNotesInput
    search_input = SearchNotesInput(query="test query", tags=["tag1"], limit=5)
    assert search_input.query == "test query"
    assert search_input.tags == ["tag1"]
    assert search_input.limit == 5
    
    # Default values
    default_search = SearchNotesInput(query="test")
    assert default_search.tags is None
    assert default_search.limit == 10
    
    # GetNoteInput
    get_input = GetNoteInput(path="notes/test.md")
    assert get_input.path == "notes/test.md"
    
    # FollowWikiLinkInput
    follow_input = FollowWikiLinkInput(
        note_path="source.md",
        link_text="[[Target]]"
    )
    assert follow_input.note_path == "source.md"
    assert follow_input.link_text == "[[Target]]"