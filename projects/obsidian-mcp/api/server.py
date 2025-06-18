import asyncio
import contextlib
import logging
from typing import List, Optional
from fastapi import FastAPI
from fastmcp import FastMCP
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


def create_mcp_server(service: ObsidianService) -> FastMCP:
    """Create and configure the MCP server with the service."""
    mcp = FastMCP("Obsidian Knowledge Server")
    
    @mcp.tool()
    def search_notes(input: SearchNotesInput) -> List[SearchResult]:
        """Search for notes by content, title, or tags."""
        return service.search_notes(input.query, input.tags, input.limit)
    
    @mcp.tool()
    def get_note(input: GetNoteInput) -> Optional[Note]:
        """Retrieve the full content of a specific note."""
        return service.get_note(input.path)
    
    @mcp.tool()
    def list_notes() -> List[Note]:
        """List all available notes with basic metadata."""
        return service.list_notes()
    
    @mcp.tool()
    def follow_wikilink(input: FollowWikiLinkInput) -> Optional[Note]:
        """Follow a wikilink from one note to another, filtering out index pages."""
        return service.follow_wikilink(input.note_path, input.link_text)
    
    return mcp


def create_app(service: ObsidianService, mcp: FastMCP) -> FastAPI:
    """Create FastAPI application with health checks and MCP server."""
    
    app = FastAPI(title="Obsidian MCP Server")
    
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
    
    # Mount MCP server
    app.mount("/mcp", mcp.http_app())
    
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
    
    # Create MCP server and FastAPI app
    mcp = create_mcp_server(service)
    app = create_app(service, mcp)
    
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