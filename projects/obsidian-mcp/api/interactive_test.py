#!/usr/bin/env python3
"""
Interactive testing of the Obsidian MCP server.
"""

import asyncio
import sys
from settings import ObsidianSettings
from obsidian_service import ObsidianService
from models import SearchNotesInput


async def interactive_test():
    """Interactive testing of the MCP server."""
    print("🔧 Interactive Obsidian MCP Test")
    print("=" * 40)
    
    # Initialize service
    settings = ObsidianSettings()
    service = ObsidianService(
        repo_url=settings.repo_url,
        token=settings.github_token,
        branch=settings.branch,
        path_prefix=settings.path_prefix
    )
    await service.initialize()
    print(f"Loaded {len(service.notes)} notes\n")
    
    while True:
        print("Commands:")
        print("  search <query>     - Search notes")
        print("  list              - List all notes")
        print("  get <path>        - Get specific note")
        print("  quit              - Exit")
        
        command = input("\n> ").strip()
        
        if command == "quit":
            break
        elif command == "list":
            print(f"\n📋 All {len(service.notes)} notes:")
            for note in service.notes:
                print(f"  - {note.title} ({note.path})")
        elif command.startswith("search "):
            query = command[7:]
            results = service.search_notes(query, limit=5)
            print(f"\n🔍 Search '{query}': {len(results)} results")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result.note.title} (score: {result.relevance_score:.1f})")
                print(f"     Path: {result.note.path}")
                print(f"     Snippet: {result.matched_content[:80]}...")
        elif command.startswith("get "):
            path = command[4:]
            note = service.get_note(path)
            if note:
                print(f"\n📄 {note.title}")
                print(f"Tags: {note.tags}")
                print(f"Content preview:\n{note.content[:200]}...")
            else:
                print(f"❌ Note not found: {path}")
        else:
            print("❌ Unknown command")


if __name__ == "__main__":
    asyncio.run(interactive_test())