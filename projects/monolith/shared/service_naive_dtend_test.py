"""Tests for naive (no-tzinfo) DTEND datetime handling in shared/service.py.

The ``parse_events_for_date`` function handles three DTEND variants:
  1. timezone-aware datetime  → ``dte.astimezone(tz)``   (covered in service_extra_test.py)
  2. date object (not datetime) → ``end_str = None``     (covered in service_extra_test.py)
  3. naive datetime (tzinfo is None) → ``dte.replace(tzinfo=tz)``   ← THIS FILE

The third path is the ``if dte.tzinfo is None:`` branch at lines 58–59 of
service.py.  It was identified as an untested branch in the coverage review.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from shared.service import parse_events_for_date

TZ = ZoneInfo("America/Vancouver")

# ---------------------------------------------------------------------------
# ICS fixtures
# ---------------------------------------------------------------------------

# Naive DTSTART and naive DTEND (no timezone indicator — no trailing Z, no
# TZID parameter).  icalendar parses these as naive datetime objects.
NAIVE_DTEND_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T090000
DTEND:20260330T100000
SUMMARY:Naive DTEND Event
END:VEVENT
END:VCALENDAR
"""

# Both DTSTART and DTEND are naive, and the event lands on the target date.
NAIVE_DTEND_SAME_DAY_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260401T140000
DTEND:20260401T153000
SUMMARY:Afternoon Meeting
END:VEVENT
END:VCALENDAR
"""

# Naive DTEND where DTSTART is also naive but cross-midnight (DTEND next day).
# The DTEND's date changes once tzinfo is applied, but we still return the
# correct end_str because we only format the time, not the date.
NAIVE_DTEND_CROSS_MIDNIGHT_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T230000
DTEND:20260331T010000
SUMMARY:Late Night Event
END:VEVENT
END:VCALENDAR
"""

# Naive DTSTART that, after replace(tzinfo=tz), matches a different date than
# the naive dt.date() value — verifies the correct branch is exercised for the
# event's timezone-aware date comparison.  For simplicity we put the event on
# the target date with no cross-day shift.
NAIVE_DTEND_EXPLICIT_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260401T080000
DTEND:20260401T083000
SUMMARY:Morning Standup
END:VEVENT
END:VCALENDAR
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNaiveDtend:
    """Exercises the ``dte.tzinfo is None`` branch inside ``parse_events_for_date``."""

    def test_naive_dtend_produces_end_time_string(self):
        """A naive DTEND datetime yields a non-None endTime in the returned event."""
        events = parse_events_for_date(NAIVE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert len(events) == 1
        # endTime must be a non-None string (naive path calls dte.replace(tzinfo=tz))
        assert events[0]["endTime"] is not None
        assert isinstance(events[0]["endTime"], str)

    def test_naive_dtend_end_time_value(self):
        """A naive DTEND of 10:00 (local) is formatted as '10:00'."""
        events = parse_events_for_date(NAIVE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert events[0]["endTime"] == "10:00"

    def test_naive_dtend_event_is_not_all_day(self):
        """An event with a naive DTEND is allDay=False."""
        events = parse_events_for_date(NAIVE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert events[0]["allDay"] is False

    def test_naive_dtend_title_preserved(self):
        """The event title is preserved when DTEND is naive."""
        events = parse_events_for_date(NAIVE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert events[0]["title"] == "Naive DTEND Event"

    def test_naive_dtend_different_date_produces_end_time(self):
        """A different event with naive DTEND also produces a correct endTime."""
        events = parse_events_for_date(NAIVE_DTEND_SAME_DAY_ICS, date(2026, 4, 1), TZ)
        assert len(events) == 1
        assert events[0]["endTime"] == "15:30"
        assert events[0]["title"] == "Afternoon Meeting"

    def test_naive_dtend_explicit_short_event(self):
        """Naive 30-minute event with DTEND yields correct endTime."""
        events = parse_events_for_date(NAIVE_DTEND_EXPLICIT_ICS, date(2026, 4, 1), TZ)
        assert len(events) == 1
        assert events[0]["endTime"] == "08:30"

    def test_naive_dtend_event_excluded_when_wrong_date_requested(self):
        """Requesting a different date excludes the naive-DTEND event."""
        # Event is on 2026-03-30; requesting 2026-03-31 should return nothing.
        events = parse_events_for_date(NAIVE_DTEND_ICS, date(2026, 3, 31), TZ)
        assert events == []

    def test_naive_dtend_cross_midnight_start_time_correct(self):
        """A cross-midnight event with naive DTSTART/DTEND has the right start time."""
        # DTSTART is 23:00 on 2026-03-30 (naive → replace with TZ → still same date)
        events = parse_events_for_date(
            NAIVE_DTEND_CROSS_MIDNIGHT_ICS, date(2026, 3, 30), TZ
        )
        assert len(events) == 1
        assert events[0]["time"] == "23:00"
