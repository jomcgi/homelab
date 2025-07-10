from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Note(BaseModel):
    """Represents an Obsidian note with metadata and content."""
    path: str = Field(description="File path relative to vault root (e.g., 'folder/note.md')")
    title: str = Field(description="Display title of the note")
    content: str = Field(description="Full markdown content of the note")
    tags: List[str] = Field(default_factory=list, description="List of tags found in the note")
    wikilinks: List[str] = Field(default_factory=list, description="List of wikilink references found in content")
    is_index_page: bool = Field(default=False, description="Whether this is an index/directory page")
    last_modified: Optional[datetime] = Field(default=None, description="When the note was last modified")


class SearchResult(BaseModel):
    """Represents a search result with relevance scoring."""
    note: Note = Field(description="The found note with full content and metadata")
    relevance_score: float = Field(ge=0.0, description="Relevance score based on query match strength (higher = more relevant)")
    matched_content: str = Field(description="Excerpt from note content showing where the search query matched")


class WikiLink(BaseModel):
    """Represents a parsed wikilink from Obsidian notes."""
    text: str = Field(description="Original wikilink text as found in source (e.g., '[[Target|Display]]')")
    target_path: Optional[str] = Field(default=None, description="The target note path being linked to")
    display_text: Optional[str] = Field(default=None, description="Custom display text if different from target")
    
    @classmethod
    def parse(cls, link_text: str) -> "WikiLink":
        """Parse a wikilink like [[Target|Display]] or [[Target]]."""
        clean_text = link_text.strip("[]")
        
        if "|" in clean_text:
            target, display = clean_text.split("|", 1)
            return cls(text=link_text, target_path=target.strip(), display_text=display.strip())
        else:
            return cls(text=link_text, target_path=clean_text.strip())


# Input/Output models for MCP tools
class SearchNotesInput(BaseModel):
    """Input for searching through the Obsidian vault."""
    query: str = Field(description="Search text to find in note titles and content. Use natural language or keywords.")
    tags: Optional[List[str]] = Field(default=None, description="Optional list of tags to filter results (e.g., ['project', 'work'])")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of search results to return (1-50)")


class GetNoteInput(BaseModel):
    """Input for retrieving a specific note by its path."""
    path: str = Field(description="Full path to the note file relative to vault root (e.g., 'Projects/My Project.md')")


class FollowWikiLinkInput(BaseModel):
    """Input for following a wikilink from one note to another."""
    note_path: str = Field(description="Path of the source note containing the wikilink")
    link_text: str = Field(description="The exact wikilink text to follow (e.g., '[[Target Note]]' or '[[Target|Display]]')")