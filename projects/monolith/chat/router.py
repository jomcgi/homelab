"""Chat API routes -- backfill endpoint."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from chat.backfill import run_backfill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/backfill", status_code=202)
async def backfill(request: Request):
    """Launch a background backfill of all Discord channel history."""
    bot = request.app.state.bot
    if not bot:
        raise HTTPException(503, "Discord bot not running")

    task = getattr(request.app.state, "backfill_task", None)
    if task and not task.done():
        raise HTTPException(409, "Backfill already running")

    task = asyncio.create_task(run_backfill(bot))
    request.app.state.backfill_task = task

    channels = [c for g in bot.guilds for c in g.text_channels]
    return {"status": "started", "channels": len(channels)}
