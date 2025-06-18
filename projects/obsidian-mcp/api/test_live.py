#!/usr/bin/env python3
"""
Test the live Obsidian MCP server with your actual notes.
"""

import asyncio
from settings import ObsidianSettings
from obsidian_service import ObsidianService


async def test_live_service():
    """Test the service with real data."""
    print("🧪 Testing Live Obsidian MCP Service")
    print("=" * 50)
    
    # Load configuration
    settings = ObsidianSettings()
    
    # Initialize service
    service = ObsidianService(
        repo_url=settings.repo_url,
        token=settings.github_token,
        branch=settings.branch,
        path_prefix=settings.path_prefix
    )
    
    print(f"Loading notes from: {settings.repo_url}")
    print(f"Path prefix: {settings.path_prefix}")
    print()
    
    await service.initialize()
    
    # Test search functionality
    print("🔍 Testing Search")
    print("-" * 30)
    
    # Search for leadership content
    results = service.search_notes("leadership", limit=3)
    print(f"Search 'leadership': {len(results)} results")
    for result in results:
        print(f"  - {result.note.title} (score: {result.relevance_score:.1f})")
        print(f"    Tags: {result.note.tags}")
        print(f"    Path: {result.note.path}")
        print()
    
    # Test tag search
    results = service.search_notes("", tags=["engineering"], limit=3)
    print(f"Tag search 'engineering': {len(results)} results")
    for result in results:
        print(f"  - {result.note.title}")
    print()
    
    # Test note retrieval
    print("📄 Testing Note Retrieval")
    print("-" * 30)
    
    if service.notes:
        first_note = service.notes[0]
        retrieved = service.get_note(first_note.path)
        if retrieved:
            print(f"✅ Retrieved: {retrieved.title}")
            print(f"   Content length: {len(retrieved.content)} chars")
            print(f"   Wikilinks: {len(retrieved.wikilinks)}")
        else:
            print("❌ Failed to retrieve note")
    
    print(f"\n📊 Total notes loaded: {len(service.notes)}")
    print("🎉 Live test completed!")


if __name__ == "__main__":
    asyncio.run(test_live_service())