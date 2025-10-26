"""Pydantic models for Obsidian API."""

from .obsidian import (
    Error,
    NoteStat,
    NoteJson,
    PatchOperation,
    PatchTargetType,
)

__all__ = [
    "Error",
    "NoteStat",
    "NoteJson",
    "PatchOperation",
    "PatchTargetType",
]
