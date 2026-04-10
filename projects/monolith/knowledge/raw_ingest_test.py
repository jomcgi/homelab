"""Tests for raw ingest Phase A (move) and Phase B (reconcile)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Note, RawInput
from knowledge.raw_ingest import (
    MovePhaseStats,
    ReconcileRawStats,
    move_phase,
    reconcile_raw_phase,
)


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestMovePhase:
    def test_moves_vault_root_md_into_raw_tree(self, tmp_path):
        _write(tmp_path / "inbox" / "note.md", "---\ntitle: Note\n---\nBody.")
        now = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
        stats = move_phase(vault_root=tmp_path, now=now)
        assert stats.moved == 1
        assert stats.deduped == 0
        assert not (tmp_path / "inbox" / "note.md").exists()
        date_dir = tmp_path / "_raw" / "2026" / "04" / "09"
        targets = list(date_dir.glob("*.md"))
        assert len(targets) == 1
        assert targets[0].read_text(encoding="utf-8").startswith("---")

    def test_skips_files_already_under_managed_dirs(self, tmp_path):
        _write(tmp_path / "_raw" / "2026" / "04" / "09" / "abc-note.md", "x")
        _write(tmp_path / "_processed" / "atoms" / "a.md", "y")
        _write(tmp_path / "_deleted_with_ttl" / "old.md", "z")
        stats = move_phase(
            vault_root=tmp_path,
            now=datetime(2026, 4, 9, tzinfo=timezone.utc),
        )
        assert stats.moved == 0

    def test_dedup_deletes_source_when_target_exists(self, tmp_path):
        content = "---\ntitle: Dup\n---\nSame body."
        _write(tmp_path / "inbox" / "a.md", content)
        _write(tmp_path / "inbox" / "b.md", content)  # identical content -> same raw_id
        now = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
        stats = move_phase(vault_root=tmp_path, now=now)
        # First gets moved, second is deduped (source deleted).
        assert stats.moved == 1
        assert stats.deduped == 1
        remaining = list((tmp_path / "inbox").glob("*.md"))
        assert remaining == []

    def test_ignores_dotfiles_and_dot_dirs(self, tmp_path):
        _write(tmp_path / ".obsidian" / "config.md", "x")
        _write(tmp_path / "inbox" / ".hidden.md", "y")
        _write(tmp_path / "inbox" / "visible.md", "---\ntitle: V\n---\nB")
        stats = move_phase(
            vault_root=tmp_path,
            now=datetime(2026, 4, 9, tzinfo=timezone.utc),
        )
        assert stats.moved == 1


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


class TestReconcileRawPhase:
    def test_inserts_raw_input_and_mirror_note_row(self, tmp_path, session):
        raw_file = tmp_path / "_raw" / "2026" / "04" / "09" / "abc1-my-note.md"
        raw_file.parent.mkdir(parents=True)
        raw_file.write_text(
            "---\ntitle: My Note\nsource: vault-drop\n---\nBody.",
            encoding="utf-8",
        )

        stats = reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        assert stats.inserted == 1
        assert stats.skipped == 0

        rows = session.exec(select(RawInput)).all()
        assert len(rows) == 1
        assert rows[0].path == "_raw/2026/04/09/abc1-my-note.md"
        assert rows[0].source == "vault-drop"

        notes = session.exec(select(Note).where(Note.type == "raw")).all()
        assert len(notes) == 1
        assert notes[0].note_id == rows[0].raw_id

    def test_is_idempotent(self, tmp_path, session):
        raw_file = tmp_path / "_raw" / "2026" / "04" / "09" / "abc1-my-note.md"
        raw_file.parent.mkdir(parents=True)
        raw_file.write_text("---\ntitle: N\n---\nBody.", encoding="utf-8")

        reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()
        stats = reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        assert stats.inserted == 0
        assert stats.skipped == 1
        assert len(session.exec(select(RawInput)).all()) == 1

    def test_missing_raw_dir_is_noop(self, tmp_path, session):
        stats = reconcile_raw_phase(vault_root=tmp_path, session=session)
        assert stats.inserted == 0
        assert stats.skipped == 0
