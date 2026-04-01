from fastapi import APIRouter

from .service import get_today_events

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/today")
def schedule_today() -> list[dict]:
    return get_today_events()
