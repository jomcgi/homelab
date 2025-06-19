import os
from typing import List, Optional
from github_client import GitHubClient
from note_parser import NoteParser
from search_engine import SearchEngine
from models import Note, SearchResult


class ObsidianService:
    """Main service that coordinates GitHub client, parser, and search engine."""
    
    def __init__(self, repo_url: str, token: Optional[str] = None,
                 branch: str = "main", path_prefix: str = ""):
        self.repo_url = repo_url
        self.token = token
        self.branch = branch
        self.path_prefix = path_prefix
        
        self.github_client = GitHubClient(repo_url, token, branch, path_prefix)
        self.note_parser = NoteParser()
        self.search_engine: Optional[SearchEngine] = None
        self.notes: List[Note] = []
    
    async def initialize(self) -> None:
        """Initialize the service by loading notes from GitHub."""
        async with self.github_client:
            await self.github_client.initialize()
            await self._load_and_parse_notes()
    
    async def _load_and_parse_notes(self) -> None:
        """Load raw files from GitHub and parse them into Note objects."""
        print("Parsing notes...")
        
        raw_files = self.github_client.get_all_files()
        notes = []
        
        for file_path, content in raw_files:
            try:
                note = self.note_parser.parse_note(file_path, content)
                notes.append(note)
            except Exception as e:
                print(f"Error parsing {file_path}: {e}")
        
        self.notes = notes
        self.search_engine = SearchEngine(notes)
        
        print(f"Successfully parsed {len(notes)} notes")
    
    def search_notes(self, query: str, tags: Optional[List[str]] = None, 
                    limit: int = 10) -> List[SearchResult]:
        """Search for notes by content, title, or tags."""
        if not self.search_engine:
            return []
        
        return self.search_engine.search(query, tags, limit)
    
    def get_note(self, path: str) -> Optional[Note]:
        """Retrieve a specific note by path."""
        if not self.search_engine:
            return None
        
        return self.search_engine.get_note_by_path(path)
    
    def list_notes(self) -> List[Note]:
        """List all available notes."""
        return self.notes.copy()
    
    def follow_wikilink(self, note_path: str, link_text: str) -> Optional[Note]:
        """Follow a wikilink from one note to another."""
        if not self.search_engine:
            return None
        
        # Get the source note to ensure it exists
        source_note = self.get_note(note_path)
        if not source_note:
            return None
        
        # Use the parser to resolve the wikilink
        target_note = self.note_parser.resolve_wikilink(link_text, self.notes)
        return target_note