"""Unit tests for knowledge.layout — pure compute_layout function."""

from __future__ import annotations

import math

import pytest

from knowledge.layout import EdgeRef, LayoutParams, NodePos, compute_layout


def _node(nid: str, x: float | None = None, y: float | None = None) -> NodePos:
    return NodePos(id=nid, prior_x=x, prior_y=y)


def _all_finite(positions: dict[str, tuple[float, float]]) -> bool:
    return all(math.isfinite(x) and math.isfinite(y) for x, y in positions.values())


class TestComputeLayout:
    def test_compute_layout_is_deterministic_with_fixed_seed(self):
        """Same inputs + same seed produce byte-identical output dicts."""
        nodes = [_node("a"), _node("b"), _node("c"), _node("d")]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c"), EdgeRef("c", "d")]
        params = LayoutParams(seed=42)

        first = compute_layout(nodes, edges, params)
        second = compute_layout(nodes, edges, params)

        assert first == second

    def test_compute_layout_is_a_fixed_point_when_seeded_with_its_own_output(
        self,
    ):
        """Stability property the gardener relies on: layout is a fixed point.

        Running compute_layout twice on the same graph, with the second pass
        seeded from the first pass's output, produces nearly identical
        positions. This is what keeps the graph from teleporting between
        gardener cycles when nothing has changed.

        We can't assert "positions stay near arbitrary priors" because
        NetworkX spring_layout post-normalizes via _rescale_layout to fit
        [-scale, +scale] regardless of where priors sat — the fixed-point
        check is the right shape.
        """
        nodes_initial = [_node("a"), _node("b"), _node("c")]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c")]
        params = LayoutParams(iterations=50, seed=42)

        first = compute_layout(nodes_initial, edges, params)

        # Seed pass 2 from pass 1's output.
        nodes_seeded = [
            _node("a", *first["a"]),
            _node("b", *first["b"]),
            _node("c", *first["c"]),
        ]
        second = compute_layout(nodes_seeded, edges, params)

        # Threshold tuned for a small (3-node) graph: spring_layout's
        # _rescale_layout post-step plus 50 force iterations per call
        # introduce ~0.05–0.10 of per-node noise even when seeded with the
        # output of the previous call, because small graphs have more
        # degrees of freedom relative to constraints. The integration test
        # in service_test.py exercises the same property on a larger
        # fixture with a tighter 0.10 threshold; this unit-level check
        # catches catastrophic reshuffles only (drifts > 0.15 in
        # normalized [-1, 1] space).
        for nid in ("a", "b", "c"):
            x1, y1 = first[nid]
            x2, y2 = second[nid]
            assert abs(x1 - x2) < 0.15, f"{nid} x drifted between passes: {x1} -> {x2}"
            assert abs(y1 - y2) < 0.15, f"{nid} y drifted between passes: {y1} -> {y2}"

    def test_compute_layout_places_new_node_finitely(self):
        """A newcomer joining a prior-positioned graph gets a finite (x, y)."""
        nodes = [
            _node("a", 0.1, 0.2),
            _node("b", -0.3, 0.4),
            _node("new"),
        ]
        edges = [EdgeRef("a", "b"), EdgeRef("a", "new")]
        params = LayoutParams(seed=42)

        positions = compute_layout(nodes, edges, params)

        assert "new" in positions
        x, y = positions["new"]
        assert math.isfinite(x) and math.isfinite(y)

    def test_compute_layout_handles_empty_graph(self):
        assert compute_layout([], [], LayoutParams()) == {}

    def test_compute_layout_handles_single_node(self):
        positions = compute_layout([_node("solo")], [], LayoutParams())
        assert set(positions.keys()) == {"solo"}
        x, y = positions["solo"]
        assert math.isfinite(x) and math.isfinite(y)

    def test_compute_layout_handles_disconnected_components(self):
        """Two cliques with no shared nodes — all positioned, all in scale box."""
        nodes = [_node(n) for n in ("a", "b", "c", "x", "y", "z")]
        edges = [
            EdgeRef("a", "b"),
            EdgeRef("b", "c"),
            EdgeRef("a", "c"),
            EdgeRef("x", "y"),
            EdgeRef("y", "z"),
            EdgeRef("x", "z"),
        ]
        params = LayoutParams(scale=1.0, seed=42)

        positions = compute_layout(nodes, edges, params)

        assert set(positions.keys()) == {n.id for n in nodes}
        assert _all_finite(positions)
        for nid, (x, y) in positions.items():
            assert -params.scale <= x <= params.scale, f"{nid} x={x} outside scale"
            assert -params.scale <= y <= params.scale, f"{nid} y={y} outside scale"

    def test_compute_layout_filters_nan_inputs_via_module_contract(self):
        """A NaN prior must be ignored at the seed step, not propagated."""
        nodes = [
            _node("a", 0.1, 0.2),
            _node("b", float("nan"), float("nan")),
            _node("c", 0.3, -0.2),
        ]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c")]
        params = LayoutParams(seed=42)

        positions = compute_layout(nodes, edges, params)

        assert "b" in positions
        x, y = positions["b"]
        assert math.isfinite(x) and math.isfinite(y)

    def test_compute_layout_param_sensitivity(self):
        """Different link_distance values produce different layouts."""
        nodes = [_node("a"), _node("b"), _node("c"), _node("d")]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c"), EdgeRef("c", "d")]

        loose = compute_layout(nodes, edges, LayoutParams(link_distance=0.05, seed=42))
        tight = compute_layout(nodes, edges, LayoutParams(link_distance=2.0, seed=42))

        assert loose != tight


class TestLayoutParamsValidation:
    def test_validates_positive_iterations(self):
        with pytest.raises(ValueError, match="iterations must be positive"):
            LayoutParams(iterations=0)

    def test_validates_positive_link_distance(self):
        with pytest.raises(ValueError, match="link_distance must be positive"):
            LayoutParams(link_distance=-1.0)

    def test_validates_finite_link_distance(self):
        with pytest.raises(
            ValueError, match="link_distance must be positive and finite"
        ):
            LayoutParams(link_distance=float("inf"))


class TestLayoutParamsFromEnv:
    def test_uses_defaults_when_env_empty(self):
        params = LayoutParams.from_env({})
        assert params.link_distance == 0.05
        assert params.iterations == 50
        assert params.seed == 42
        assert params.scale == 1.0

    def test_reads_overrides_from_env(self):
        params = LayoutParams.from_env(
            {
                "KNOWLEDGE_LAYOUT_LINK_DISTANCE": "0.1",
                "KNOWLEDGE_LAYOUT_ITERATIONS": "100",
                "KNOWLEDGE_LAYOUT_SEED": "7",
                "KNOWLEDGE_LAYOUT_SCALE": "2.0",
            }
        )
        assert params.link_distance == 0.1
        assert params.iterations == 100
        assert params.seed == 7
        assert params.scale == 2.0

    def test_validates_invalid_env_values(self):
        with pytest.raises(ValueError):
            LayoutParams.from_env({"KNOWLEDGE_LAYOUT_ITERATIONS": "0"})
        with pytest.raises(ValueError):
            LayoutParams.from_env({"KNOWLEDGE_LAYOUT_LINK_DISTANCE": "-0.1"})
