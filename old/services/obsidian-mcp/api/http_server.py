#!/usr/bin/env python3
"""
HTTP wrapper for the Obsidian MCP server for easy testing.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from settings import ObsidianSettings
from obsidian_service import ObsidianService
from models import SearchNotesInput, GetNoteInput, FollowWikiLinkInput


# Global service instance
service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global service
    
    # Startup
    settings = ObsidianSettings()
    service = ObsidianService(
        repo_url=settings.repo_url,
        token=settings.github_token,
        branch=settings.branch,
        path_prefix=settings.path_prefix
    )
    await service.initialize()
    print(f"✅ Loaded {len(service.notes)} notes")
    
    yield
    
    # Shutdown (nothing to clean up)


# Initialize FastAPI app
app = FastAPI(title="Obsidian MCP HTTP Test Server", lifespan=lifespan)


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "message": "Obsidian MCP HTTP Test Server",
        "notes_loaded": len(service.notes) if service else 0,
        "endpoints": {
            "search": "POST /search",
            "note": "GET /note/{path}",
            "notes": "GET /notes",
            "follow": "POST /follow"
        }
    }


@app.post("/search")
async def search_notes(query: str, tags: str = None, limit: int = 10):
    """Search notes by content, title, or tags."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    tag_list = tags.split(",") if tags else None
    results = service.search_notes(query, tag_list, limit)
    
    return {
        "query": query,
        "tags": tag_list,
        "results": [
            {
                "title": result.note.title,
                "path": result.note.path,
                "relevance_score": result.relevance_score,
                "matched_content": result.matched_content,
                "tags": result.note.tags,
                "wikilinks": result.note.wikilinks
            }
            for result in results
        ]
    }


@app.get("/note/{path:path}")
async def get_note(path: str):
    """Get a specific note by path."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    note = service.get_note(path)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    return {
        "title": note.title,
        "path": note.path,
        "content": note.content,
        "tags": note.tags,
        "wikilinks": note.wikilinks,
        "is_index_page": note.is_index_page
    }


@app.get("/notes")
async def list_notes(limit: int = 50):
    """List all available notes."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    notes = service.list_notes()[:limit]
    return {
        "total": len(service.notes),
        "returned": len(notes),
        "notes": [
            {
                "title": note.title,
                "path": note.path,
                "tags": note.tags,
                "is_index_page": note.is_index_page
            }
            for note in notes
        ]
    }


@app.post("/follow")
async def follow_wikilink(note_path: str, link_text: str):
    """Follow a wikilink from one note to another."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    target_note = service.follow_wikilink(note_path, link_text)
    if not target_note:
        raise HTTPException(status_code=404, detail="Wikilink target not found")
    
    return {
        "source_path": note_path,
        "link_text": link_text,
        "target": {
            "title": target_note.title,
            "path": target_note.path,
            "tags": target_note.tags
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)