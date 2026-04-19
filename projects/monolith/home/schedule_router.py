from fastapi import APIRouter

from home.schedule import get_today_events

router = APIRouter(prefix="/api/home/schedule", tags=["schedule"])


@router.get("/today")
def schedule_today() -> list[dict]:
    return get_today_events()
