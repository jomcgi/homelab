import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session

from ..db import engine
from .router import _archive_and_reset

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Los_Angeles")


async def run_scheduler() -> None:
    """Run daily/weekly reset at midnight Pacific."""
    while True:
        now = datetime.now(TZ)
        next_midnight = datetime.combine(
            now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
        )
        sleep_seconds = (next_midnight - now).total_seconds()
        logger.info(
            "Scheduler: next reset at %s (sleeping %.0fs)",
            next_midnight.isoformat(),
            sleep_seconds,
        )
        await asyncio.sleep(sleep_seconds)

        reset_time = datetime.now(TZ)
        weekly = reset_time.weekday() == 5  # Saturday = end of Friday
        logger.info("Scheduler: triggering %s reset", "weekly" if weekly else "daily")

        try:
            with Session(engine) as session:
                _archive_and_reset(session, weekly_reset=weekly)
        except Exception:
            logger.exception("Scheduler: reset failed, will retry next cycle")
