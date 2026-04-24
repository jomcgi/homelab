"""Stub notes for unresolved wikilinks — source of truth for gap state.

Each unresolved [[wikilink]] gets a barebones note at
_researching/<slug>.md. Claude classifies by editing the frontmatter.
The reconciler projects frontmatter changes into the gaps table.

Write semantics are idempotent and non-destructive: once a stub exists,
write_stub is a no-op. This preserves classifier edits and user edits
against re-runs of discover_gaps.
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

    Idempotent: if the file already exists, do nothing. Never overwrites —
    classifier edits and user edits are preserved.

    Returns the stub path (whether newly written or already present).
    """
    stub_dir = vault_root / RESEARCHING_DIR
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / f"{note_id}.md"
    if stub.exists():
        return stub

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
