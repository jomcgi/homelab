"""Server-side force-directed layout for the knowledge graph.

This module is intentionally pure: every public function takes inputs and
returns outputs with no I/O. The reconcile handler and the local preview
script both call ``compute_layout`` with identical ``LayoutParams`` so dev
and prod produce the same result.

Algorithm: structural split into a connected core + an orphan ring.
================================================================

The vault graph is bimodal: a single dense connected component of
linked notes, and a long tail of orphan notes (no inbound or outbound
links). A single force-directed pass over the union produces a tight
central blob that pushes orphans to the canvas edges via repulsion
without conveying useful structural information — and the post-rescale
step then squeezes the connected core into a tiny center smear.

Instead we partition by edge membership:

* **Connected nodes** (any node touched by an edge) are laid out with
  ``nx.forceatlas2_layout``. FA2's logarithmic-attraction option
  (``linlog=True``) spreads dense central regions while keeping
  hub/leaf relationships visible. We post-scale the FA2 result so its
  bounding box fills ``core_fraction`` of the unit canvas.
* **Orphan nodes** are placed on a perimeter ring at radius
  ``ring_radius_fraction``. Each orphan's angle is derived from an MD5
  hash of its note id, giving stable per-id positions that don't drift
  when other orphans are added or removed.

This split keeps the two visual concerns separate (organic spread vs.
deterministic placement) and makes the layout cycle-stable: an
unchanged graph produces an unchanged layout.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

import networkx as nx

NoteId = str


@dataclass(frozen=True, slots=True)
class NodePos:
    id: NoteId
    prior_x: float | None
    prior_y: float | None


@dataclass(frozen=True, slots=True)
class EdgeRef:
    source: NoteId
    target: NoteId


def _is_truthy(value: str) -> bool:
    """Parse a string env value as a boolean.

    Truthy: ``"1"``, ``"true"``, ``"yes"`` (case-insensitive).
    Everything else (including empty string, ``"0"``, ``"false"``,
    ``"no"``) is falsy.
    """
    return value.strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True, slots=True)
class LayoutParams:
    scaling_ratio: float = 2.0
    gravity: float = 0.5
    max_iter: int = 100
    linlog: bool = True
    core_fraction: float = 0.99
    ring_radius_fraction: float = 0.995
    seed: int = 42

    def __post_init__(self) -> None:
        if not (self.scaling_ratio > 0 and math.isfinite(self.scaling_ratio)):
            raise ValueError(
                f"scaling_ratio must be positive and finite, got {self.scaling_ratio}"
            )
        # Gravity may legitimately be 0 (no center pull). Disallow negatives
        # and non-finite values.
        if not (self.gravity >= 0 and math.isfinite(self.gravity)):
            raise ValueError(
                f"gravity must be non-negative and finite, got {self.gravity}"
            )
        if self.max_iter <= 0:
            raise ValueError(f"max_iter must be positive, got {self.max_iter}")
        if not (0 < self.core_fraction <= 1):
            raise ValueError(
                f"core_fraction must be in (0, 1], got {self.core_fraction}"
            )
        if not (0 < self.ring_radius_fraction <= 1):
            raise ValueError(
                f"ring_radius_fraction must be in (0, 1], got {self.ring_radius_fraction}"
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "LayoutParams":
        """Read layout knobs from environment variables, falling back to defaults.

        Invalid values raise ValueError via __post_init__ — the pod fails to
        start, ArgoCD surfaces CrashLoopBackOff, no silent fallback.
        """
        env = environ if environ is not None else os.environ
        return cls(
            scaling_ratio=float(env.get("KNOWLEDGE_LAYOUT_SCALING_RATIO", "2.0")),
            gravity=float(env.get("KNOWLEDGE_LAYOUT_GRAVITY", "0.5")),
            max_iter=int(env.get("KNOWLEDGE_LAYOUT_MAX_ITER", "100")),
            linlog=_is_truthy(env.get("KNOWLEDGE_LAYOUT_LINLOG", "true")),
            core_fraction=float(env.get("KNOWLEDGE_LAYOUT_CORE_FRACTION", "0.99")),
            ring_radius_fraction=float(
                env.get("KNOWLEDGE_LAYOUT_RING_RADIUS_FRACTION", "0.995")
            ),
            seed=int(env.get("KNOWLEDGE_LAYOUT_SEED", "42")),
        )


def _orphan_position(note_id: NoteId, ring_radius: float) -> tuple[float, float]:
    """Place an orphan on the canvas-edge ring at a hash-determined angle.

    MD5 of the note id, first 8 hex chars (32 bits), divided by
    ``0xFFFFFFFF`` gives a uniform value in ``[0, 1)``. Multiply by
    ``2*pi`` for the angle. Stable per id, independent of which other
    orphans exist in the graph.
    """
    digest = hashlib.md5(note_id.encode()).hexdigest()
    h = int(digest[:8], 16)
    angle = 2 * math.pi * (h / 0xFFFFFFFF)
    return (ring_radius * math.cos(angle), ring_radius * math.sin(angle))


def compute_layout(
    nodes: list[NodePos],
    edges: list[EdgeRef],
    params: LayoutParams,
) -> dict[NoteId, tuple[float, float]]:
    """Compute (x, y) positions via FA2-on-connected + hash-ring-on-orphans.

    See the module docstring for the algorithm. In short:

    1. Partition ``nodes`` into ``connected`` (touched by an edge) and
       ``orphans`` (not touched by any edge).
    2. Run ``nx.forceatlas2_layout`` on the connected subgraph, seeded
       with each node's ``prior_x``/``prior_y`` if both are finite.
       Post-scale so the bounding box fills ``core_fraction`` of the
       unit canvas.
    3. Place each orphan at a hash-determined angle on the perimeter
       ring at radius ``ring_radius_fraction``.

    Non-finite outputs (NaN/Inf) are filtered out. Caller treats
    missing positions as "use random-center fallback at render time."
    """
    if not nodes:
        return {}

    edge_endpoints: set[NoteId] = set()
    for e in edges:
        edge_endpoints.add(e.source)
        edge_endpoints.add(e.target)

    connected = [n for n in nodes if n.id in edge_endpoints]
    orphans = [n for n in nodes if n.id not in edge_endpoints]

    out: dict[NoteId, tuple[float, float]] = {}

    if connected:
        g = nx.Graph()
        connected_ids = {n.id for n in connected}
        for n in connected:
            g.add_node(n.id)
        for e in edges:
            if e.source in connected_ids and e.target in connected_ids:
                g.add_edge(e.source, e.target)

        prior: dict[NoteId, tuple[float, float]] = {
            n.id: (n.prior_x, n.prior_y)
            for n in connected
            if n.prior_x is not None
            and n.prior_y is not None
            and math.isfinite(n.prior_x)
            and math.isfinite(n.prior_y)
        }

        raw = nx.forceatlas2_layout(
            g,
            pos=prior or None,
            max_iter=params.max_iter,
            scaling_ratio=params.scaling_ratio,
            gravity=params.gravity,
            linlog=params.linlog,
            seed=params.seed,
        )

        # Find FA2's bounding box across finite outputs and post-scale to
        # fill `core_fraction` of the unit canvas. Skip the rescale entirely
        # when every coordinate is zero (single connected node, etc.) to
        # avoid a divide-by-zero.
        finite = {
            nid: (float(x), float(y))
            for nid, (x, y) in raw.items()
            if math.isfinite(float(x)) and math.isfinite(float(y))
        }
        if finite:
            max_extent = max(
                (max(abs(x), abs(y)) for x, y in finite.values()),
                default=0.0,
            )
            if max_extent > 0:
                scale_factor = params.core_fraction / max_extent
            else:
                scale_factor = 1.0
            for nid, (x, y) in finite.items():
                out[nid] = (x * scale_factor, y * scale_factor)

    for n in orphans:
        x, y = _orphan_position(n.id, params.ring_radius_fraction)
        if math.isfinite(x) and math.isfinite(y):
            out[n.id] = (x, y)

    return out
