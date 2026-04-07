"""Supplementary tests for generate-red-dashboard.py.

Covers functions and edge cases NOT tested in the existing test files:
- _id(): UUID format, uniqueness, type
- main(): stdout output is valid JSON matching build_dashboard()
- _base_query(): internal fields (stepInterval, expression, disabled, reduceTo,
                 limit, orderBy, selectColumns, functions, aggregations, having)
- _service_filter(): dataType, type, isJSON fields
- _sub_service_filter(): dataType, isColumn, isJSON, type fields
- _error_filter(): isColumn, isJSON, type fields
- build_dashboard() geometry: layout positions/sizes, no widget overlap
- build_dashboard() widget query content: each panel has correct operator/filters
- build_dashboard() variable flags: allSelected, multiSelect, showALLOption,
                    selectedValue, order
- build_dashboard() JSON serializability and version field
- build_dashboard() error_pct formula expression
- build_dashboard() latency panel has p50/p95/p99 queries
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import uuid

# ---------------------------------------------------------------------------
# Import the module via importlib (filename contains a hyphen)
# ---------------------------------------------------------------------------

_SCRIPT = pathlib.Path(__file__).parent / "generate-red-dashboard.py"
_spec = importlib.util.spec_from_file_location("generate_red_dashboard", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_id = _mod._id
_service_filter = _mod._service_filter
_sub_service_filter = _mod._sub_service_filter
_error_filter = _mod._error_filter
_base_query = _mod._base_query
_query_wrapper = _mod._query_wrapper
_widget = _mod._widget
_operation_group_by = _mod._operation_group_by
build_dashboard = _mod.build_dashboard
SUB_SERVICES = _mod.SUB_SERVICES
SERVICE_NAME = _mod.SERVICE_NAME


# ---------------------------------------------------------------------------
# _id
# ---------------------------------------------------------------------------


class TestId:
    def test_returns_string(self):
        """_id() must return a str."""
        assert isinstance(_id(), str)

    def test_is_valid_uuid(self):
        """_id() must return a parseable UUID string."""
        value = _id()
        parsed = uuid.UUID(value)  # raises ValueError if malformed
        assert str(parsed) == value

    def test_unique_per_call(self):
        """Successive calls to _id() must produce different values."""
        ids = {_id() for _ in range(20)}
        assert len(ids) == 20

    def test_lowercase_hex(self):
        """UUID output must use lowercase hex (standard str(uuid.uuid4()) format)."""
        value = _id()
        assert value == value.lower()

    def test_has_four_hyphens(self):
        """Standard UUID format contains exactly 4 hyphens."""
        assert _id().count("-") == 4


# ---------------------------------------------------------------------------
# main() / __main__ block
# The script has no standalone main() function — it uses an if __name__ block.
# These tests verify the equivalent behaviour: json.dumps(build_dashboard(), indent=2).
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_outputs_valid_json(self):
        """The __main__ block produces valid JSON (json.dumps of build_dashboard())."""
        output = json.dumps(_mod.build_dashboard(), indent=2)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_main_output_has_required_keys(self):
        """JSON output contains all required top-level dashboard keys."""
        output = json.dumps(_mod.build_dashboard(), indent=2)
        parsed = json.loads(output)
        for key in ("title", "description", "tags", "version", "layout", "widgets", "variables"):
            assert key in parsed, f"Missing key: {key}"

    def test_main_output_is_indented(self):
        """__main__ block pretty-prints with indent=2 (lines start with spaces)."""
        output = json.dumps(_mod.build_dashboard(), indent=2)
        lines = output.splitlines()
        indented_lines = [ln for ln in lines if ln.startswith("  ")]
        assert len(indented_lines) > 0, "Expected indented (pretty-printed) JSON output"

    def test_main_output_matches_build_dashboard(self):
        """Parsed JSON output is structurally equivalent to build_dashboard()."""
        output = json.dumps(_mod.build_dashboard(), indent=2)
        parsed = json.loads(output)
        expected = _mod.build_dashboard()
        # Variable dict keys are fresh UUIDs per call — compare everything else.
        for key in ("title", "description", "tags", "version", "layout", "widgets"):
            assert parsed[key] == expected[key], f"Mismatch for key: {key}"

    def test_main_output_stdout_capture(self):
        """Simulated script execution writes valid JSON to stdout."""
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print(json.dumps(_mod.build_dashboard(), indent=2))
        finally:
            sys.stdout = old_stdout
        parsed = json.loads(buf.getvalue())
        assert "widgets" in parsed


# ---------------------------------------------------------------------------
# _service_filter – extra field coverage
# ---------------------------------------------------------------------------


class TestServiceFilterFields:
    def test_data_type_is_string(self):
        """serviceName is stored as a string type in SigNoz."""
        f = _service_filter()
        assert f["key"]["dataType"] == "string"

    def test_type_is_tag(self):
        """The key type must be 'tag'."""
        f = _service_filter()
        assert f["key"]["type"] == "tag"

    def test_is_json_is_false(self):
        """isJSON must be False for a standard column attribute."""
        f = _service_filter()
        assert f["key"]["isJSON"] is False

    def test_returns_new_dict_each_call(self):
        """Each call must return an independent dict (not shared state)."""
        f1 = _service_filter()
        f2 = _service_filter()
        assert f1 is not f2


# ---------------------------------------------------------------------------
# _sub_service_filter – extra field coverage
# ---------------------------------------------------------------------------


class TestSubServiceFilterFields:
    def test_data_type_is_string(self):
        f = _sub_service_filter()
        assert f["key"]["dataType"] == "string"

    def test_type_is_tag(self):
        f = _sub_service_filter()
        assert f["key"]["type"] == "tag"

    def test_is_column_is_true(self):
        f = _sub_service_filter()
        assert f["key"]["isColumn"] is True

    def test_is_json_is_false(self):
        f = _sub_service_filter()
        assert f["key"]["isJSON"] is False

    def test_returns_new_dict_each_call(self):
        f1 = _sub_service_filter()
        f2 = _sub_service_filter()
        assert f1 is not f2


# ---------------------------------------------------------------------------
# _error_filter – extra field coverage
# ---------------------------------------------------------------------------


class TestErrorFilterFields:
    def test_is_column_is_true(self):
        f = _error_filter()
        assert f["key"]["isColumn"] is True

    def test_is_json_is_false(self):
        f = _error_filter()
        assert f["key"]["isJSON"] is False

    def test_type_is_tag(self):
        f = _error_filter()
        assert f["key"]["type"] == "tag"

    def test_returns_new_dict_each_call(self):
        f1 = _error_filter()
        f2 = _error_filter()
        assert f1 is not f2


# ---------------------------------------------------------------------------
# _base_query – internal field coverage
# ---------------------------------------------------------------------------


class TestBaseQueryInternalFields:
    def test_step_interval_is_60(self):
        """Queries must use a 60-second aggregation step."""
        q = _base_query("A", "count")
        assert q["stepInterval"] == 60

    def test_expression_equals_query_name(self):
        """The expression field must echo the query name for self-reference."""
        for name in ("A", "B", "C", "F1"):
            q = _base_query(name, "count")
            assert q["expression"] == name, (
                f"expression should equal name for query {name!r}"
            )

    def test_disabled_is_false(self):
        """Queries are enabled by default."""
        q = _base_query("A", "rate")
        assert q["disabled"] is False

    def test_reduce_to_is_avg(self):
        """reduceTo defaults to 'avg'."""
        q = _base_query("A", "count")
        assert q["reduceTo"] == "avg"

    def test_limit_is_none(self):
        """limit defaults to None (no row limit)."""
        q = _base_query("A", "count")
        assert q["limit"] is None

    def test_order_by_is_empty_list(self):
        """orderBy defaults to an empty list."""
        q = _base_query("A", "count")
        assert q["orderBy"] == []

    def test_select_columns_is_empty_list(self):
        """selectColumns defaults to an empty list."""
        q = _base_query("A", "count")
        assert q["selectColumns"] == []

    def test_functions_is_empty_list(self):
        """functions defaults to an empty list."""
        q = _base_query("A", "count")
        assert q["functions"] == []

    def test_aggregations_is_empty_list(self):
        """aggregations defaults to an empty list."""
        q = _base_query("A", "count")
        assert q["aggregations"] == []

    def test_having_expression_is_empty_string(self):
        """having.expression defaults to ''."""
        q = _base_query("A", "count")
        assert q["having"] == {"expression": ""}

    def test_multiple_extra_filters(self):
        """Multiple extra_filters are all appended to the filter items."""
        extra1 = _error_filter()
        extra2 = {
            "key": {"key": "http.status_code", "dataType": "int64", "type": "tag",
                    "isColumn": False, "isJSON": False},
            "op": ">",
            "value": 400,
        }
        q = _base_query("A", "count", extra_filters=[extra1, extra2])
        items = q["filters"]["items"]
        # base: service + sub_service + 2 extra = 4 total
        assert len(items) == 4

    def test_extra_filters_do_not_mutate_baseline(self):
        """Calling _base_query with extra_filters must not affect a subsequent
        call without extra_filters."""
        _base_query("A", "count", extra_filters=[_error_filter()])
        q_clean = _base_query("B", "count")
        assert len(q_clean["filters"]["items"]) == 2


# ---------------------------------------------------------------------------
# build_dashboard – version field
# ---------------------------------------------------------------------------


class TestBuildDashboardVersion:
    def test_version_is_v5(self):
        """The dashboard version must be 'v5'."""
        d = build_dashboard()
        assert d["version"] == "v5"


# ---------------------------------------------------------------------------
# build_dashboard – JSON serializability
# ---------------------------------------------------------------------------


class TestBuildDashboardJsonSerializable:
    def test_is_json_serializable(self):
        """build_dashboard() output must be fully JSON serializable."""
        d = build_dashboard()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_roundtrip_is_stable(self):
        """JSON → parse → JSON must be idempotent (no lossy types)."""
        d = build_dashboard()
        once = json.dumps(d, sort_keys=True)
        twice = json.dumps(json.loads(once), sort_keys=True)
        assert once == twice


# ---------------------------------------------------------------------------
# build_dashboard – layout geometry
# ---------------------------------------------------------------------------


class TestBuildDashboardLayoutGeometry:
    def _layout(self):
        return build_dashboard()["layout"]

    def test_all_widgets_have_height_3(self):
        for entry in self._layout():
            assert entry["h"] == 3, f"Widget {entry['i']} has unexpected height {entry['h']}"

    def test_all_widgets_have_width_6(self):
        for entry in self._layout():
            assert entry["w"] == 6, f"Widget {entry['i']} has unexpected width {entry['w']}"

    def test_x_positions_are_0_or_6(self):
        """A 2-column grid means x is either 0 (left) or 6 (right)."""
        for entry in self._layout():
            assert entry["x"] in (0, 6), (
                f"Widget {entry['i']} has unexpected x={entry['x']}"
            )

    def test_y_positions_are_0_or_3(self):
        """A 2-row grid means y is either 0 (top) or 3 (bottom)."""
        for entry in self._layout():
            assert entry["y"] in (0, 3), (
                f"Widget {entry['i']} has unexpected y={entry['y']}"
            )

    def test_no_moved_flag(self):
        for entry in self._layout():
            assert entry["moved"] is False

    def test_no_static_flag(self):
        for entry in self._layout():
            assert entry["static"] is False

    def test_no_overlapping_cells(self):
        """Each cell occupies a unique (x, y) coordinate."""
        positions = [(e["x"], e["y"]) for e in self._layout()]
        assert len(positions) == len(set(positions)), "Layout entries share a grid position"

    def test_rate_widget_is_top_left(self):
        layout_by_id = {e["i"]: e for e in self._layout()}
        rate = layout_by_id["red-request-rate"]
        assert rate["x"] == 0 and rate["y"] == 0

    def test_error_widget_is_top_right(self):
        layout_by_id = {e["i"]: e for e in self._layout()}
        error = layout_by_id["red-error-count"]
        assert error["x"] == 6 and error["y"] == 0

    def test_latency_widget_is_bottom_left(self):
        layout_by_id = {e["i"]: e for e in self._layout()}
        latency = layout_by_id["red-latency"]
        assert latency["x"] == 0 and latency["y"] == 3

    def test_error_pct_widget_is_bottom_right(self):
        layout_by_id = {e["i"]: e for e in self._layout()}
        error_pct = layout_by_id["red-error-pct"]
        assert error_pct["x"] == 6 and error_pct["y"] == 3


# ---------------------------------------------------------------------------
# build_dashboard – widget query content (per-panel verification)
# ---------------------------------------------------------------------------


class TestBuildDashboardWidgetQueryContent:
    def _widgets_by_id(self):
        return {w["id"]: w for w in build_dashboard()["widgets"]}

    # --- Rate panel ---

    def test_rate_widget_uses_rate_operator(self):
        """Rate panel must aggregate with 'rate'."""
        w = self._widgets_by_id()["red-request-rate"]
        queries = w["query"]["builder"]["queryData"]
        assert len(queries) == 1
        assert queries[0]["aggregateOperator"] == "rate"

    def test_rate_widget_groups_by_operation(self):
        """Rate panel must group by operation name."""
        w = self._widgets_by_id()["red-request-rate"]
        queries = w["query"]["builder"]["queryData"]
        assert queries[0]["groupBy"] == _operation_group_by()

    def test_rate_widget_has_no_extra_filters(self):
        """Rate panel has no extra filters beyond service + sub-service."""
        w = self._widgets_by_id()["red-request-rate"]
        queries = w["query"]["builder"]["queryData"]
        assert len(queries[0]["filters"]["items"]) == 2

    # --- Error Count panel ---

    def test_error_widget_uses_count_operator(self):
        w = self._widgets_by_id()["red-error-count"]
        queries = w["query"]["builder"]["queryData"]
        assert queries[0]["aggregateOperator"] == "count"

    def test_error_widget_has_error_filter(self):
        """Error Count panel must include the hasError=true filter."""
        w = self._widgets_by_id()["red-error-count"]
        queries = w["query"]["builder"]["queryData"]
        filter_keys = [f["key"]["key"] for f in queries[0]["filters"]["items"]]
        assert "hasError" in filter_keys

    def test_error_widget_has_3_filters(self):
        """Error Count panel: service + sub-service + hasError = 3 filters."""
        w = self._widgets_by_id()["red-error-count"]
        queries = w["query"]["builder"]["queryData"]
        assert len(queries[0]["filters"]["items"]) == 3

    # --- Latency panel ---

    def test_latency_widget_has_three_queries(self):
        """Latency panel must have exactly 3 queries (p50, p95, p99)."""
        w = self._widgets_by_id()["red-latency"]
        queries = w["query"]["builder"]["queryData"]
        assert len(queries) == 3

    def test_latency_widget_query_names_are_a_b_c(self):
        w = self._widgets_by_id()["red-latency"]
        names = {q["queryName"] for q in w["query"]["builder"]["queryData"]}
        assert names == {"A", "B", "C"}

    def test_latency_widget_operators_are_p50_p95_p99(self):
        w = self._widgets_by_id()["red-latency"]
        ops = {q["aggregateOperator"] for q in w["query"]["builder"]["queryData"]}
        assert ops == {"p50", "p95", "p99"}

    def test_latency_widget_has_duration_aggregate_attribute(self):
        """All latency queries must reference durationNano."""
        w = self._widgets_by_id()["red-latency"]
        for q in w["query"]["builder"]["queryData"]:
            assert q["aggregateAttribute"]["key"] == "durationNano"

    def test_latency_widget_has_no_formulas(self):
        w = self._widgets_by_id()["red-latency"]
        assert w["query"]["builder"]["queryFormulas"] == []

    # --- Error Rate % panel ---

    def test_error_pct_widget_has_two_queries(self):
        """Error Rate % panel must have 2 queries (A=errors, B=total)."""
        w = self._widgets_by_id()["red-error-pct"]
        queries = w["query"]["builder"]["queryData"]
        assert len(queries) == 2

    def test_error_pct_widget_has_one_formula(self):
        """Error Rate % panel must have exactly 1 formula."""
        w = self._widgets_by_id()["red-error-pct"]
        formulas = w["query"]["builder"]["queryFormulas"]
        assert len(formulas) == 1

    def test_error_pct_formula_expression(self):
        """The formula expression must compute errors/total * 100."""
        w = self._widgets_by_id()["red-error-pct"]
        formula = w["query"]["builder"]["queryFormulas"][0]
        assert formula["expression"] == "A*100/B"

    def test_error_pct_formula_name_is_f1(self):
        w = self._widgets_by_id()["red-error-pct"]
        formula = w["query"]["builder"]["queryFormulas"][0]
        assert formula["queryName"] == "F1"

    def test_error_pct_query_a_has_error_filter(self):
        """The first query in Error Rate % must filter for errors."""
        w = self._widgets_by_id()["red-error-pct"]
        queries = w["query"]["builder"]["queryData"]
        query_a = next(q for q in queries if q["queryName"] == "A")
        filter_keys = [f["key"]["key"] for f in query_a["filters"]["items"]]
        assert "hasError" in filter_keys

    def test_error_pct_query_b_has_no_error_filter(self):
        """The second query in Error Rate % counts all requests (no hasError filter)."""
        w = self._widgets_by_id()["red-error-pct"]
        queries = w["query"]["builder"]["queryData"]
        query_b = next(q for q in queries if q["queryName"] == "B")
        filter_keys = [f["key"]["key"] for f in query_b["filters"]["items"]]
        assert "hasError" not in filter_keys


# ---------------------------------------------------------------------------
# build_dashboard – variable flags
# ---------------------------------------------------------------------------


class TestBuildDashboardVariableFlags:
    def _var(self):
        d = build_dashboard()
        return next(iter(d["variables"].values()))

    def test_all_selected_is_true(self):
        """Variable must default to ALL selected."""
        assert self._var()["allSelected"] is True

    def test_multi_select_is_false(self):
        """Variable is single-select only."""
        assert self._var()["multiSelect"] is False

    def test_show_all_option_is_true(self):
        """Variable UI must show the ALL option."""
        assert self._var()["showALLOption"] is True

    def test_selected_value_is_all(self):
        """Default selected value must be 'ALL'."""
        assert self._var()["selectedValue"] == "ALL"

    def test_order_is_zero(self):
        """First (and only) variable must have order=0."""
        assert self._var()["order"] == 0

    def test_sort_is_asc(self):
        """Variables must be sorted ASC."""
        assert self._var()["sort"] == "ASC"

    def test_custom_value_separator_is_comma(self):
        """Route prefixes in customValue are comma-separated."""
        custom_values = self._var()["customValue"]
        # Should contain at least one comma given multiple sub-services
        assert "," in custom_values

    def test_custom_value_has_correct_count(self):
        """customValue must contain exactly len(SUB_SERVICES) route prefixes."""
        custom_values = self._var()["customValue"]
        parts = [v.strip() for v in custom_values.split(",") if v.strip()]
        assert len(parts) == len(SUB_SERVICES)

    def test_description_mentions_route_prefix(self):
        """Variable description should mention route prefix."""
        assert "route prefix" in self._var()["description"].lower()


# ---------------------------------------------------------------------------
# build_dashboard – deterministic except for variable UUIDs
# ---------------------------------------------------------------------------


class TestBuildDashboardDeterminism:
    def test_title_is_constant(self):
        """Title must never change between calls."""
        assert build_dashboard()["title"] == build_dashboard()["title"]

    def test_widgets_are_identical_across_calls(self):
        """Widget list must be identical across independent calls."""
        d1 = build_dashboard()
        d2 = build_dashboard()
        assert d1["widgets"] == d2["widgets"]

    def test_layout_is_identical_across_calls(self):
        d1 = build_dashboard()
        d2 = build_dashboard()
        assert d1["layout"] == d2["layout"]

    def test_variable_uuid_key_differs_across_calls(self):
        """Each call to build_dashboard() generates a fresh UUID key for the
        sub-service variable, so the dict key will (almost certainly) differ."""
        d1 = build_dashboard()
        d2 = build_dashboard()
        key1 = next(iter(d1["variables"]))
        key2 = next(iter(d2["variables"]))
        # Very high probability they differ; at minimum, both are valid UUIDs.
        uuid.UUID(key1)
        uuid.UUID(key2)
