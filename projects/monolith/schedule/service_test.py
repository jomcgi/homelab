from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from schedule.service import parse_events_for_date

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
