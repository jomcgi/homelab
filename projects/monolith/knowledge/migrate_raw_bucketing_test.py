"""Tests for the one-shot raw bucketing migration script."""

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.migrate_raw_bucketing import run_migration
from knowledge.models import AtomRawProvenance, Note, RawInput


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


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


class TestRunMigration:
    def test_moves_deleted_ttl_files_into_raw_grandfathered(self, tmp_path, session):
        _write(
            tmp_path / "_deleted_with_ttl" / "inbox" / "old.md",
            "---\ntitle: Old\nttl: 2026-04-09T00:00:00Z\noriginal_path: inbox/old.md\n---\nBody.",
        )

        run_migration(vault_root=tmp_path, session=session)
        session.commit()

        # _deleted_with_ttl removed.
        assert not (tmp_path / "_deleted_with_ttl").exists()
        # Moved into _raw/grandfathered.
        gf = tmp_path / "_raw" / "grandfathered"
        files = list(gf.glob("*.md"))
        assert len(files) == 1
        # ttl stripped, original_path stripped.
        body = files[0].read_text(encoding="utf-8")
        assert "ttl:" not in body
        assert "original_path:" not in body

        # raw_inputs row + mirror note row + raw sentinel provenance row.
        raws = session.exec(select(RawInput)).all()
        assert len(raws) == 1
        assert raws[0].source == "grandfathered"
        assert raws[0].original_path == "inbox/old.md"

        mirror = session.exec(select(Note).where(Note.type == "raw")).all()
        assert len(mirror) == 1
        # indexed_at must be set — previously this was passed explicitly; after
        # commit 1a7de3b0 it is omitted from the call site and relies on the
        # default_factory on Note.indexed_at.
        assert mirror[0].indexed_at is not None

        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration"
            )
        ).all()
        raw_sentinels = [s for s in sentinels if s.atom_fk is None]
        assert len(raw_sentinels) == 1
        assert raw_sentinels[0].raw_fk == raws[0].id

    def test_grandfathers_existing_atoms(self, tmp_path, session):
        atom = Note(
            note_id="pre-existing",
            path="_processed/atoms/pre-existing.md",
            title="Pre",
            content_hash="h",
            type="atom",
        )
        session.add(atom)
        session.commit()

        run_migration(vault_root=tmp_path, session=session)
        session.commit()

        atom_sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.atom_fk == atom.id,
                AtomRawProvenance.gardener_version == "pre-migration",
            )
        ).all()
        assert len(atom_sentinels) == 1
        assert atom_sentinels[0].raw_fk is None

    def test_is_idempotent(self, tmp_path, session):
        _write(
            tmp_path / "_deleted_with_ttl" / "old.md",
            "---\ntitle: Old\n---\nBody.",
        )
        atom = Note(
            note_id="a",
            path="_processed/atoms/a.md",
            title="A",
            content_hash="h",
            type="atom",
        )
        session.add(atom)
        session.commit()

        run_migration(vault_root=tmp_path, session=session)
        session.commit()
        run_migration(vault_root=tmp_path, session=session)
        session.commit()

        raws = session.exec(select(RawInput)).all()
        assert len(raws) == 1
        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration"
            )
        ).all()
        # One raw sentinel + one atom sentinel.
        assert len(sentinels) == 2
