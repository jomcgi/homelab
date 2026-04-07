import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar
from sqlmodel import Session

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Vancouver")

# In-memory cache, populated by poll_calendar()
_cached_events: list[dict] = []

ICAL_FEED_URL = os.environ.get("ICAL_FEED_URL", "")


def parse_events_for_date(ics_text: str, target_date: date, tz: ZoneInfo) -> list[dict]:
    cal = Calendar.from_ical(ics_text)
    all_day = []
    timed = []
    seen: set[tuple[str | None, str]] = set()

    for component in cal.walk("VEVENT"):
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        dt = dtstart.dt
        summary = str(component.get("SUMMARY", ""))

        # All-day event: dtstart is a date, not datetime
        if isinstance(dt, date) and not isinstance(dt, datetime):
            if dt == target_date:
                key = (None, summary)
                if key not in seen:
                    seen.add(key)
                    all_day.append({"time": None, "title": summary, "allDay": True})
            continue

        # Timed event: convert to target timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)

        if dt.date() == target_date:
            time_str = dt.strftime("%H:%M")
            key = (time_str, summary)
            if key not in seen:
                seen.add(key)
                # Parse end time
                dtend = component.get("DTEND")
                end_str = None
                if dtend is not None:
                    dte = dtend.dt
                    if isinstance(dte, datetime):
                        if dte.tzinfo is None:
                            dte = dte.replace(tzinfo=tz)
                        else:
                            dte = dte.astimezone(tz)
                        end_str = dte.strftime("%H:%M")
                timed.append(
                    {
                        "time": time_str,
                        "endTime": end_str,
                        "title": summary,
                        "allDay": False,
                    }
                )

    timed.sort(key=lambda e: e["time"])
    return all_day + timed


def get_today_events() -> list[dict]:
    return list(_cached_events)


async def poll_calendar() -> None:
    global _cached_events
    if not ICAL_FEED_URL:
        logger.warning("ICAL_FEED_URL not set, skipping calendar poll")
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(ICAL_FEED_URL, timeout=30)
            resp.raise_for_status()
        today = datetime.now(TZ).date()
        _cached_events = parse_events_for_date(resp.text, today, TZ)
        logger.info("Calendar refreshed: %d events for %s", len(_cached_events), today)
    except Exception:
        logger.exception("Failed to fetch calendar feed")


async def calendar_poll_handler(session: Session) -> None:
    """Scheduler handler for calendar polling. Session unused (stateless HTTP fetch)."""
    await poll_calendar()
    return None


def on_startup(session: Session) -> None:
    """Register shared jobs with the scheduler."""
    from shared.scheduler import register_job

    register_job(
        session,
        name="shared.calendar_poll",
        interval_secs=900,  # 15 minutes
        handler=calendar_poll_handler,
        ttl_secs=120,
    )
