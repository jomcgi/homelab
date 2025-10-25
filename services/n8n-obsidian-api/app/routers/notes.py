"""Domain-specific note management endpoints for n8n workflows."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.obsidian import ObsidianClient, PathRestrictionError
from app.config import settings
from app.models import NoteJson, PatchOperation, PatchTargetType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes", tags=["notes"])


# Dependency to get Obsidian client
async def get_obsidian_client() -> ObsidianClient:
    """Dependency that provides an Obsidian API client."""
    async with ObsidianClient(
        base_url=settings.obsidian_api_url,
        api_key=settings.obsidian_api_key,
    ) as client:
        yield client


# Request/Response models for our domain-specific endpoints


class CreateNoteRequest(BaseModel):
    """Request to create or update a note."""

    path: str = Field(..., description="Path to note in /n8n/ folder (e.g., 'n8n/meeting.md')")
    content: str = Field(..., description="Markdown content of the note")


class AppendToNoteRequest(BaseModel):
    """Request to append content to a note."""

    path: str = Field(..., description="Path to note in /n8n/ folder")
    content: str = Field(..., description="Content to append")


class UpdateFrontmatterRequest(BaseModel):
    """Request to update a frontmatter field."""

    path: str = Field(..., description="Path to note in /n8n/ folder")
    key: str = Field(..., description="Frontmatter field key")
    value: Any = Field(..., description="Value to set (can be any JSON-serializable type)")


class AppendToSectionRequest(BaseModel):
    """Request to append content under a specific heading."""

    path: str = Field(..., description="Path to note in /n8n/ folder")
    heading: str = Field(..., description="Heading to append under (e.g., 'Daily Notes')")
    content: str = Field(..., description="Content to append")


class ReadNoteResponse(BaseModel):
    """Response containing note data."""

    note: NoteJson


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: str = "Operation completed successfully"


# Endpoints


@router.post("/create", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    request: CreateNoteRequest,
    client: ObsidianClient = Depends(get_obsidian_client),
) -> SuccessResponse:
    """
    Create a new note or update an existing one.

    This endpoint creates or completely replaces a note's content.
    The path must be within the /n8n/ directory.

    Example:
        POST /notes/create
        {
            "path": "n8n/workflows/data-sync.md",
            "content": "# Data Sync Workflow\\n\\nStatus: Active"
        }
    """
    try:
        await client.create_or_update_note(request.path, request.content)
        return SuccessResponse(message=f"Note created/updated: {request.path}")
    except PathRestrictionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create note")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create note: {str(e)}",
        )


@router.post("/append", response_model=SuccessResponse)
async def append_to_note(
    request: AppendToNoteRequest,
    client: ObsidianClient = Depends(get_obsidian_client),
) -> SuccessResponse:
    """
    Append content to the end of a note.

    Creates the note if it doesn't exist.
    Useful for adding entries to logs or journals.

    Example:
        POST /notes/append
        {
            "path": "n8n/logs/workflow-runs.md",
            "content": "\\n- [2024-01-15] Workflow executed successfully"
        }
    """
    try:
        await client.append_to_note(request.path, request.content)
        return SuccessResponse(message=f"Content appended to: {request.path}")
    except PathRestrictionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("Failed to append to note")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to append to note: {str(e)}",
        )


@router.post("/append-to-section", response_model=SuccessResponse)
async def append_to_section(
    request: AppendToSectionRequest,
    client: ObsidianClient = Depends(get_obsidian_client),
) -> SuccessResponse:
    """
    Append content under a specific heading in a note.

    This is useful for organizing content into sections.
    For nested headings, use '::' separator (e.g., 'Main::Sub').

    Example:
        POST /notes/append-to-section
        {
            "path": "n8n/project-notes.md",
            "heading": "Tasks",
            "content": "\\n- [ ] Review API integration"
        }
    """
    try:
        await client.patch_note(
            path=request.path,
            content=request.content,
            operation=PatchOperation.APPEND,
            target_type=PatchTargetType.HEADING,
            target=request.heading,
        )
        return SuccessResponse(
            message=f"Content appended to section '{request.heading}' in {request.path}"
        )
    except PathRestrictionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("Failed to append to section")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to append to section: {str(e)}",
        )


@router.post("/update-frontmatter", response_model=SuccessResponse)
async def update_frontmatter(
    request: UpdateFrontmatterRequest,
    client: ObsidianClient = Depends(get_obsidian_client),
) -> SuccessResponse:
    """
    Update a single frontmatter field in a note.

    Frontmatter is YAML metadata at the top of markdown files.

    Example:
        POST /notes/update-frontmatter
        {
            "path": "n8n/workflows/sync.md",
            "key": "status",
            "value": "completed"
        }
    """
    try:
        await client.update_frontmatter(request.path, request.key, request.value)
        return SuccessResponse(
            message=f"Frontmatter '{request.key}' updated in {request.path}"
        )
    except PathRestrictionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update frontmatter")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update frontmatter: {str(e)}",
        )


@router.get("/{path:path}", response_model=ReadNoteResponse)
async def read_note(
    path: str,
    client: ObsidianClient = Depends(get_obsidian_client),
) -> ReadNoteResponse:
    """
    Read a note from anywhere in the vault.

    Returns structured data including content, tags, frontmatter, and metadata.
    Read operations are allowed for all vault paths.

    Example:
        GET /notes/n8n/workflows/sync.md
    """
    try:
        note = await client.get_note(path, as_json=True)
        return ReadNoteResponse(note=note)
    except Exception as e:
        logger.exception("Failed to read note")
        if "404" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Note not found: {path}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read note: {str(e)}",
        )


@router.delete("/{path:path}", response_model=SuccessResponse)
async def delete_note(
    path: str,
    client: ObsidianClient = Depends(get_obsidian_client),
) -> SuccessResponse:
    """
    Delete a note from the vault.

    Only allowed for notes in /n8n/ directory.

    Example:
        DELETE /notes/n8n/temp/scratch.md
    """
    try:
        await client.delete_note(path)
        return SuccessResponse(message=f"Note deleted: {path}")
    except PathRestrictionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("Failed to delete note")
        if "404" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Note not found: {path}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete note: {str(e)}",
        )
