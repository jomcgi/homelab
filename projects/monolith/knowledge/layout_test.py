"""Unit tests for knowledge.layout — pure compute_layout function.

The layout splits the graph into a connected core (laid out by
``nx.forceatlas2_layout``) and an orphan ring (hash-determined angles
on the canvas perimeter). Tests cover both branches plus the param
plumbing and validation paths.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from knowledge.layout import EdgeRef, LayoutParams, NodePos, compute_layout


def _node(nid: str, x: float | None = None, y: float | None = None) -> NodePos:
    return NodePos(id=nid, prior_x=x, prior_y=y)


def _all_finite(positions: dict[str, tuple[float, float]]) -> bool:
    return all(math.isfinite(x) and math.isfinite(y) for x, y in positions.values())


def _expected_orphan_angle(nid: str) -> float:
    h = int(hashlib.md5(nid.encode()).hexdigest()[:8], 16)
    return 2 * math.pi * (h / 0xFFFFFFFF)


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

        Running compute_layout twice on the same graph, with the second
        pass seeded from the first pass's output, produces nearly
        identical positions. This is what keeps the graph from
        teleporting between gardener cycles when nothing has changed.

        FA2 introduces some per-iteration repulsion noise even when
        seeded with the previous output, and the post-scale step
        re-fits the bounding box to ``core_fraction`` regardless of
        the input scale, so we use a generous threshold appropriate
        for the small (3-node) graph.
        """
        nodes_initial = [_node("a"), _node("b"), _node("c")]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c")]
        params = LayoutParams(max_iter=100, seed=42)

        first = compute_layout(nodes_initial, edges, params)

        # Seed pass 2 from pass 1's output.
        nodes_seeded = [
            _node("a", *first["a"]),
            _node("b", *first["b"]),
            _node("c", *first["c"]),
        ]
        second = compute_layout(nodes_seeded, edges, params)

        # FA2 + post-scale: small (3-node) graphs reposition by roughly
        # the connected-core radius (~core_fraction = 0.99), so the
        # check here only catches catastrophic reshuffles. A tighter
        # threshold lives in the larger-fixture integration test.
        for nid in ("a", "b", "c"):
            x1, y1 = first[nid]
            x2, y2 = second[nid]
            assert abs(x1 - x2) < 0.5, f"{nid} x drifted between passes: {x1} -> {x2}"
            assert abs(y1 - y2) < 0.5, f"{nid} y drifted between passes: {y1} -> {y2}"

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
        """Single orphan node: ring placement, no FA2."""
        positions = compute_layout([_node("solo")], [], LayoutParams())
        assert set(positions.keys()) == {"solo"}
        x, y = positions["solo"]
        assert math.isfinite(x) and math.isfinite(y)

    def test_compute_layout_handles_disconnected_components(self):
        """Two cliques with no shared nodes — all positioned, all in core."""
        nodes = [_node(n) for n in ("a", "b", "c", "x", "y", "z")]
        edges = [
            EdgeRef("a", "b"),
            EdgeRef("b", "c"),
            EdgeRef("a", "c"),
            EdgeRef("x", "y"),
            EdgeRef("y", "z"),
            EdgeRef("x", "z"),
        ]
        params = LayoutParams(seed=42)

        positions = compute_layout(nodes, edges, params)

        assert set(positions.keys()) == {n.id for n in nodes}
        assert _all_finite(positions)
        # All connected → all inside the core radius.
        eps = 1e-9
        for nid, (x, y) in positions.items():
            assert max(abs(x), abs(y)) <= params.core_fraction + eps, (
                f"{nid}=({x},{y}) outside core_fraction={params.core_fraction}"
            )

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
        """Different gravity values produce different layouts."""
        nodes = [_node("a"), _node("b"), _node("c"), _node("d")]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c"), EdgeRef("c", "d")]

        loose = compute_layout(nodes, edges, LayoutParams(gravity=0.1, seed=42))
        tight = compute_layout(nodes, edges, LayoutParams(gravity=10.0, seed=42))

        assert loose != tight

    def test_compute_layout_uses_full_canvas_radius_when_orphans_present(self):
        """Mixed graph: orphans live on the ring, connected fits the core."""
        nodes = [
            _node("a"),
            _node("b"),
            _node("c"),
            _node("orph1"),
            _node("orph2"),
        ]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c"), EdgeRef("a", "c")]
        params = LayoutParams(seed=42)

        positions = compute_layout(nodes, edges, params)

        eps = 1e-9
        for nid in ("orph1", "orph2"):
            x, y = positions[nid]
            r = math.hypot(x, y)
            assert abs(r - params.ring_radius_fraction) < 1e-9, (
                f"{nid} ring radius {r} != {params.ring_radius_fraction}"
            )

        # The connected nodes' bounding box must reach exactly
        # core_fraction (post-scale fits the core to that radius).
        connected_max_extent = max(
            max(abs(positions[nid][0]), abs(positions[nid][1]))
            for nid in ("a", "b", "c")
        )
        assert abs(connected_max_extent - params.core_fraction) < 1e-9, (
            f"connected max extent {connected_max_extent} != "
            f"core_fraction {params.core_fraction}"
        )

    def test_compute_layout_orphan_positions_are_hash_stable(self):
        """An orphan's angle depends only on its id, not the rest of the graph."""
        params = LayoutParams(seed=42)

        alone = compute_layout([_node("X")], [], params)
        with_others = compute_layout(
            [_node(nid) for nid in ("X", "A", "B", "C", "D", "E")], [], params
        )

        assert alone["X"] == with_others["X"]

        expected_angle = _expected_orphan_angle("X")
        x, y = alone["X"]
        assert math.isclose(
            math.atan2(y, x) % (2 * math.pi), expected_angle, abs_tol=1e-9
        )

    def test_compute_layout_orphan_ring_positions_are_deterministic(self):
        """Same orphan-only graph called twice yields identical positions."""
        nodes = [_node(nid) for nid in ("orph1", "orph2", "orph3")]
        params = LayoutParams(seed=42)

        first = compute_layout(nodes, [], params)
        second = compute_layout(nodes, [], params)

        assert first == second

    def test_compute_layout_handles_no_edges_all_orphans(self):
        """Every node is an orphan: ring is populated, no FA2 invocation."""
        nodes = [_node(nid) for nid in ("a", "b", "c")]
        params = LayoutParams(seed=42)

        positions = compute_layout(nodes, [], params)

        assert set(positions.keys()) == {"a", "b", "c"}
        for nid, (x, y) in positions.items():
            r = math.hypot(x, y)
            assert abs(r - params.ring_radius_fraction) < 1e-9, (
                f"{nid} ring radius {r} != {params.ring_radius_fraction}"
            )

    def test_compute_layout_handles_no_orphans_all_connected(self):
        """Every node is connected: only the FA2 + core-scale path runs."""
        nodes = [_node(nid) for nid in ("a", "b", "c")]
        edges = [EdgeRef("a", "b"), EdgeRef("b", "c"), EdgeRef("a", "c")]
        params = LayoutParams(seed=42)

        positions = compute_layout(nodes, edges, params)

        assert set(positions.keys()) == {"a", "b", "c"}
        assert _all_finite(positions)
        eps = 1e-9
        for nid, (x, y) in positions.items():
            assert max(abs(x), abs(y)) <= params.core_fraction + eps

    def test_compute_layout_orphan_x_node_alone_is_pure_ring(self):
        """A node with no edges goes straight to the ring (regression)."""
        params = LayoutParams(seed=42)
        positions = compute_layout([_node("solo")], [], params)
        x, y = positions["solo"]
        r = math.hypot(x, y)
        assert abs(r - params.ring_radius_fraction) < 1e-9


class TestLayoutParamsValidation:
    def test_validates_positive_max_iter(self):
        with pytest.raises(ValueError, match="max_iter must be positive"):
            LayoutParams(max_iter=0)

    def test_validates_positive_scaling_ratio(self):
        with pytest.raises(ValueError, match="scaling_ratio must be positive"):
            LayoutParams(scaling_ratio=-1.0)

    def test_validates_finite_scaling_ratio(self):
        with pytest.raises(
            ValueError, match="scaling_ratio must be positive and finite"
        ):
            LayoutParams(scaling_ratio=float("inf"))

    def test_allows_zero_gravity(self):
        # Gravity is allowed to be zero (no center pull) — should not raise.
        params = LayoutParams(gravity=0.0)
        assert params.gravity == 0.0

    def test_validates_non_negative_gravity(self):
        with pytest.raises(ValueError, match="gravity must be non-negative and finite"):
            LayoutParams(gravity=-0.1)

    def test_validates_finite_gravity(self):
        with pytest.raises(ValueError, match="gravity must be non-negative and finite"):
            LayoutParams(gravity=float("nan"))

    def test_validates_core_fraction_upper_bound(self):
        with pytest.raises(ValueError, match=r"core_fraction must be in \(0, 1\]"):
            LayoutParams(core_fraction=1.5)

    def test_validates_core_fraction_lower_bound(self):
        with pytest.raises(ValueError, match=r"core_fraction must be in \(0, 1\]"):
            LayoutParams(core_fraction=0.0)

    def test_validates_ring_radius_fraction_upper_bound(self):
        with pytest.raises(
            ValueError, match=r"ring_radius_fraction must be in \(0, 1\]"
        ):
            LayoutParams(ring_radius_fraction=1.5)

    def test_validates_ring_radius_fraction_lower_bound(self):
        with pytest.raises(
            ValueError, match=r"ring_radius_fraction must be in \(0, 1\]"
        ):
            LayoutParams(ring_radius_fraction=0.0)


class TestLayoutParamsFromEnv:
    def test_uses_defaults_when_env_empty(self):
        params = LayoutParams.from_env({})
        assert params.scaling_ratio == 2.0
        assert params.gravity == 0.5
        assert params.max_iter == 100
        assert params.linlog is True
        assert params.core_fraction == 0.99
        assert params.ring_radius_fraction == 0.995
        assert params.seed == 42

    def test_reads_overrides_from_env(self):
        params = LayoutParams.from_env(
            {
                "KNOWLEDGE_LAYOUT_SCALING_RATIO": "3.5",
                "KNOWLEDGE_LAYOUT_GRAVITY": "1.0",
                "KNOWLEDGE_LAYOUT_MAX_ITER": "200",
                "KNOWLEDGE_LAYOUT_LINLOG": "0",
                "KNOWLEDGE_LAYOUT_CORE_FRACTION": "0.8",
                "KNOWLEDGE_LAYOUT_RING_RADIUS_FRACTION": "0.9",
                "KNOWLEDGE_LAYOUT_SEED": "7",
            }
        )
        assert params.scaling_ratio == 3.5
        assert params.gravity == 1.0
        assert params.max_iter == 200
        assert params.linlog is False
        assert params.core_fraction == 0.8
        assert params.ring_radius_fraction == 0.9
        assert params.seed == 7

    @pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "True", "yes", "YES"])
    def test_parses_truthy_linlog_values(self, truthy: str):
        params = LayoutParams.from_env({"KNOWLEDGE_LAYOUT_LINLOG": truthy})
        assert params.linlog is True

    @pytest.mark.parametrize("falsy", ["0", "false", "FALSE", "no", "", "off", "nope"])
    def test_parses_falsy_linlog_values(self, falsy: str):
        params = LayoutParams.from_env({"KNOWLEDGE_LAYOUT_LINLOG": falsy})
        assert params.linlog is False

    def test_validates_invalid_env_values(self):
        with pytest.raises(ValueError):
            LayoutParams.from_env({"KNOWLEDGE_LAYOUT_MAX_ITER": "0"})
        with pytest.raises(ValueError):
            LayoutParams.from_env({"KNOWLEDGE_LAYOUT_SCALING_RATIO": "-0.1"})
        with pytest.raises(ValueError):
            LayoutParams.from_env({"KNOWLEDGE_LAYOUT_CORE_FRACTION": "2.0"})
        with pytest.raises(ValueError):
            LayoutParams.from_env({"KNOWLEDGE_LAYOUT_RING_RADIUS_FRACTION": "0"})
