"""Tests for gap stub note writing / parsing."""

from pathlib import Path

import yaml

from knowledge.gap_stubs import (
    RESEARCHING_DIR,
    dedupe_stub_frontmatter,
    parse_stub_frontmatter,
    write_stub,
)


def test_write_stub_creates_file_with_expected_frontmatter(tmp_path: Path) -> None:
    write_stub(
        vault_root=tmp_path,
        note_id="linkerd-mtls",
        title="linkerd-mtls",
        referenced_by=["note-a", "note-b"],
        discovered_at="2026-04-25T08:00:00Z",
    )
    stub = tmp_path / RESEARCHING_DIR / "linkerd-mtls.md"
    assert stub.is_file()
    body = stub.read_text()
    assert body.startswith("---\n")
    fm_block = body.split("---\n", 2)[1]
    meta = yaml.safe_load(fm_block)
    assert meta == {
        "id": "linkerd-mtls",
        "title": "linkerd-mtls",
        "type": "gap",
        "status": "discovered",
        "gap_class": None,
        "referenced_by": ["note-a", "note-b"],
        "discovered_at": "2026-04-25T08:00:00Z",
        "classified_at": None,
        "classifier_version": None,
    }


def test_write_stub_is_idempotent(tmp_path: Path) -> None:
    """Identical args on a second call must not rewrite the file."""
    args = {
        "vault_root": tmp_path,
        "note_id": "linkerd-mtls",
        "title": "linkerd-mtls",
        "referenced_by": ["note-a"],
        "discovered_at": "2026-04-25T08:00:00Z",
    }
    write_stub(**args)
    first = (tmp_path / RESEARCHING_DIR / "linkerd-mtls.md").read_text()
    write_stub(**args)
    second = (tmp_path / RESEARCHING_DIR / "linkerd-mtls.md").read_text()
    assert first == second


def test_parse_stub_frontmatter_roundtrips(tmp_path: Path) -> None:
    write_stub(
        vault_root=tmp_path,
        note_id="linkerd-mtls",
        title="linkerd-mtls",
        referenced_by=["note-a"],
        discovered_at="2026-04-25T08:00:00Z",
    )
    stub = tmp_path / RESEARCHING_DIR / "linkerd-mtls.md"
    meta = parse_stub_frontmatter(stub)
    assert meta["id"] == "linkerd-mtls"
    assert meta["type"] == "gap"
    assert meta["status"] == "discovered"
    assert meta["gap_class"] is None


def test_parse_stub_frontmatter_with_classification(tmp_path: Path) -> None:
    """A stub Claude has already edited carries gap_class + classified_at."""
    stub = tmp_path / RESEARCHING_DIR / "my-therapist.md"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(
        "---\n"
        "id: my-therapist\n"
        "title: my-therapist\n"
        "type: gap\n"
        "status: classified\n"
        "gap_class: internal\n"
        "referenced_by:\n"
        "  - note-a\n"
        'discovered_at: "2026-04-25T08:00:00Z"\n'
        'classified_at: "2026-04-25T08:05:00Z"\n'
        'classifier_version: "opus-4-7@v1"\n'
        "---\n\n"
    )
    meta = parse_stub_frontmatter(stub)
    assert meta["gap_class"] == "internal"
    assert meta["status"] == "classified"
    assert meta["classifier_version"] == "opus-4-7@v1"


def test_write_stub_updates_referenced_by_on_existing_stub(tmp_path):
    """write_stub updates referenced_by when the file exists with a stale list."""
    from knowledge.gap_stubs import write_stub
    import yaml

    write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a", "src-b"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    stub = (tmp_path / "_researching" / "merkle-tree.md").read_text()
    fm = yaml.safe_load(stub.split("---\n", 2)[1])
    assert fm["referenced_by"] == ["src-a", "src-b"]


def test_write_stub_preserves_classifier_edits(tmp_path):
    """Classifier-edited keys (gap_class, status, classifier_version) survive a referenced_by update."""
    from datetime import datetime, timezone

    import yaml

    from knowledge.gap_stubs import write_stub

    stub_path = write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    # Simulate a classifier edit.
    classified_at = datetime.now(timezone.utc).isoformat()
    text = stub_path.read_text()
    parts = text.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    fm["gap_class"] = "external"
    fm["status"] = "classified"
    fm["classifier_version"] = "opus-4-7@v1"
    fm["classified_at"] = classified_at
    new_fm = yaml.dump(fm, default_flow_style=False, sort_keys=False)
    stub_path.write_text(f"---\n{new_fm}---\n{parts[2]}")

    # Now discover_gaps re-runs and adds a second source note.
    write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a", "src-b"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    fm_after = yaml.safe_load(stub_path.read_text().split("---\n", 2)[1])
    assert fm_after["referenced_by"] == ["src-a", "src-b"], (
        "referenced_by should be updated"
    )
    assert fm_after["gap_class"] == "external", "classifier edits must survive"
    assert fm_after["status"] == "classified"
    assert fm_after["classifier_version"] == "opus-4-7@v1"
    assert fm_after["classified_at"] == classified_at


def test_write_stub_idempotent_when_referenced_by_matches(tmp_path):
    """No write happens when referenced_by already matches — no mtime churn."""
    from knowledge.gap_stubs import write_stub

    stub_path = write_stub(
        vault_root=tmp_path,
        note_id="m",
        title="m",
        referenced_by=["a", "b"],
        discovered_at="2026-04-25T00:00:00Z",
    )
    mtime_before = stub_path.stat().st_mtime_ns

    write_stub(
        vault_root=tmp_path,
        note_id="m",
        title="m",
        referenced_by=["a", "b"],
        discovered_at="2026-04-25T00:00:00Z",
    )
    mtime_after = stub_path.stat().st_mtime_ns

    assert mtime_after == mtime_before, "no-change call must not rewrite the file"


def test_dedupe_stub_frontmatter_collapses_duplicate_keys(tmp_path):
    """Stubs with duplicate status keys (from append-not-replace edits) get cleaned."""
    stub_dir = tmp_path / "_researching"
    stub_dir.mkdir()
    bad_stub = stub_dir / "accelerate.md"
    # Hand-crafted duplicate-key frontmatter — PyYAML's safe_load takes
    # last-wins, so this is parseable but ugly.
    bad_stub.write_text(
        "---\n"
        "id: accelerate\n"
        "title: accelerate\n"
        "type: gap\n"
        "status: discovered\n"
        "gap_class: external\n"
        "referenced_by:\n"
        "- sre-synthesis-pattern\n"
        "discovered_at: '2026-04-24T22:50:23Z'\n"
        "classified_at: '2026-04-24T23:00:00Z'\n"
        "classifier_version: opus-4-7@v1\n"
        "status: classified\n"
        "---\n\n"
    )

    cleaned = dedupe_stub_frontmatter(tmp_path)
    assert cleaned == 1, f"Expected one stub cleaned, got {cleaned}"

    # Round-tripped frontmatter has only one status key, last-wins value.
    fm = yaml.safe_load(bad_stub.read_text().split("---\n", 2)[1])
    assert fm["status"] == "classified"
    text = bad_stub.read_text()
    assert text.count("status:") == 1, (
        f"Expected one status key, got {text.count('status:')}"
    )


def test_dedupe_stub_frontmatter_idempotent(tmp_path):
    """Clean stubs and a second run is a no-op."""
    write_stub(
        vault_root=tmp_path,
        note_id="m",
        title="m",
        referenced_by=["a"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    first = dedupe_stub_frontmatter(tmp_path)
    second = dedupe_stub_frontmatter(tmp_path)
    assert first == 0, "Already-clean stub should not need cleaning"
    assert second == 0


def test_dedupe_stub_frontmatter_handles_missing_dir(tmp_path):
    """No _researching/ directory → no-op (returns 0)."""
    assert dedupe_stub_frontmatter(tmp_path) == 0
