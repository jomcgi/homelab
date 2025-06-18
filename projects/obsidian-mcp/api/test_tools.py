#!/usr/bin/env python3
"""
Test the MCP tools directly.
"""

import asyncio
from settings import ObsidianSettings
from obsidian_service import ObsidianService
from models import SearchNotesInput, GetNoteInput, FollowWikiLinkInput


async def test_mcp_tools():
    """Test all MCP tools with your data."""
    print("🔧 Testing MCP Tools")
    print("=" * 50)
    
    # Initialize service
    settings = ObsidianSettings()
    service = ObsidianService(
        repo_url=settings.repo_url,
        token=settings.github_token,
        branch=settings.branch,
        path_prefix=settings.path_prefix
    )
    await service.initialize()
    
    print("🔍 Tool: search_notes")
    print("-" * 30)
    search_input = SearchNotesInput(query="leadership systems", limit=3)
    results = service.search_notes(search_input.query, search_input.tags, search_input.limit)
    print(f"Found {len(results)} results:")
    for result in results:
        print(f"  - {result.note.title} (score: {result.relevance_score:.1f})")
        print(f"    Snippet: {result.matched_content[:80]}...")
    print()
    
    print("📄 Tool: get_note")
    print("-" * 30)
    if results:
        note_path = results[0].note.path
        get_input = GetNoteInput(path=note_path)
        note = service.get_note(get_input.path)
        if note:
            print(f"Retrieved: {note.title}")
            print(f"Content preview: {note.content[:100]}...")
            print(f"Tags: {note.tags}")
            print(f"Wikilinks: {note.wikilinks[:3]}...")  # First 3 wikilinks
        print()
    
    print("📋 Tool: list_notes")  
    print("-" * 30)
    all_notes = service.list_notes()
    print(f"Total notes: {len(all_notes)}")
    print("Sample notes:")
    for note in all_notes[:5]:
        print(f"  - {note.title}")
    print()
    
    print("🔗 Tool: follow_wikilink")
    print("-" * 30)
    if results and results[0].note.wikilinks:
        source_path = results[0].note.path
        link_text = results[0].note.wikilinks[0]
        follow_input = FollowWikiLinkInput(note_path=source_path, link_text=link_text)
        target_note = service.follow_wikilink(follow_input.note_path, follow_input.link_text)
        if target_note:
            print(f"✅ Followed link '{link_text}' → {target_note.title}")
        else:
            print(f"❌ Could not resolve link: {link_text}")
    else:
        print("No wikilinks to test")
    
    print("\n🎉 Tool testing completed!")


if __name__ == "__main__":
    asyncio.run(test_mcp_tools())