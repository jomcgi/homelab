"""Smoke tests for preview-layout.py.

The script's filename contains a hyphen, so it can't be imported as a normal
module. Match the pattern used by ``generate_red_dashboard_test.py`` and
load it via ``importlib.util.spec_from_file_location``.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

# ---------------------------------------------------------------------------
# Import the hyphenated script via importlib
# ---------------------------------------------------------------------------

_SCRIPT = pathlib.Path(__file__).parent / "preview-layout.py"
_spec = importlib.util.spec_from_file_location("preview_layout", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_preview_layout_writes_html_with_circles(tmp_path):
    """Snapshot in -> preview HTML out, with the right shapes baked in."""
    snap = tmp_path / "graph.json"
    snap.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "a", "title": "A"},
                    {"id": "b", "title": "B"},
                ],
                "edges": [{"source": "a", "target": "b"}],
            }
        )
    )
    out = tmp_path / "preview.html"
    rc = main(["--snapshot", str(snap), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    body = out.read_text()
    assert "<svg" in body
    assert body.count("<circle") == 2  # one per node
    assert "<line" in body  # one edge
    assert "</html>" in body  # well-formed close


def test_preview_layout_handles_missing_optional_keys(tmp_path):
    """Snapshot nodes can omit x/y keys (newcomers); script must not crash."""
    snap = tmp_path / "graph.json"
    snap.write_text(
        json.dumps(
            {
                "nodes": [{"id": "n1", "title": "N1"}],
                "edges": [],
            }
        )
    )
    out = tmp_path / "preview.html"
    rc = main(["--snapshot", str(snap), "--out", str(out)])
    assert rc == 0
    assert out.exists()


def test_preview_layout_html_is_self_contained(tmp_path):
    """No external <script src> or <link href> in the output."""
    snap = tmp_path / "graph.json"
    snap.write_text(
        json.dumps(
            {
                "nodes": [{"id": "a", "title": "A"}],
                "edges": [],
            }
        )
    )
    out = tmp_path / "preview.html"
    rc = main(["--snapshot", str(snap), "--out", str(out)])
    assert rc == 0
    body = out.read_text()
    assert "<script src=" not in body
    assert "<link " not in body


def test_preview_layout_passes_params_to_compute_layout(tmp_path, monkeypatch):
    """CLI args end up as a LayoutParams passed to compute_layout."""
    captured = {}

    real_compute = _mod.compute_layout

    def spy(nodes, edges, params):
        captured["params"] = params
        return real_compute(nodes, edges, params)

    monkeypatch.setattr(_mod, "compute_layout", spy)

    snap = tmp_path / "graph.json"
    snap.write_text(
        json.dumps(
            {
                "nodes": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
                "edges": [{"source": "a", "target": "b"}],
            }
        )
    )
    out = tmp_path / "preview.html"
    rc = main(
        [
            "--snapshot",
            str(snap),
            "--link-distance",
            "0.1",
            "--iterations",
            "25",
            "--seed",
            "7",
            "--scale",
            "2.0",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    p = captured["params"]
    assert p.link_distance == 0.1
    assert p.iterations == 25
    assert p.seed == 7
    assert p.scale == 2.0
