"""Tests for generate-red-dashboard.py.

Covers:
- build_dashboard() returns a dict with required top-level keys
- Exactly 4 widgets with stable, well-known IDs
- Layout has 4 entries whose 'i' values match the widget IDs
- Sub-service variable lists all SUB_SERVICES route prefixes in customValue
- _service_filter() targets serviceName = monolith-backend
- _sub_service_filter() uses the {{.sub_service}} template variable
- _error_filter() targets hasError = true
- _base_query() includes extra_filters when provided
- _base_query() includes group_by when provided
- Latency widget sets yAxisUnit = 'ns'
- Error-count widget sets isStacked = True
"""

from __future__ import annotations

import importlib.util
import pathlib

# ---------------------------------------------------------------------------
# Import the module via importlib (filename contains a hyphen)
# ---------------------------------------------------------------------------

_SCRIPT = pathlib.Path(__file__).parent / "generate-red-dashboard.py"
_spec = importlib.util.spec_from_file_location("generate_red_dashboard", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_dashboard = _mod.build_dashboard
SUB_SERVICES = _mod.SUB_SERVICES
SERVICE_NAME = _mod.SERVICE_NAME
_service_filter = _mod._service_filter
_sub_service_filter = _mod._sub_service_filter
_error_filter = _mod._error_filter
_base_query = _mod._base_query
_query_wrapper = _mod._query_wrapper
_widget = _mod._widget

# Stable widget IDs that the sidecar relies on for upsert-vs-create decisions.
EXPECTED_WIDGET_IDS = {
    "red-request-rate",
    "red-error-count",
    "red-latency",
    "red-error-pct",
}


# ---------------------------------------------------------------------------
# build_dashboard – top-level structure
# ---------------------------------------------------------------------------


class TestBuildDashboardStructure:
    def test_returns_dict(self):
        d = build_dashboard()
        assert isinstance(d, dict)

    def test_required_top_level_keys(self):
        d = build_dashboard()
        for key in ("title", "description", "tags", "variables", "layout", "widgets"):
            assert key in d, f"Missing key: {key}"

    def test_title(self):
        d = build_dashboard()
        assert d["title"] == "Monolith RED Dashboard"

    def test_tags_include_expected_labels(self):
        d = build_dashboard()
        for tag in ("monolith", "red", "performance", "traces"):
            assert tag in d["tags"], f"Missing tag: {tag}"


# ---------------------------------------------------------------------------
# build_dashboard – widgets
# ---------------------------------------------------------------------------


class TestBuildDashboardWidgets:
    def test_exactly_four_widgets(self):
        d = build_dashboard()
        assert len(d["widgets"]) == 4

    def test_widget_ids_are_stable(self):
        d = build_dashboard()
        ids = {w["id"] for w in d["widgets"]}
        assert ids == EXPECTED_WIDGET_IDS

    def test_latency_widget_y_unit_ns(self):
        d = build_dashboard()
        latency = next(w for w in d["widgets"] if w["id"] == "red-latency")
        assert latency.get("yAxisUnit") == "ns"

    def test_error_count_widget_is_stacked(self):
        d = build_dashboard()
        error = next(w for w in d["widgets"] if w["id"] == "red-error-count")
        assert error["isStacked"] is True

    def test_non_stacked_widgets_are_not_stacked(self):
        """Rate, latency, and error-pct widgets should not be stacked."""
        d = build_dashboard()
        non_stacked_ids = EXPECTED_WIDGET_IDS - {"red-error-count"}
        for w in d["widgets"]:
            if w["id"] in non_stacked_ids:
                assert w["isStacked"] is False, (
                    f"Widget {w['id']} should not be stacked"
                )


# ---------------------------------------------------------------------------
# build_dashboard – layout
# ---------------------------------------------------------------------------


class TestBuildDashboardLayout:
    def test_layout_has_four_entries(self):
        d = build_dashboard()
        assert len(d["layout"]) == 4

    def test_layout_ids_match_widget_ids(self):
        d = build_dashboard()
        layout_ids = {entry["i"] for entry in d["layout"]}
        widget_ids = {w["id"] for w in d["widgets"]}
        assert layout_ids == widget_ids


# ---------------------------------------------------------------------------
# build_dashboard – variables
# ---------------------------------------------------------------------------


class TestBuildDashboardVariables:
    def test_exactly_one_variable(self):
        d = build_dashboard()
        assert len(d["variables"]) == 1

    def test_variable_name_is_sub_service(self):
        d = build_dashboard()
        var = next(iter(d["variables"].values()))
        assert var["name"] == "sub_service"

    def test_variable_type_is_custom(self):
        d = build_dashboard()
        var = next(iter(d["variables"].values()))
        assert var["type"] == "CUSTOM"

    def test_variable_custom_value_includes_all_route_prefixes(self):
        """Every SUB_SERVICES route prefix must appear in customValue."""
        d = build_dashboard()
        var = next(iter(d["variables"].values()))
        custom_values = var["customValue"]
        for prefix in SUB_SERVICES.values():
            assert prefix in custom_values, (
                f"Route prefix '{prefix}' missing from customValue: {custom_values}"
            )

    def test_variable_id_matches_key(self):
        """The dict key and the 'id' field inside the variable must agree."""
        d = build_dashboard()
        for key, var in d["variables"].items():
            assert var["id"] == key


# ---------------------------------------------------------------------------
# _service_filter
# ---------------------------------------------------------------------------


class TestServiceFilter:
    def test_key_is_service_name(self):
        f = _service_filter()
        assert f["key"]["key"] == "serviceName"

    def test_value_is_monolith_backend(self):
        f = _service_filter()
        assert f["value"] == SERVICE_NAME
        assert f["value"] == "monolith-backend"

    def test_op_is_equals(self):
        f = _service_filter()
        assert f["op"] == "="

    def test_is_column(self):
        f = _service_filter()
        assert f["key"]["isColumn"] is True


# ---------------------------------------------------------------------------
# _sub_service_filter
# ---------------------------------------------------------------------------


class TestSubServiceFilter:
    def test_uses_template_variable(self):
        f = _sub_service_filter()
        assert f["value"] == "{{.sub_service}}"

    def test_key_is_name(self):
        f = _sub_service_filter()
        assert f["key"]["key"] == "name"

    def test_op_is_contains(self):
        f = _sub_service_filter()
        assert f["op"] == "contains"


# ---------------------------------------------------------------------------
# _error_filter
# ---------------------------------------------------------------------------


class TestErrorFilter:
    def test_key_is_has_error(self):
        f = _error_filter()
        assert f["key"]["key"] == "hasError"

    def test_value_is_true(self):
        f = _error_filter()
        assert f["value"] == "true"

    def test_op_is_equals(self):
        f = _error_filter()
        assert f["op"] == "="

    def test_data_type_is_bool(self):
        f = _error_filter()
        assert f["key"]["dataType"] == "bool"


# ---------------------------------------------------------------------------
# _base_query
# ---------------------------------------------------------------------------


class TestBaseQuery:
    def test_always_includes_service_and_sub_service_filters(self):
        q = _base_query("A", "count")
        items = q["filters"]["items"]
        keys = [item["key"]["key"] for item in items]
        assert "serviceName" in keys
        assert "name" in keys

    def test_extra_filters_are_merged(self):
        extra = _error_filter()
        q = _base_query("A", "count", extra_filters=[extra])
        items = q["filters"]["items"]
        keys = [item["key"]["key"] for item in items]
        assert "hasError" in keys
        assert len(items) == 3  # service + sub_service + hasError

    def test_no_extra_filters_gives_two_items(self):
        q = _base_query("A", "count")
        assert len(q["filters"]["items"]) == 2

    def test_group_by_is_set(self):
        gb = [
            {
                "key": "name",
                "dataType": "string",
                "type": "tag",
                "isColumn": True,
                "isJSON": False,
            }
        ]
        q = _base_query("A", "rate", group_by=gb)
        assert q["groupBy"] == gb

    def test_no_group_by_gives_empty_list(self):
        q = _base_query("A", "count")
        assert q["groupBy"] == []

    def test_query_name_is_set(self):
        q = _base_query("B", "p95")
        assert q["queryName"] == "B"

    def test_aggregate_operator_is_set(self):
        q = _base_query("A", "p50")
        assert q["aggregateOperator"] == "p50"

    def test_data_source_is_traces(self):
        q = _base_query("A", "rate")
        assert q["dataSource"] == "traces"

    def test_filters_op_is_and(self):
        q = _base_query("A", "count")
        assert q["filters"]["op"] == "AND"

    def test_agg_attr_sets_aggregate_attribute(self):
        """When agg_attr is provided, aggregateAttribute should equal that value."""
        attr = {
            "key": "durationNano",
            "dataType": "float64",
            "type": "tag",
            "isColumn": True,
            "isJSON": False,
        }
        q = _base_query("A", "p50", agg_attr=attr)
        assert q["aggregateAttribute"] == attr

    def test_no_agg_attr_gives_empty_dict(self):
        """Without agg_attr, aggregateAttribute defaults to {}."""
        q = _base_query("A", "count")
        assert q["aggregateAttribute"] == {}

    def test_legend_propagates(self):
        """When legend is provided, it appears verbatim in the query."""
        q = _base_query("A", "rate", legend="p50")
        assert q["legend"] == "p50"

    def test_default_legend_is_empty_string(self):
        q = _base_query("A", "count")
        assert q["legend"] == ""


# ---------------------------------------------------------------------------
# _query_wrapper
# ---------------------------------------------------------------------------


class TestQueryWrapper:
    def test_query_type_is_builder(self):
        w = _query_wrapper([])
        assert w["queryType"] == "builder"

    def test_query_data_is_stored(self):
        qd = [_base_query("A", "rate")]
        w = _query_wrapper(qd)
        assert w["builder"]["queryData"] == qd

    def test_no_formulas_gives_empty_list(self):
        """When query_formulas is omitted, builder.queryFormulas should be []."""
        w = _query_wrapper([])
        assert w["builder"]["queryFormulas"] == []

    def test_non_empty_query_formulas_are_stored(self):
        """When query_formulas is provided, builder.queryFormulas is populated."""
        formula = {
            "queryName": "F1",
            "expression": "A*100/B",
            "disabled": False,
            "legend": "error %",
            "stepInterval": 60,
            "dataSource": "traces",
            "groupBy": [],
            "having": {"expression": ""},
            "limit": None,
            "orderBy": [],
            "selectColumns": [],
            "functions": [],
            "aggregations": [],
        }
        w = _query_wrapper([_base_query("A", "count")], query_formulas=[formula])
        assert w["builder"]["queryFormulas"] == [formula]
        assert len(w["builder"]["queryFormulas"]) == 1


# ---------------------------------------------------------------------------
# _widget
# ---------------------------------------------------------------------------


class TestWidget:
    def test_id_is_set(self):
        q = _query_wrapper([_base_query("A", "rate")])
        w = _widget("my-id", "Title", "Desc", q)
        assert w["id"] == "my-id"

    def test_title_is_set(self):
        q = _query_wrapper([_base_query("A", "rate")])
        w = _widget("id1", "My Title", "Desc", q)
        assert w["title"] == "My Title"

    def test_without_y_unit_key_is_absent(self):
        """When y_unit is not provided, 'yAxisUnit' must not be present in the widget."""
        q = _query_wrapper([_base_query("A", "rate")])
        w = _widget("id1", "Title", "Desc", q)
        assert "yAxisUnit" not in w

    def test_with_y_unit_key_is_present(self):
        """When y_unit is provided, 'yAxisUnit' should appear with that value."""
        q = _query_wrapper([_base_query("A", "p50")])
        w = _widget("id1", "Title", "Desc", q, y_unit="ns")
        assert w["yAxisUnit"] == "ns"

    def test_stacked_true_sets_is_stacked(self):
        """When stacked=True, isStacked must be True in the returned dict."""
        q = _query_wrapper([_base_query("A", "count")])
        w = _widget("id1", "Title", "Desc", q, stacked=True)
        assert w["isStacked"] is True

    def test_stacked_false_by_default(self):
        q = _query_wrapper([_base_query("A", "count")])
        w = _widget("id1", "Title", "Desc", q)
        assert w["isStacked"] is False

    def test_query_is_embedded(self):
        q = _query_wrapper([_base_query("A", "rate")])
        w = _widget("id1", "Title", "Desc", q)
        assert w["query"] == q


# ---------------------------------------------------------------------------
# build_dashboard – description mentions all sub-service keys
# ---------------------------------------------------------------------------


class TestBuildDashboardDescription:
    def test_description_contains_all_sub_service_keys(self):
        """Dashboard description must mention every key in SUB_SERVICES."""
        d = build_dashboard()
        description = d["description"]
        for key in SUB_SERVICES.keys():
            assert key in description, (
                f"SUB_SERVICES key '{key}' not found in dashboard description: {description!r}"
            )
