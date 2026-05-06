#!/usr/bin/env python3
"""Standalone layout preview tool for the knowledge graph.

Loads a graph snapshot (JSON in the same shape as the /api/knowledge/graph
response), runs ``compute_layout`` with command-line-supplied params, and
writes a single self-contained HTML file you open in a browser to visualize
the layout. No force simulation runs in the browser — positions are baked
in by ``compute_layout`` exactly as they would be in prod.

Usage:
    python preview-layout.py \\
        --snapshot graph.json \\
        --link-distance 0.05 \\
        --iterations 50 \\
        --seed 42 \\
        --scale 1.0 \\
        --out preview.html

Once you find params you like, copy them into
``projects/monolith/deploy/values.yaml`` and trigger
``homelab scheduler jobs run-now knowledge.reconcile`` to apply without
waiting for the next reconcile cycle (the layout pass runs as the last
step of every reconcile).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from knowledge.layout import EdgeRef, LayoutParams, NodePos, compute_layout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a knowledge-graph layout preview to a self-contained HTML file."
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        help="Path to a graph JSON snapshot ({nodes:[...], edges:[...]}).",
    )
    parser.add_argument("--link-distance", type=float, default=0.05)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("preview.html"),
        help="Output HTML path (default: preview.html).",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.snapshot.read_text())
    nodes = [
        NodePos(
            id=n["id"],
            prior_x=n.get("x"),
            prior_y=n.get("y"),
        )
        for n in payload["nodes"]
    ]
    edges = [EdgeRef(source=e["source"], target=e["target"]) for e in payload["edges"]]
    params = LayoutParams(
        link_distance=args.link_distance,
        iterations=args.iterations,
        seed=args.seed,
        scale=args.scale,
    )
    positions = compute_layout(nodes, edges, params)
    args.out.write_text(_render_html(payload, positions, params))
    print(f"Wrote {args.out} ({len(positions)} positioned of {len(nodes)} nodes)")
    return 0


def _render_html(
    payload: dict,
    positions: dict[str, tuple[float, float]],
    params: LayoutParams,
) -> str:
    """Render a single self-contained HTML document with baked-in positions.

    Nodes without a computed position (filtered out by compute_layout for
    NaN/Inf) fall back to (0, 0) so the file is still well-formed.
    """
    nodes_with_pos = [
        {
            **n,
            "x": positions.get(n["id"], (0.0, 0.0))[0],
            "y": positions.get(n["id"], (0.0, 0.0))[1],
        }
        for n in payload["nodes"]
    ]
    data = json.dumps({"nodes": nodes_with_pos, "edges": payload["edges"]})
    title = html.escape(
        f"layout preview (k={params.link_distance}, iter={params.iterations}, "
        f"seed={params.seed}, scale={params.scale})"
    )
    span = 2 * params.scale
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;background:#111;color:#eee;font-family:sans-serif">
<h1 style="padding:1rem;margin:0;font-size:1rem;font-weight:normal">{title}</h1>
<svg width="100%" height="800" viewBox="-{params.scale} -{params.scale} {span} {span}" preserveAspectRatio="xMidYMid meet" style="background:#111">
<g id="g"></g>
</svg>
<script>
const data = {data};
const g = document.getElementById('g');
const ns = "http://www.w3.org/2000/svg";
const byId = new Map(data.nodes.map(n => [n.id, n]));
for (const e of data.edges) {{
    const a = byId.get(e.source), b = byId.get(e.target);
    if (!a || !b) continue;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
    line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
    line.setAttribute('stroke', '#444'); line.setAttribute('stroke-width', '0.005');
    g.appendChild(line);
}}
for (const n of data.nodes) {{
    const c = document.createElementNS(ns, 'circle');
    c.setAttribute('cx', n.x); c.setAttribute('cy', n.y);
    c.setAttribute('r', '0.015'); c.setAttribute('fill', '#4af');
    const t = document.createElementNS(ns, 'title');
    t.textContent = n.title || n.id;
    c.appendChild(t);
    g.appendChild(c);
}}
</script></body></html>"""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
