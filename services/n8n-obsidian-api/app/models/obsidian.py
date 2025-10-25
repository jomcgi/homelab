"""Pydantic models matching Obsidian Local REST API schema."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Error(BaseModel):
    """Error response from Obsidian API."""

    error_code: int = Field(
        ..., alias="errorCode", description="A 5-digit error code identifying the error type"
    )
    message: str = Field(..., description="Error message")


class NoteStat(BaseModel):
    """File statistics for a note."""

    ctime: float = Field(..., description="Creation time (Unix timestamp)")
    mtime: float = Field(..., description="Modification time (Unix timestamp)")
    size: int = Field(..., description="File size in bytes")


class NoteJson(BaseModel):
    """JSON representation of a note with metadata."""

    path: str = Field(..., description="Path to the note relative to vault root")
    content: str = Field(..., description="Markdown content of the note")
    tags: list[str] = Field(default_factory=list, description="Tags found in the note")
    frontmatter: dict[str, Any] = Field(
        default_factory=dict, description="YAML frontmatter as dict"
    )
    stat: NoteStat = Field(..., description="File statistics")

    class Config:
        """Pydantic config."""

        populate_by_name = True


class PatchOperation(str, Enum):
    """Patch operation types for PATCH requests."""

    APPEND = "append"
    PREPEND = "prepend"
    REPLACE = "replace"


class PatchTargetType(str, Enum):
    """Target types for PATCH operations."""

    HEADING = "heading"
    BLOCK = "block"
    FRONTMATTER = "frontmatter"
