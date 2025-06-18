from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Note(BaseModel):
    """Represents an Obsidian note with metadata and content."""
    path: str
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    wikilinks: List[str] = Field(default_factory=list)
    is_index_page: bool = False
    last_modified: Optional[datetime] = None


class SearchResult(BaseModel):
    """Represents a search result with relevance scoring."""
    note: Note
    relevance_score: float = Field(ge=0.0, description="Relevance score (>= 0)")
    matched_content: str = Field(description="Content snippet showing the match")


class WikiLink(BaseModel):
    """Represents a parsed wikilink."""
    text: str
    target_path: Optional[str] = None
    display_text: Optional[str] = None
    
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
    """Input for searching notes."""
    query: str = Field(description="Text to search for in note content and titles")
    tags: Optional[List[str]] = Field(default=None, description="Filter by specific tags")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of results")


class GetNoteInput(BaseModel):
    """Input for retrieving a specific note."""
    path: str = Field(description="Path to the note file")


class FollowWikiLinkInput(BaseModel):
    """Input for following a wikilink."""
    note_path: str = Field(description="Path of the source note")
    link_text: str = Field(description="The wikilink text to follow")