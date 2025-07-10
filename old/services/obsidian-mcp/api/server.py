import asyncio
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from models import Note, SearchResult, SearchNotesInput, GetNoteInput, FollowWikiLinkInput
from obsidian_service import ObsidianService
from settings import ObsidianSettings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthCheckFilter(logging.Filter):
    """Filter out health check requests from access logs."""
    def filter(self, record):
        return not (hasattr(record, 'getMessage') and 
                   ('GET /health' in record.getMessage() or 'GET /ready' in record.getMessage()))


def create_app(service: ObsidianService) -> FastAPI:
    """Create FastAPI application with REST API endpoints."""
    
    app = FastAPI(title="Obsidian Knowledge API", description="REST API for searching and retrieving Obsidian notes")
    
    # Health check endpoints for Kubernetes probes
    @app.get("/health")
    def health_check():
        """Health check endpoint for Kubernetes liveness probe."""
        return {"status": "healthy"}
    
    @app.get("/ready")
    def readiness_check():
        """Readiness check endpoint for Kubernetes readiness probe."""
        # Check if service is actually ready with notes loaded
        if hasattr(service, '_notes_cache') and service._notes_cache:
            return {"status": "ready", "notes_count": len(service._notes_cache)}
        return {"status": "not_ready", "reason": "notes not loaded"}
    
    # REST API endpoints
    @app.post("/api/search", response_model=List[SearchResult])
    def search_notes(input: SearchNotesInput) -> List[SearchResult]:
        """Search through the Obsidian vault using natural language queries. Returns ranked results with relevance scores and matched content excerpts."""
        try:
            return service.search_notes(input.query, input.tags, input.limit)
        except Exception as e:
            logger.error(f"Error searching notes: {e}")
            raise HTTPException(status_code=500, detail="Failed to search notes")
    
    @app.get("/api/notes/{path:path}", response_model=Note)
    def get_note(path: str) -> Note:
        """Retrieve the complete content and metadata of a specific note by its file path."""
        try:
            note = service.get_note(path)
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")
            return note
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting note {path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve note")
    
    @app.get("/api/notes", response_model=List[Note])
    def list_notes() -> List[Note]:
        """List all notes in the Obsidian vault with their metadata (useful for getting an overview of available content)."""
        try:
            return service.list_notes()
        except Exception as e:
            logger.error(f"Error listing notes: {e}")
            raise HTTPException(status_code=500, detail="Failed to list notes")
    
    @app.post("/api/follow-link", response_model=Note)
    def follow_wikilink(input: FollowWikiLinkInput) -> Note:
        """Follow a wikilink reference from one note to retrieve the linked note's content. Resolves Obsidian-style [[wikilinks]] to actual notes."""
        try:
            note = service.follow_wikilink(input.note_path, input.link_text)
            if not note:
                raise HTTPException(status_code=404, detail="Linked note not found")
            return note
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error following wikilink: {e}")
            raise HTTPException(status_code=500, detail="Failed to follow wikilink")
    
    return app


def main():
    """Main entry point."""
    import uvicorn
    
    # Load configuration from environment
    settings = ObsidianSettings()
    
    async def initialize_service():
        # Initialize service
        service = ObsidianService(
            repo_url=settings.repo_url,
            token=settings.github_token,
            branch=settings.branch,
            path_prefix=settings.path_prefix
        )
        await service.initialize()
        return service
    
    # Initialize service first
    service = asyncio.run(initialize_service())
    
    # Create FastAPI app
    app = create_app(service)
    
    # Configure uvicorn logging to filter out health checks
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    log_config["filters"] = {
        "health_filter": {
            "()": HealthCheckFilter,
        }
    }
    log_config["handlers"]["access"]["filters"] = ["health_filter"]
    
    # Run with uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_config=log_config
    )


if __name__ == "__main__":
    main()