from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest

import shared.service as svc
from shared.service import parse_events_for_date, poll_calendar

TZ = ZoneInfo("America/Vancouver")

# Minimal ICS with one timed event and one all-day event
SAMPLE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T090000
DTEND:20260330T093000
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260330
DTEND;VALUE=DATE:20260331
SUMMARY:Company Holiday
END:VEVENT
BEGIN:VEVENT
DTSTART:20260331T140000
DTEND:20260331T150000
SUMMARY:Tomorrow Event
END:VEVENT
END:VCALENDAR
"""


def test_parse_timed_event():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    timed = [e for e in events if not e["allDay"]]
    assert len(timed) == 1
    assert timed[0]["time"] == "09:00"
    assert timed[0]["endTime"] == "09:30"
    assert timed[0]["title"] == "Standup"


def test_parse_all_day_event():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    all_day = [e for e in events if e["allDay"]]
    assert len(all_day) == 1
    assert all_day[0]["title"] == "Company Holiday"
    assert all_day[0]["time"] is None


def test_all_day_events_come_first():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    assert events[0]["allDay"] is True
    assert events[1]["allDay"] is False


def test_excludes_other_dates():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    titles = [e["title"] for e in events]
    assert "Tomorrow Event" not in titles


def test_empty_calendar():
    ics = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"
    events = parse_events_for_date(ics, date(2026, 3, 30), TZ)
    assert events == []


DUPLICATE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T094500
DTEND:20260330T103000
SUMMARY:Infra Ops Review
END:VEVENT
BEGIN:VEVENT
DTSTART:20260330T094500
DTEND:20260330T103000
SUMMARY:Infra Ops Review
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260330
DTEND;VALUE=DATE:20260331
SUMMARY:Holiday
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260330
DTEND;VALUE=DATE:20260331
SUMMARY:Holiday
END:VEVENT
END:VCALENDAR
"""


def test_deduplicates_events():
    events = parse_events_for_date(DUPLICATE_ICS, date(2026, 3, 30), TZ)
    assert len(events) == 2
    assert events[0]["title"] == "Holiday"
    assert events[1]["title"] == "Infra Ops Review"
    assert events[1]["endTime"] == "10:30"


NO_DTEND_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T120000
SUMMARY:Lunch
END:VEVENT
END:VCALENDAR
"""


def test_missing_dtend_returns_none():
    events = parse_events_for_date(NO_DTEND_ICS, date(2026, 3, 30), TZ)
    assert len(events) == 1
    assert events[0]["endTime"] is None


# ---------------------------------------------------------------------------
# poll_calendar() — async function tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_calendar_skips_when_url_not_set():
    """poll_calendar returns immediately without touching the cache when ICAL_FEED_URL is empty."""
    original = svc._cached_events
    try:
        svc._cached_events = [{"sentinel": True}]
        with patch.object(svc, "ICAL_FEED_URL", ""):
            await poll_calendar()
        # Cache must be untouched
        assert svc._cached_events == [{"sentinel": True}]
    finally:
        svc._cached_events = original


@pytest.mark.asyncio
async def test_poll_calendar_handles_network_failure():
    """Network error during calendar fetch is caught; _cached_events is not cleared."""
    original = svc._cached_events
    try:
        sentinel_events = [{"title": "Keep me", "time": None, "allDay": True}]
        svc._cached_events = sentinel_events.copy()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(svc, "ICAL_FEED_URL", "http://example.com/calendar.ics"),
            patch("shared.service.httpx.AsyncClient", return_value=mock_client),
        ):
            await poll_calendar()

        # Cache must be preserved after a network failure
        assert svc._cached_events == sentinel_events
    finally:
        svc._cached_events = original


@pytest.mark.asyncio
async def test_poll_calendar_handles_http_error_response():
    """HTTP error status (e.g. 500) is caught via raise_for_status; cache is preserved."""
    original = svc._cached_events
    try:
        sentinel_events = [{"title": "Keep me", "time": None, "allDay": True}]
        svc._cached_events = sentinel_events.copy()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(),
            )
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(svc, "ICAL_FEED_URL", "http://example.com/calendar.ics"),
            patch("shared.service.httpx.AsyncClient", return_value=mock_client),
        ):
            await poll_calendar()

        # Cache must be preserved after an HTTP error
        assert svc._cached_events == sentinel_events
    finally:
        svc._cached_events = original


@pytest.mark.asyncio
async def test_poll_calendar_handles_malformed_ical():
    """A parse error from malformed iCal bytes is caught; _cached_events is not cleared.

    This test exercises the real parse path: Calendar.from_ical() raises when given
    garbage data, and poll_calendar()'s broad except clause must absorb that error and
    leave the existing cache intact.
    """
    original = svc._cached_events
    try:
        sentinel_events = [{"title": "Keep me", "time": None, "allDay": True}]
        svc._cached_events = sentinel_events.copy()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        # Provide genuinely malformed iCal bytes so Calendar.from_ical() raises
        mock_response.text = "NOT-ICAL\x00\xff garbage data that no parser can handle"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(svc, "ICAL_FEED_URL", "http://example.com/calendar.ics"),
            patch("shared.service.httpx.AsyncClient", return_value=mock_client),
        ):
            await poll_calendar()

        # Cache must be preserved after a parse error
        assert svc._cached_events == sentinel_events
    finally:
        svc._cached_events = original


@pytest.mark.asyncio
async def test_poll_calendar_updates_cache_on_success():
    """On a successful fetch, _cached_events is replaced with parsed events."""
    original = svc._cached_events
    try:
        svc._cached_events = []

        valid_events = [{"title": "Standup", "time": "09:00", "allDay": False}]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        mock_response.text = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(svc, "ICAL_FEED_URL", "http://example.com/calendar.ics"),
            patch("shared.service.httpx.AsyncClient", return_value=mock_client),
            patch.object(svc, "parse_events_for_date", return_value=valid_events),
        ):
            await poll_calendar()

        assert svc._cached_events == valid_events
    finally:
        svc._cached_events = original
