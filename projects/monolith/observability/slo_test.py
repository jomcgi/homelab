import pytest

from observability.slo import (
    compute_status,
    compute_budget,
    compute_brief,
    aggregate_group,
)


class TestComputeStatus:
    def test_healthy_when_above_target(self):
        assert compute_status(current=99.5, target=99.0) == "healthy"

    def test_warning_when_within_half_percent(self):
        assert compute_status(current=98.8, target=99.0) == "warning"

    def test_degraded_when_below_threshold(self):
        assert compute_status(current=98.0, target=99.0) == "degraded"

    def test_healthy_when_exactly_at_target(self):
        assert compute_status(current=99.0, target=99.0) == "healthy"

    def test_no_slo_returns_healthy(self):
        assert compute_status(current=None, target=None) == "healthy"


class TestComputeBudget:
    def test_full_budget_remaining(self):
        budget = compute_budget(
            current=100.0, target=99.0, window_days=30, elapsed_days=15
        )
        assert budget["consumed"] == 0
        assert budget["remaining"] == "432.0 min"
        assert budget["window"] == "30d"

    def test_budget_partially_consumed(self):
        budget = compute_budget(
            current=98.0, target=99.0, window_days=30, elapsed_days=15
        )
        assert budget["consumed"] > 0
        assert float(budget["remaining"].replace(" min", "")) < 432.0

    def test_budget_exhausted(self):
        budget = compute_budget(
            current=95.0, target=99.0, window_days=30, elapsed_days=30
        )
        assert budget["remaining"] == "0 min"


class TestComputeBrief:
    def test_brief_with_slo_and_metric(self):
        brief = compute_brief(availability=99.97, metrics={"rps": "12.5"})
        assert "99.97%" in brief
        assert "12.5 rps" in brief

    def test_brief_slo_only(self):
        brief = compute_brief(availability=100.0, metrics={})
        assert "100%" in brief

    def test_brief_no_slo(self):
        brief = compute_brief(availability=None, metrics={"clients": "a, b"})
        assert "a, b" in brief


class TestAggregateGroup:
    def test_min_availability(self):
        children = [
            {"slo": {"current": 99.5}},
            {"slo": {"current": 100.0}},
            {"slo": {"current": 99.8}},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        assert result["slo"]["current"] == 99.5

    def test_worst_status(self):
        children = [
            {"status": "healthy"},
            {"status": "degraded"},
            {"status": "healthy"},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        assert result["status"] == "degraded"

    def test_sum_rps(self):
        children = [
            {"slo": {"current": 100.0}, "metrics": [{"k": "rps", "v": "5.0"}]},
            {"slo": {"current": 100.0}, "metrics": [{"k": "rps", "v": "3.2"}]},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        rps = next((m for m in result["metrics"] if m["k"] == "rps"), None)
        assert rps is not None
        assert float(rps["v"]) == pytest.approx(8.2, abs=0.1)

    def test_max_latency(self):
        children = [
            {"slo": {"current": 100.0}, "metrics": [{"k": "p99", "v": "42ms"}]},
            {"slo": {"current": 100.0}, "metrics": [{"k": "p99", "v": "180ms"}]},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        latency = next((m for m in result["metrics"] if m["k"] == "latency"), None)
        assert latency is not None
        assert latency["v"] == "180ms"
