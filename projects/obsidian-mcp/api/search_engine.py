import re
from typing import List, Optional, Set
from models import Note, SearchResult


class SearchEngine:
    """Simple search engine for Obsidian notes."""
    
    def __init__(self, notes: List[Note]):
        self.notes = notes
        self._build_search_index()
    
    def _build_search_index(self) -> None:
        """Build a simple search index for faster lookups."""
        self.title_index = {}
        self.content_index = {}
        self.tag_index = {}
        
        for note in self.notes:
            # Index by title words
            title_words = self._tokenize(note.title)
            for word in title_words:
                if word not in self.title_index:
                    self.title_index[word] = []
                self.title_index[word].append(note)
            
            # Index by content words
            content_words = self._tokenize(note.content)
            for word in content_words:
                if word not in self.content_index:
                    self.content_index[word] = []
                self.content_index[word].append(note)
            
            # Index by tags
            for tag in note.tags:
                tag_lower = tag.lower()
                if tag_lower not in self.tag_index:
                    self.tag_index[tag_lower] = []
                self.tag_index[tag_lower].append(note)
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization - split on word boundaries and normalize."""
        # Remove markdown syntax and normalize
        clean_text = re.sub(r'[#*_`\[\]()]', ' ', text)
        words = re.findall(r'\b\w+\b', clean_text.lower())
        return [word for word in words if len(word) > 2]  # Filter short words
    
    def search(self, query: str, tags: Optional[List[str]] = None, limit: int = 10) -> List[SearchResult]:
        """Search for notes matching the query and optional tag filters."""
        query_words = self._tokenize(query)
        if not query_words and not tags:
            return []
        
        # Find candidate notes (use list to avoid hashability issues)
        candidates = []
        seen_paths = set()
        
        # Search by query words
        if query_words:
            for word in query_words:
                # Search in titles (higher weight)
                if word in self.title_index:
                    for note in self.title_index[word]:
                        if note.path not in seen_paths:
                            candidates.append(note)
                            seen_paths.add(note.path)
                
                # Search in content
                if word in self.content_index:
                    for note in self.content_index[word]:
                        if note.path not in seen_paths:
                            candidates.append(note)
                            seen_paths.add(note.path)
        
        # Filter by tags if specified
        if tags:
            tag_matched_paths = set()
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in self.tag_index:
                    for note in self.tag_index[tag_lower]:
                        tag_matched_paths.add(note.path)
            
            if query_words:
                # Intersect with query results
                candidates = [note for note in candidates if note.path in tag_matched_paths]
            else:
                # Tag-only search
                candidates = []
                for tag in tags:
                    tag_lower = tag.lower()
                    if tag_lower in self.tag_index:
                        for note in self.tag_index[tag_lower]:
                            if note.path not in seen_paths:
                                candidates.append(note)
                                seen_paths.add(note.path)
        
        # Score and rank results
        results = []
        for note in candidates:
            score = self._calculate_relevance_score(note, query, query_words, tags)
            if score > 0:
                snippet = self._extract_snippet(note, query_words)
                results.append(SearchResult(
                    note=note,
                    relevance_score=score,
                    matched_content=snippet
                ))
        
        # Sort by relevance score (descending) and limit results
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]
    
    def _calculate_relevance_score(self, note: Note, original_query: str, 
                                 query_words: List[str], tags: Optional[List[str]]) -> float:
        """Calculate relevance score for a note."""
        score = 0.0
        
        # Title matches (highest weight)
        title_lower = note.title.lower()
        original_lower = original_query.lower()
        
        if original_lower in title_lower:
            score += 10.0  # Exact phrase match in title
        
        for word in query_words:
            if word in title_lower:
                score += 5.0  # Word match in title
        
        # Content matches
        content_lower = note.content.lower()
        
        if original_lower in content_lower:
            score += 3.0  # Exact phrase match in content
        
        for word in query_words:
            # Count word frequency in content
            word_count = content_lower.count(word)
            score += word_count * 1.0
        
        # Tag matches
        if tags:
            note_tags_lower = [tag.lower() for tag in note.tags]
            for tag in tags:
                if tag.lower() in note_tags_lower:
                    score += 8.0  # Tag match
        
        # Boost for non-index pages
        if not note.is_index_page:
            score *= 1.2
        
        return score
    
    def _extract_snippet(self, note: Note, query_words: List[str]) -> str:
        """Extract a relevant snippet from the note content."""
        content = note.content
        
        # Try to find the first occurrence of any query word
        best_position = -1
        for word in query_words:
            pos = content.lower().find(word)
            if pos != -1 and (best_position == -1 or pos < best_position):
                best_position = pos
        
        if best_position == -1:
            # No query words found, return beginning of content
            return self._clean_snippet(content[:200])
        
        # Extract snippet around the found position
        start = max(0, best_position - 100)
        end = min(len(content), best_position + 200)
        
        snippet = content[start:end]
        
        # Try to start and end at word boundaries
        if start > 0:
            space_pos = snippet.find(' ')
            if space_pos != -1:
                snippet = snippet[space_pos + 1:]
        
        if end < len(content):
            space_pos = snippet.rfind(' ')
            if space_pos != -1:
                snippet = snippet[:space_pos]
        
        return self._clean_snippet(snippet)
    
    def _clean_snippet(self, snippet: str) -> str:
        """Clean a snippet by removing markdown syntax and normalizing whitespace."""
        # Remove markdown headers
        snippet = re.sub(r'^#+\s*', '', snippet, flags=re.MULTILINE)
        
        # Remove markdown formatting
        snippet = re.sub(r'[*_`]', '', snippet)
        
        # Remove wikilinks but keep the text
        snippet = re.sub(r'\[\[([^\]]+)\]\]', r'\1', snippet)
        
        # Normalize whitespace
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        
        return snippet
    
    def get_note_by_path(self, path: str) -> Optional[Note]:
        """Get a specific note by its path."""
        for note in self.notes:
            if note.path == path:
                return note
        return None
    
    def list_all_notes(self) -> List[Note]:
        """Get all notes, optionally filtered."""
        return self.notes.copy()