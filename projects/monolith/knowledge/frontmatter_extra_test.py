"""Extra coverage tests for knowledge.frontmatter — uncovered branches."""

from datetime import datetime, timezone

import pytest

from knowledge.frontmatter import FrontmatterError, ParsedFrontmatter, _edges, _to_datetime, parse


# ---------------------------------------------------------------------------
# _edges — non-dict input
# ---------------------------------------------------------------------------


class TestEdgesExtra:
    def test_edges_list_value_returns_empty_with_warning(self, caplog):
        """If edges is a list (not a mapping), warn and return {}."""
        import logging

        with caplog.at_level(logging.WARNING):
            result = _edges(["refines", "related"])

        assert result == {}
        assert any("not a mapping" in r.message for r in caplog.records)

    def test_edges_string_value_returns_empty_with_warning(self, caplog):
        """If edges is a plain string (not a mapping), warn and return {}."""
        import logging

        with caplog.at_level(logging.WARNING):
            result = _edges("refines: parent")

        assert result == {}
        assert any("not a mapping" in r.message for r in caplog.records)

    def test_edges_integer_value_returns_empty_with_warning(self, caplog):
        """If edges is an integer (not a mapping), warn and return {}."""
        import logging

        with caplog.at_level(logging.WARNING):
            result = _edges(42)

        assert result == {}

    def test_edges_none_returns_empty(self):
        """None edges returns empty dict without logging."""
        assert _edges(None) == {}

    def test_edges_unknown_key_is_dropped_with_warning(self, caplog):
        """A known edge type is kept; an unknown one is dropped with a warning."""
        import logging

        with caplog.at_level(logging.WARNING):
            result = _edges({"refines": ["parent"], "invented_type": ["x"]})

        assert "refines" in result
        assert "invented_type" not in result
        assert any("unknown edge type" in r.message for r in caplog.records)

    def test_edges_numeric_key_coerced_to_string_then_dropped(self, caplog):
        """A numeric dict key is coerced to str; since it's not a known edge type, it's dropped."""
        import logging

        with caplog.at_level(logging.WARNING):
            # Key 123 → str("123") → not in _KNOWN_EDGE_TYPES → dropped
            result = _edges({123: ["some-target"]})

        assert result == {}
        assert any("unknown edge type" in r.message for r in caplog.records)

    def test_edges_empty_target_list_not_included(self):
        """An edge type with an empty target list is omitted from output."""
        result = _edges({"refines": [], "related": ["a"]})
        assert "refines" not in result
        assert result == {"related": ["a"]}

    def test_edges_via_parse_non_dict_block_warns(self, caplog):
        """When a YAML frontmatter edges block is a list, parse logs a warning."""
        import logging

        raw = "---\nedges:\n  - refines\n  - related\n---\nbody"
        with caplog.at_level(logging.WARNING):
            meta, _ = parse(raw)

        assert meta.edges == {}
        assert any("not a mapping" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _to_datetime — uncovered branches
# ---------------------------------------------------------------------------


class TestToDatetimeExtra:
    def test_already_aware_datetime_passes_through_unchanged(self):
        """A timezone-aware datetime is returned as-is (tzinfo preserved)."""
        dt = datetime(2017, 6, 12, 15, 30, tzinfo=timezone.utc)
        result = _to_datetime(dt)
        assert result == dt
        assert result.tzinfo is timezone.utc

    def test_naive_datetime_gets_utc_tzinfo(self):
        """A naive datetime is tagged with UTC."""
        from datetime import datetime

        naive = datetime(2023, 1, 1, 12, 0)
        result = _to_datetime(naive)
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2023

    def test_date_object_converted_to_midnight_utc(self):
        """A date object (not datetime) is converted to midnight UTC datetime."""
        from datetime import date

        d = date(2024, 3, 15)
        result = _to_datetime(d)
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.hour == 0
        assert result.tzinfo == timezone.utc

    def test_integer_type_warns_and_returns_none(self, caplog):
        """An integer value (unparseable date type) logs a warning and returns None."""
        import logging

        with caplog.at_level(logging.WARNING):
            result = _to_datetime(12345)

        assert result is None
        assert any("unparseable date type" in r.message for r in caplog.records)

    def test_invalid_isoformat_string_warns_and_returns_none(self, caplog):
        """A non-ISO string logs a warning and returns None."""
        import logging

        with caplog.at_level(logging.WARNING):
            result = _to_datetime("not-a-date-at-all")

        assert result is None
        assert any("invalid date" in r.message for r in caplog.records)

    def test_isoformat_string_without_timezone_gets_utc(self):
        """An ISO string without timezone gets UTC tzinfo added."""
        result = _to_datetime("2023-06-01T12:00:00")
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2023
        assert result.hour == 12

    def test_aware_datetime_via_parse(self):
        """YAML frontmatter with timezone-aware datetime preserves tzinfo."""
        # PyYAML parses UTC-offset datetimes as timezone-aware datetime objects
        raw = "---\ncreated: 2017-06-12T15:30:00+00:00\n---\nbody"
        meta, _ = parse(raw)
        assert meta.created is not None
        assert meta.created.tzinfo is not None
        assert meta.created.year == 2017
        assert meta.created.hour == 15

    def test_date_string_via_parse_gets_utc(self):
        """YAML date value (parsed as datetime.date) is converted to UTC datetime."""
        # '2017-06-12' in YAML → datetime.date(2017, 6, 12) → _to_datetime date-like branch
        raw = "---\ncreated: 2017-06-12\n---\nbody"
        meta, _ = parse(raw)
        assert meta.created is not None
        assert meta.created.year == 2017
        assert meta.created.month == 6
        assert meta.created.day == 12
        assert meta.created.tzinfo == timezone.utc

    def test_none_returns_none(self):
        """None input returns None (no datetime)."""
        assert _to_datetime(None) is None
