import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import create_fleeting_note

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteCreate(BaseModel):
    content: str


@router.post("", status_code=201)
async def post_note(data: NoteCreate) -> dict:
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    try:
        return await create_fleeting_note(data.content)
    except Exception:
        logger.exception("Failed to create note in vault")
        raise HTTPException(status_code=502, detail="vault unavailable")
