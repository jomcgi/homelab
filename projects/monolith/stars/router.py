"""HTTP router for the stars domain.

Exposes one read endpoint, anonymous and cookie-free, with cache headers per
ADR 002 (docs/decisions/platform/002-cdn-cached-data-fetching.md). The 5-minute
``s-maxage`` matches the freshness expectation of an hourly refresh — clients
poll the edge, not origin.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from app.db import get_session
from stars.service import get_latest_payload

logger = logging.getLogger("monolith.stars.router")

# ADR 002: anonymous JSON endpoints set s-maxage so the Cloudflare edge can
# cache. SWR=24h means the edge can keep serving the last good response while
# revalidating in the background, even if origin briefly fails.
_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=86400"

router = APIRouter(prefix="/api/stars", tags=["stars"])


@router.get("/best")
def get_best_locations(
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    """Latest scored stargazing locations.

    Returns the most recent successful refresh payload. If no refresh has
    completed yet (cold start, fresh deploy), returns an empty-but-shaped
    response so the frontend can render gracefully.
    """
    response.headers["Cache-Control"] = _CACHE_CONTROL
    payload = get_latest_payload(session)
    if payload is None:
        return {
            "locations": [],
            "total_locations": 0,
            "ranked_count": 0,
            "cached_at": None,
        }
    return payload
