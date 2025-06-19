import re
from typing import List, Optional
import frontmatter
from models import Note, WikiLink


class NoteParser:
    """Parser for Obsidian markdown notes with frontmatter and wikilinks."""
    
    # Regex patterns
    WIKILINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')
    INDEX_INDICATORS = ["index", "readme", "contents", "toc"]
    
    def parse_note(self, file_path: str, content: str) -> Note:
        """Parse a markdown file into a Note object."""
        # Parse frontmatter
        post = frontmatter.loads(content)
        metadata = post.metadata
        body_content = post.content
        
        # Extract title
        title = self._extract_title(metadata, body_content, file_path)
        
        # Extract tags
        tags = self._extract_tags(metadata, body_content)
        
        # Extract wikilinks
        wikilinks = self._extract_wikilinks(body_content)
        
        # Determine if this is an index page
        is_index_page = self._is_index_page(file_path, title, metadata)
        
        return Note(
            path=file_path,
            title=title,
            content=content,
            tags=tags,
            wikilinks=wikilinks,
            is_index_page=is_index_page
        )
    
    def _extract_title(self, metadata: dict, content: str, file_path: str) -> str:
        """Extract title from frontmatter, H1, or filename."""
        # Try frontmatter title first
        if "title" in metadata:
            return metadata["title"]
        
        # Try first H1 heading
        h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if h1_match:
            return h1_match.group(1).strip()
        
        # Fall back to filename without extension
        filename = file_path.split("/")[-1]
        return filename.replace(".md", "").replace("-", " ").replace("_", " ").title()
    
    def _extract_tags(self, metadata: dict, content: str) -> List[str]:
        """Extract tags from frontmatter and inline tags."""
        tags = set()
        
        # Frontmatter tags
        if "tags" in metadata:
            fm_tags = metadata["tags"]
            if isinstance(fm_tags, list):
                tags.update(fm_tags)
            elif isinstance(fm_tags, str):
                # Handle comma-separated or space-separated tags
                tags.update(tag.strip() for tag in re.split(r'[,\s]+', fm_tags) if tag.strip())
        
        # Inline hashtags (#tag)
        hashtag_pattern = re.compile(r'#([a-zA-Z0-9_-]+)')
        hashtags = hashtag_pattern.findall(content)
        tags.update(hashtags)
        
        return sorted(list(tags))
    
    def _extract_wikilinks(self, content: str) -> List[str]:
        """Extract all wikilinks from the content."""
        matches = self.WIKILINK_PATTERN.findall(content)
        return [match.strip() for match in matches]
    
    def _is_index_page(self, file_path: str, title: str, metadata: dict) -> bool:
        """Determine if this is an index/summary page."""
        # Check explicit frontmatter flag
        if metadata.get("index", False) or metadata.get("type") == "index":
            return True
        
        # Check filename
        filename = file_path.split("/")[-1].lower()
        if any(indicator in filename for indicator in self.INDEX_INDICATORS):
            return True
        
        # Check title
        title_lower = title.lower()
        if any(indicator in title_lower for indicator in self.INDEX_INDICATORS):
            return True
        
        return False
    
    def resolve_wikilink(self, link_text: str, available_notes: List[Note]) -> Optional[Note]:
        """Resolve a wikilink to an actual note, filtering out index pages."""
        # Parse the wikilink
        wiki_link = WikiLink.parse(f"[[{link_text}]]")
        target = wiki_link.target_path
        
        if not target:
            return None
        
        # Try exact path match first
        for note in available_notes:
            if note.path == target or note.path.endswith(f"/{target}"):
                if not note.is_index_page:  # Filter out index pages
                    return note
        
        # Try title match
        target_lower = target.lower()
        for note in available_notes:
            if note.title.lower() == target_lower:
                if not note.is_index_page:  # Filter out index pages
                    return note
        
        # Try filename match (without extension)
        for note in available_notes:
            filename = note.path.split("/")[-1].replace(".md", "")
            if filename.lower() == target_lower:
                if not note.is_index_page:  # Filter out index pages
                    return note
        
        return None