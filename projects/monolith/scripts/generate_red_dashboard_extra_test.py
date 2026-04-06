"""Extra unit tests for generate-red-dashboard.py helper functions.

Covers functions not tested in generate_red_dashboard_test.py:
- _query_wrapper(): wrapper structure, formulas, promql/clickhouse boilerplate
- _widget(): all fields, optional y_unit, stacked flag, panel_type
- _operation_group_by(): key definition and field values
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

_query_wrapper = _mod._query_wrapper
_widget = _mod._widget
_operation_group_by = _mod._operation_group_by
_base_query = _mod._base_query


# ---------------------------------------------------------------------------
# _query_wrapper
# ---------------------------------------------------------------------------


class TestQueryWrapper:
    def test_query_type_is_builder(self):
        """_query_wrapper always produces queryType='builder'."""
        result = _query_wrapper([])
        assert result["queryType"] == "builder"

    def test_builder_key_is_present(self):
        """_query_wrapper contains a 'builder' key."""
        result = _query_wrapper([])
        assert "builder" in result

    def test_query_data_stored_in_builder(self):
        """_query_wrapper places queryData inside the builder dict."""
        q = _base_query("A", "count")
        result = _query_wrapper([q])
        assert result["builder"]["queryData"] == [q]

    def test_empty_formulas_by_default(self):
        """_query_wrapper defaults queryFormulas to an empty list."""
        result = _query_wrapper([])
        assert result["builder"]["queryFormulas"] == []

    def test_formulas_included_when_provided(self):
        """_query_wrapper stores provided formulas in queryFormulas."""
        formula = {"queryName": "F1", "expression": "A*100/B", "disabled": False}
        result = _query_wrapper([], query_formulas=[formula])
        assert result["builder"]["queryFormulas"] == [formula]

    def test_multiple_formulas(self):
        """_query_wrapper stores multiple formulas."""
        formulas = [
            {"queryName": "F1", "expression": "A*100/B"},
            {"queryName": "F2", "expression": "A+B"},
        ]
        result = _query_wrapper([], query_formulas=formulas)
        assert len(result["builder"]["queryFormulas"]) == 2

    def test_promql_key_is_present(self):
        """_query_wrapper includes a 'promql' boilerplate key."""
        result = _query_wrapper([])
        assert "promql" in result

    def test_clickhouse_sql_key_is_present(self):
        """_query_wrapper includes a 'clickhouse_sql' boilerplate key."""
        result = _query_wrapper([])
        assert "clickhouse_sql" in result

    def test_multiple_query_data_entries(self):
        """_query_wrapper accepts and stores multiple queryData entries."""
        q1 = _base_query("A", "count")
        q2 = _base_query("B", "rate")
        q3 = _base_query("C", "p95")
        result = _query_wrapper([q1, q2, q3])
        assert len(result["builder"]["queryData"]) == 3

    def test_empty_query_data(self):
        """_query_wrapper accepts an empty queryData list."""
        result = _query_wrapper([])
        assert result["builder"]["queryData"] == []

    def test_none_formulas_defaults_to_empty_list(self):
        """_query_wrapper with query_formulas=None produces empty queryFormulas."""
        result = _query_wrapper([], query_formulas=None)
        assert result["builder"]["queryFormulas"] == []


# ---------------------------------------------------------------------------
# _widget
# ---------------------------------------------------------------------------


class TestWidget:
    def test_id_field_is_set(self):
        """_widget stores the widget id."""
        w = _widget("my-widget-id", "Title", "Desc", {})
        assert w["id"] == "my-widget-id"

    def test_title_field_is_set(self):
        """_widget stores the title."""
        w = _widget("id1", "My Panel Title", "Desc", {})
        assert w["title"] == "My Panel Title"

    def test_description_field_is_set(self):
        """_widget stores the description."""
        w = _widget("id1", "T", "My description text", {})
        assert w["description"] == "My description text"

    def test_default_panel_type_is_graph(self):
        """_widget defaults panelTypes to 'graph'."""
        w = _widget("id1", "T", "D", {})
        assert w["panelTypes"] == "graph"

    def test_custom_panel_type(self):
        """_widget accepts a custom panel_type value."""
        w = _widget("id1", "T", "D", {}, panel_type="table")
        assert w["panelTypes"] == "table"

    def test_stacked_defaults_to_false(self):
        """_widget sets isStacked=False by default."""
        w = _widget("id1", "T", "D", {})
        assert w["isStacked"] is False

    def test_stacked_true_sets_is_stacked_true(self):
        """_widget with stacked=True sets isStacked=True."""
        w = _widget("id1", "T", "D", {}, stacked=True)
        assert w["isStacked"] is True

    def test_stacked_false_explicit_sets_is_stacked_false(self):
        """_widget with stacked=False explicitly sets isStacked=False."""
        w = _widget("id1", "T", "D", {}, stacked=False)
        assert w["isStacked"] is False

    def test_y_axis_unit_absent_by_default(self):
        """_widget does not include yAxisUnit when y_unit is not given."""
        w = _widget("id1", "T", "D", {})
        assert "yAxisUnit" not in w

    def test_y_axis_unit_set_when_provided(self):
        """_widget sets yAxisUnit to the given y_unit string."""
        w = _widget("id1", "T", "D", {}, y_unit="ns")
        assert w["yAxisUnit"] == "ns"

    def test_y_axis_unit_different_values(self):
        """_widget supports arbitrary y_unit strings."""
        w = _widget("id1", "T", "D", {}, y_unit="ms")
        assert w["yAxisUnit"] == "ms"

    def test_query_is_stored(self):
        """_widget stores the query object under the 'query' key."""
        q = _query_wrapper([])
        w = _widget("id1", "T", "D", q)
        assert w["query"] is q

    def test_fill_spans_is_false(self):
        """_widget sets fillSpans to False."""
        w = _widget("id1", "T", "D", {})
        assert w["fillSpans"] is False

    def test_null_zero_values_is_zero(self):
        """_widget sets nullZeroValues to 'zero'."""
        w = _widget("id1", "T", "D", {})
        assert w["nullZeroValues"] == "zero"

    def test_opacity_is_one(self):
        """_widget sets opacity to '1'."""
        w = _widget("id1", "T", "D", {})
        assert w["opacity"] == "1"

    def test_thresholds_is_empty_list(self):
        """_widget initializes thresholds as an empty list."""
        w = _widget("id1", "T", "D", {})
        assert w["thresholds"] == []

    def test_selected_log_fields_is_empty(self):
        """_widget initializes selectedLogFields as an empty list."""
        w = _widget("id1", "T", "D", {})
        assert w["selectedLogFields"] == []

    def test_selected_traces_fields_is_empty(self):
        """_widget initializes selectedTracesFields as an empty list."""
        w = _widget("id1", "T", "D", {})
        assert w["selectedTracesFields"] == []


# ---------------------------------------------------------------------------
# _operation_group_by
# ---------------------------------------------------------------------------


class TestOperationGroupBy:
    def test_returns_a_list(self):
        """_operation_group_by returns a list."""
        result = _operation_group_by()
        assert isinstance(result, list)

    def test_has_exactly_one_entry(self):
        """_operation_group_by returns exactly one group-by entry."""
        result = _operation_group_by()
        assert len(result) == 1

    def test_key_is_name(self):
        """_operation_group_by groups by 'name' (the operation/span name)."""
        result = _operation_group_by()
        assert result[0]["key"] == "name"

    def test_data_type_is_string(self):
        """_operation_group_by has dataType='string'."""
        result = _operation_group_by()
        assert result[0]["dataType"] == "string"

    def test_type_is_tag(self):
        """_operation_group_by has type='tag'."""
        result = _operation_group_by()
        assert result[0]["type"] == "tag"

    def test_is_column_is_true(self):
        """_operation_group_by has isColumn=True (it is a table column)."""
        result = _operation_group_by()
        assert result[0]["isColumn"] is True

    def test_is_json_is_false(self):
        """_operation_group_by has isJSON=False."""
        result = _operation_group_by()
        assert result[0]["isJSON"] is False

    def test_result_is_compatible_with_base_query_group_by(self):
        """_operation_group_by output can be passed directly to _base_query."""
        gb = _operation_group_by()
        q = _base_query("A", "rate", group_by=gb)
        assert q["groupBy"] == gb
