"""Extra coverage tests for shared/service.py — timezone-aware events,
date-type DTEND, get_today_events(), and DTSTART with no value."""

from datetime import date
from unittest.mock import patch
from zoneinfo import ZoneInfo

import shared.service as svc
from shared.service import get_today_events, parse_events_for_date

TZ = ZoneInfo("America/Vancouver")


# ---------------------------------------------------------------------------
# get_today_events
# ---------------------------------------------------------------------------


class TestGetTodayEvents:
    def test_returns_empty_list_when_cache_empty(self):
        """get_today_events returns [] when the in-memory cache is unpopulated."""
        # Patch the module-level cache to be empty
        with patch.object(svc, "_cached_events", []):
            result = get_today_events()
        assert result == []

    def test_returns_copy_of_cached_events(self):
        """get_today_events returns a shallow copy, not the original list."""
        fake_events = [{"time": "09:00", "title": "Standup", "allDay": False}]
        with patch.object(svc, "_cached_events", fake_events):
            result = get_today_events()
        assert result == fake_events
        assert result is not fake_events  # must be a copy

    def test_mutation_of_result_does_not_affect_cache(self):
        """Mutating the returned list does not change the internal cache."""
        original = [{"title": "Meeting"}]
        with patch.object(svc, "_cached_events", list(original)):
            result = get_today_events()
            result.append({"title": "Extra"})
            # Re-read the cache
            assert len(get_today_events()) == 1

    def test_returns_all_cached_events(self):
        """get_today_events returns every item in the cache."""
        fake_events = [
            {"time": None, "title": "Holiday", "allDay": True},
            {"time": "10:00", "title": "Sync", "allDay": False},
            {"time": "14:00", "title": "Demo", "allDay": False},
        ]
        with patch.object(svc, "_cached_events", fake_events):
            result = get_today_events()
        assert len(result) == 3


# ---------------------------------------------------------------------------
# parse_events_for_date — timezone-aware DTSTART
# ---------------------------------------------------------------------------

# ICS with a UTC-stamped timed event on 2026-03-30
TIMEZONE_AWARE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T170000Z
DTEND:20260330T183000Z
SUMMARY:UTC Meeting
END:VEVENT
END:VCALENDAR
"""

# ICS where DTEND is a date value (not a datetime)
DATE_DTEND_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T090000
DTEND;VALUE=DATE:20260331
SUMMARY:Standup with date DTEND
END:VEVENT
END:VCALENDAR
"""

# ICS where DTSTART element is absent (malformed, should be skipped)
MISSING_DTSTART_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:No Start Time
DTEND:20260330T100000
END:VEVENT
BEGIN:VEVENT
DTSTART:20260330T110000
SUMMARY:Valid Event
END:VEVENT
END:VCALENDAR
"""


class TestParseEventsTimezoneAware:
    def test_utc_event_converted_to_target_tz(self):
        """A UTC DTSTART is converted to the target timezone for date matching."""
        # 2026-03-30T17:00:00Z  ==  2026-03-30T10:00:00 America/Vancouver
        events = parse_events_for_date(TIMEZONE_AWARE_ICS, date(2026, 3, 30), TZ)
        assert len(events) == 1
        assert events[0]["title"] == "UTC Meeting"
        assert events[0]["allDay"] is False

    def test_utc_event_time_converted_correctly(self):
        """Time field reflects the target-timezone local time, not UTC."""
        events = parse_events_for_date(TIMEZONE_AWARE_ICS, date(2026, 3, 30), TZ)
        assert events[0]["time"] == "10:00"  # UTC 17:00 → Vancouver 10:00

    def test_utc_event_end_time_converted(self):
        """endTime field is also converted from UTC to the target timezone."""
        events = parse_events_for_date(TIMEZONE_AWARE_ICS, date(2026, 3, 30), TZ)
        assert events[0]["endTime"] == "11:30"  # UTC 18:30 → Vancouver 11:30

    def test_utc_event_excluded_for_wrong_date(self):
        """UTC event is excluded when asking for a different local date."""
        events = parse_events_for_date(TIMEZONE_AWARE_ICS, date(2026, 3, 29), TZ)
        assert events == []


class TestParseEventsDateTypeDtend:
    def test_date_dtend_yields_none_end_time(self):
        """When DTEND is a date value (not datetime), endTime is None."""
        events = parse_events_for_date(DATE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert len(events) == 1
        assert events[0]["endTime"] is None

    def test_date_dtend_event_still_included(self):
        """An event with a date-type DTEND is still returned."""
        events = parse_events_for_date(DATE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert events[0]["title"] == "Standup with date DTEND"

    def test_date_dtend_allday_false(self):
        """A timed event is still allDay=False even with a date-type DTEND."""
        events = parse_events_for_date(DATE_DTEND_ICS, date(2026, 3, 30), TZ)
        assert events[0]["allDay"] is False


class TestParseEventsMissingDtstart:
    def test_event_without_dtstart_is_skipped(self):
        """A VEVENT component without DTSTART is silently skipped."""
        events = parse_events_for_date(MISSING_DTSTART_ICS, date(2026, 3, 30), TZ)
        # Only the valid event (11:00) should be returned
        assert len(events) == 1
        assert events[0]["title"] == "Valid Event"

    def test_valid_event_after_missing_dtstart_is_included(self):
        """Events following a malformed VEVENT are still processed."""
        events = parse_events_for_date(MISSING_DTSTART_ICS, date(2026, 3, 30), TZ)
        assert events[0]["time"] == "11:00"
