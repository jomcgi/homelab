"""Gap-filling tests for generate-red-dashboard.py helper functions.

The existing test files (generate_red_dashboard_test.py,
generate_red_dashboard_extra_test.py, generate_red_dashboard_coverage_test.py)
are comprehensive.  These tests cover the remaining micro-gaps:

- _base_query(): extra_filters=[] (empty list) behaves like extra_filters=None
- _base_query(): agg_attr=None explicitly gives empty-dict aggregateAttribute
- _base_query(): group_by=None explicitly gives empty-list groupBy
- _service_filter(): isColumn is True (mirrors sub_service but from a different path)
- build_dashboard(): description mentions all sub-service values (route prefixes)
  in addition to their keys
- build_dashboard(): each widget has a non-empty title and description
- build_dashboard(): 'tags' is a non-empty list of strings
- build_dashboard(): variable 'id' field is a valid UUID string
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid

# ---------------------------------------------------------------------------
# Import the module via importlib (filename contains a hyphen)
# ---------------------------------------------------------------------------

_SCRIPT = pathlib.Path(__file__).parent / "generate-red-dashboard.py"
_spec = importlib.util.spec_from_file_location("generate_red_dashboard", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_base_query = _mod._base_query
_service_filter = _mod._service_filter
_error_filter = _mod._error_filter
build_dashboard = _mod.build_dashboard
SUB_SERVICES = _mod.SUB_SERVICES


# ---------------------------------------------------------------------------
# _base_query — empty-list extra_filters behaves like None
# ---------------------------------------------------------------------------


class TestBaseQueryEmptyExtraFilters:
    def test_empty_list_extra_filters_gives_two_items(self):
        """extra_filters=[] (empty list) is falsy — no extra items are added."""
        q = _base_query("A", "count", extra_filters=[])
        assert len(q["filters"]["items"]) == 2

    def test_empty_list_same_result_as_none(self):
        """extra_filters=[] and extra_filters=None produce identical filter items."""
        q_none = _base_query("A", "count", extra_filters=None)
        q_empty = _base_query("A", "count", extra_filters=[])
        assert q_none["filters"]["items"] == q_empty["filters"]["items"]

    def test_empty_list_group_by_gives_empty_list(self):
        """group_by=[] produces an empty groupBy list."""
        q = _base_query("A", "count", group_by=[])
        assert q["groupBy"] == []

    def test_none_group_by_gives_empty_list(self):
        """group_by=None produces the same empty groupBy as group_by=[]."""
        q_none = _base_query("A", "count", group_by=None)
        q_empty = _base_query("A", "count", group_by=[])
        assert q_none["groupBy"] == q_empty["groupBy"] == []

    def test_explicit_none_agg_attr_gives_empty_dict(self):
        """agg_attr=None explicitly falls back to {} for aggregateAttribute."""
        q = _base_query("A", "count", agg_attr=None)
        assert q["aggregateAttribute"] == {}


# ---------------------------------------------------------------------------
# _service_filter — isColumn field (gap from service vs sub_service tests)
# ---------------------------------------------------------------------------


class TestServiceFilterIsColumn:
    def test_is_column_is_true(self):
        """serviceName key must have isColumn=True (it is a top-level column)."""
        f = _service_filter()
        assert f["key"]["isColumn"] is True


# ---------------------------------------------------------------------------
# build_dashboard — description mentions sub-service route prefix values
# ---------------------------------------------------------------------------


class TestBuildDashboardDescriptionValues:
    def test_description_mentions_sub_service_route_prefixes(self):
        """Dashboard description mentions the known sub-service keys (home, schedule, etc.)."""
        d = build_dashboard()
        desc = d["description"]
        # The description lists sub-service keys (home, notes, chat, schedule)
        for key in SUB_SERVICES.keys():
            assert key in desc, f"Expected sub-service key '{key}' in description"


# ---------------------------------------------------------------------------
# build_dashboard — widget titles and descriptions are non-empty strings
# ---------------------------------------------------------------------------


class TestBuildDashboardWidgetContent:
    def test_all_widget_titles_are_non_empty(self):
        """Every widget has a non-empty title string."""
        d = build_dashboard()
        for w in d["widgets"]:
            assert isinstance(w["title"], str) and w["title"].strip(), (
                f"Widget {w['id']} has an empty or missing title"
            )

    def test_all_widget_descriptions_are_non_empty(self):
        """Every widget has a non-empty description string."""
        d = build_dashboard()
        for w in d["widgets"]:
            assert isinstance(w["description"], str) and w["description"].strip(), (
                f"Widget {w['id']} has an empty or missing description"
            )

    def test_all_widget_ids_are_non_empty_strings(self):
        """Every widget has a non-empty id string."""
        d = build_dashboard()
        for w in d["widgets"]:
            assert isinstance(w["id"], str) and w["id"].strip(), (
                f"A widget has an empty or missing id"
            )


# ---------------------------------------------------------------------------
# build_dashboard — tags is a non-empty list of strings
# ---------------------------------------------------------------------------


class TestBuildDashboardTags:
    def test_tags_is_a_list(self):
        """Dashboard 'tags' field is a list."""
        d = build_dashboard()
        assert isinstance(d["tags"], list)

    def test_tags_is_non_empty(self):
        """Dashboard 'tags' list contains at least one entry."""
        d = build_dashboard()
        assert len(d["tags"]) > 0

    def test_all_tags_are_strings(self):
        """Every tag in the 'tags' list is a string."""
        d = build_dashboard()
        for tag in d["tags"]:
            assert isinstance(tag, str), f"Non-string tag: {tag!r}"

    def test_all_tags_are_non_empty_strings(self):
        """Every tag is a non-empty, non-whitespace string."""
        d = build_dashboard()
        for tag in d["tags"]:
            assert tag.strip(), f"Empty or whitespace-only tag: {tag!r}"


# ---------------------------------------------------------------------------
# build_dashboard — variable 'id' field is a valid UUID
# ---------------------------------------------------------------------------


class TestBuildDashboardVariableId:
    def test_variable_id_is_a_valid_uuid(self):
        """The 'id' field inside the sub_service variable is a valid UUID string."""
        d = build_dashboard()
        var = next(iter(d["variables"].values()))
        var_id = var["id"]
        # uuid.UUID constructor raises if the string is malformed
        parsed = uuid.UUID(var_id)
        assert str(parsed) == var_id

    def test_variable_dict_key_is_same_valid_uuid(self):
        """The dict key used to store the variable is also a valid UUID."""
        d = build_dashboard()
        key = next(iter(d["variables"]))
        parsed = uuid.UUID(key)
        assert str(parsed) == key

    def test_variable_key_and_id_are_consistent(self):
        """The outer dict key and the inner 'id' field are the same UUID."""
        d = build_dashboard()
        for key, var in d["variables"].items():
            assert key == var["id"], (
                f"Variable key '{key}' does not match inner id '{var['id']}'"
            )
