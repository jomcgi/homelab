"""Tests for gap stub note writing / parsing."""

from pathlib import Path

import yaml

from knowledge.gap_stubs import (
    RESEARCHING_DIR,
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
    args = {
        "vault_root": tmp_path,
        "note_id": "linkerd-mtls",
        "title": "linkerd-mtls",
        "referenced_by": ["note-a"],
        "discovered_at": "2026-04-25T08:00:00Z",
    }
    write_stub(**args)
    first = (tmp_path / RESEARCHING_DIR / "linkerd-mtls.md").read_text()
    write_stub(**{**args, "referenced_by": ["note-a", "note-c"]})
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
