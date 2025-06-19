#!/usr/bin/env python3
"""
Basic test script to verify the Obsidian MCP server components work.
This doesn't require a real GitHub repository.
"""

import asyncio
from note_parser import NoteParser
from search_engine import SearchEngine
from models import Note


async def test_basic_functionality():
    """Test basic functionality without GitHub integration."""
    
    print("🧪 Testing Obsidian MCP Server Components")
    print("=" * 50)
    
    # Create test notes
    parser = NoteParser()
    
    test_files = [
        ("leadership.md", """---
title: Leadership Principles
tags: [leadership, management, team]
---

# Leadership Principles

## Core Values
- Lead by example
- Empower your team
- Make data-driven decisions

This connects to [[Team Management]] and [[Decision Making]].

#leadership #management
"""),
        ("team-management.md", """# Team Management

Best practices for managing engineering teams:

1. Regular 1:1s
2. Clear goals and expectations
3. Feedback loops

References [[Leadership Principles]] for core values.

#management #teams
"""),
        ("index.md", """---
title: Knowledge Base Index
index: true
---

# Knowledge Base

This is the main index page linking to:
- [[Leadership Principles]]
- [[Team Management]]
"""),
        ("decision-making.md", """# Decision Making Framework

A framework for making better decisions:

## Process
1. Define the problem
2. Gather information
3. Consider alternatives
4. Make the decision
5. Review outcomes

#decisions #framework
""")
    ]
    
    # Parse all notes
    notes = []
    for path, content in test_files:
        note = parser.parse_note(path, content)
        notes.append(note)
        print(f"✅ Parsed: {note.title} ({path})")
        print(f"   Tags: {note.tags}")
        print(f"   Wikilinks: {note.wikilinks}")
        print(f"   Is Index: {note.is_index_page}")
        print()
    
    # Test search engine
    print("🔍 Testing Search Engine")
    print("-" * 30)
    
    search_engine = SearchEngine(notes)
    
    # Test text search
    results = search_engine.search("leadership team", limit=5)
    print(f"Search 'leadership team': {len(results)} results")
    for result in results:
        print(f"  - {result.note.title} (score: {result.relevance_score:.1f})")
        print(f"    Snippet: {result.matched_content[:100]}...")
    print()
    
    # Test tag search
    results = search_engine.search("", tags=["management"], limit=5)
    print(f"Tag search 'management': {len(results)} results")
    for result in results:
        print(f"  - {result.note.title}")
    print()
    
    # Test wikilink resolution
    print("🔗 Testing Wikilink Resolution")
    print("-" * 30)
    
    target = parser.resolve_wikilink("Team Management", notes)
    if target:
        print(f"✅ Resolved 'Team Management' -> {target.title}")
    else:
        print("❌ Failed to resolve 'Team Management'")
    
    # Test index page filtering
    index_target = parser.resolve_wikilink("Knowledge Base Index", notes)
    if index_target is None:
        print("✅ Correctly filtered out index page")
    else:
        print("❌ Failed to filter index page")
    
    print("\n🎉 Basic functionality test completed!")


if __name__ == "__main__":
    asyncio.run(test_basic_functionality())