"""Server-side force-directed layout for the knowledge graph.

This module is intentionally pure: every public function takes inputs and
returns outputs with no I/O. The reconcile handler and the local preview
script both call ``compute_layout`` with identical ``LayoutParams`` so dev
and prod produce the same result.
"""

from __future__ import annotations

import math
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


@dataclass(frozen=True, slots=True)
class LayoutParams:
    link_distance: float = 0.05
    iterations: int = 50
    seed: int = 42
    scale: float = 1.0

    def __post_init__(self) -> None:
        if not (self.link_distance > 0 and math.isfinite(self.link_distance)):
            raise ValueError(
                f"link_distance must be positive and finite, got {self.link_distance}"
            )
        if self.iterations <= 0:
            raise ValueError(f"iterations must be positive, got {self.iterations}")
        if not (self.scale > 0 and math.isfinite(self.scale)):
            raise ValueError(f"scale must be positive and finite, got {self.scale}")


def compute_layout(
    nodes: list[NodePos],
    edges: list[EdgeRef],
    params: LayoutParams,
) -> dict[NoteId, tuple[float, float]]:
    """Compute (x, y) positions for the graph using NetworkX spring_layout.

    Surviving nodes (those with prior_x/prior_y) seed the algorithm so the
    result evolves smoothly from the previous layout. Newcomers get random
    starting positions chosen by NetworkX; their final positions are
    determined by the iterations.

    Non-finite outputs (NaN/Inf) are filtered out. Caller treats missing
    positions as "use random-center fallback at render time."
    """
    if not nodes:
        return {}

    g = nx.Graph()
    for n in nodes:
        g.add_node(n.id)
    for e in edges:
        if e.source in g and e.target in g:
            g.add_edge(e.source, e.target)

    prior: dict[NoteId, tuple[float, float]] = {
        n.id: (n.prior_x, n.prior_y)
        for n in nodes
        if n.prior_x is not None
        and n.prior_y is not None
        and math.isfinite(n.prior_x)
        and math.isfinite(n.prior_y)
    }

    raw = nx.spring_layout(
        g,
        pos=prior or None,
        iterations=params.iterations,
        k=params.link_distance,
        seed=params.seed,
        scale=params.scale,
    )

    return {
        nid: (float(x), float(y))
        for nid, (x, y) in raw.items()
        if math.isfinite(x) and math.isfinite(y)
    }
