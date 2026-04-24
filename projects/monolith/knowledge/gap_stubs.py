"""Stub notes for unresolved wikilinks — source of truth for gap state.

Each unresolved [[wikilink]] gets a barebones note at
_researching/<slug>.md. Claude classifies by editing the frontmatter.
The reconciler projects frontmatter changes into the gaps table.

Write semantics are mostly non-destructive: once a stub exists,
write_stub only updates ``referenced_by`` (the one field discover_gaps
recomputes each cycle); all classifier edits and body content are
preserved against re-runs of discover_gaps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

RESEARCHING_DIR = "_researching"


def write_stub(
    *,
    vault_root: Path,
    note_id: str,
    title: str,
    referenced_by: list[str],
    discovered_at: str,
) -> Path:
    """Write a barebones gap stub to _researching/<note_id>.md.

    Three behaviors keyed off file existence:
      * No file: write a fresh stub with all default fields.
      * File exists, ``referenced_by`` already matches: no-op (preserves
        mtime — important for stable reconciler reads).
      * File exists, ``referenced_by`` differs: rewrite ONLY that field;
        all other frontmatter (classifier edits like ``gap_class``,
        ``status``, ``classifier_version``, body content) is preserved.

    Returns the stub path.
    """
    stub_dir = vault_root / RESEARCHING_DIR
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / f"{note_id}.md"

    if not stub.exists():
        fm: dict[str, Any] = {
            "id": note_id,
            "title": title,
            "type": "gap",
            "status": "discovered",
            "gap_class": None,
            "referenced_by": referenced_by,
            "discovered_at": discovered_at,
            "classified_at": None,
            "classifier_version": None,
        }
        fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False)
        stub.write_text(f"---\n{fm_str}---\n\n")
        return stub

    # File exists — only touch referenced_by, preserve everything else.
    text = stub.read_text()
    if not text.startswith("---\n"):
        return stub  # Not a frontmattered stub — leave it alone.
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return stub
    fm = yaml.safe_load(parts[1])
    if not isinstance(fm, dict):
        return stub

    if fm.get("referenced_by") == referenced_by:
        return stub  # No change — skip the write to avoid mtime churn.

    fm["referenced_by"] = referenced_by
    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False)
    stub.write_text(f"---\n{fm_str}---\n{parts[2]}")
    return stub


def parse_stub_frontmatter(stub: Path) -> dict[str, Any]:
    """Parse the YAML frontmatter of a stub note into a dict.

    Returns an empty dict if the file has no valid frontmatter. Raises
    yaml.YAMLError on malformed YAML (caller decides recovery strategy).
    """
    text = stub.read_text()
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}
    meta = yaml.safe_load(parts[1])
    return meta if isinstance(meta, dict) else {}
