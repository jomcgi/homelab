"""Tests for the one-shot raw bucketing migration script."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.migrate_raw_bucketing import main, run_migration
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


class TestMain:
    """Tests for the main() CLI entrypoint."""

    def test_main_raises_systemexit_when_no_dsn(self, tmp_path, monkeypatch):
        """main() raises SystemExit when --dsn is absent and DATABASE_URL is unset."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(
            sys, "argv", ["migrate_raw_bucketing", "--vault-root", str(tmp_path)]
        )
        with pytest.raises(SystemExit, match="--dsn or DATABASE_URL is required"):
            main()

    def test_main_uses_database_url_env_var(self, tmp_path, monkeypatch):
        """main() uses DATABASE_URL env var when --dsn is not passed on the CLI.

        run_migration is mocked to avoid the need for a real schema — the goal
        here is to verify that DATABASE_URL is accepted as the DSN source.
        """
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        monkeypatch.setattr(
            sys, "argv", ["migrate_raw_bucketing", "--vault-root", str(tmp_path)]
        )
        with patch("knowledge.migrate_raw_bucketing.run_migration") as mock_run:
            main()
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["vault_root"] == tmp_path

    def test_main_uses_vault_root_env_var(self, tmp_path, monkeypatch):
        """main() uses VAULT_ROOT env var as the default for --vault-root."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        monkeypatch.setattr(sys, "argv", ["migrate_raw_bucketing"])
        with patch("knowledge.migrate_raw_bucketing.run_migration") as mock_run:
            main()
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["vault_root"] == tmp_path

    def test_main_happy_path_with_cli_args(self, tmp_path, monkeypatch):
        """main() passes correct vault_root and a live session when called with --dsn and --vault-root."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "migrate_raw_bucketing",
                "--vault-root",
                str(tmp_path),
                "--dsn",
                "sqlite://",
            ],
        )
        with patch("knowledge.migrate_raw_bucketing.run_migration") as mock_run:
            main()
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["vault_root"] == tmp_path
        # session is the second keyword argument; it should be a live Session.
        assert kwargs["session"] is not None

    def test_main_migrates_files_end_to_end(self, tmp_path, monkeypatch):
        """main() with an SQLite DSN actually moves files and inserts DB rows.

        The SQLModel models carry ``schema="knowledge"`` for Postgres but SQLite
        does not support schemas.  The same technique used by session_fixture is
        applied here: schemas are nulled for the entire duration of the test
        (both DDL and DML), then restored in a finally block.
        """
        deleted_dir = tmp_path / "_deleted_with_ttl"
        deleted_dir.mkdir()
        (deleted_dir / "note.md").write_text(
            "---\ntitle: Legacy\nttl: 2026-01-01T00:00:00Z\n---\nContent.",
            encoding="utf-8",
        )

        # Use a file-based SQLite DB so it persists across two engine instances.
        db_path = tmp_path / "test.db"
        dsn = f"sqlite:///{db_path}"

        # Null schemas for the whole test: DDL + the main() call (DML).
        original_schemas = {}
        for table in SQLModel.metadata.tables.values():
            if table.schema is not None:
                original_schemas[table.name] = table.schema
                table.schema = None
        try:
            setup_engine = create_engine(dsn, connect_args={"check_same_thread": False})
            SQLModel.metadata.create_all(setup_engine)
            setup_engine.dispose()

            monkeypatch.delenv("DATABASE_URL", raising=False)
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "migrate_raw_bucketing",
                    "--vault-root",
                    str(tmp_path),
                    "--dsn",
                    dsn,
                ],
            )
            main()
        finally:
            for table in SQLModel.metadata.tables.values():
                if table.name in original_schemas:
                    table.schema = original_schemas[table.name]

        # _deleted_with_ttl directory should be gone after migration.
        assert not deleted_dir.exists()
        # Grandfathered file should exist under _raw/grandfathered/.
        gf_files = list((tmp_path / "_raw" / "grandfathered").glob("*.md"))
        assert len(gf_files) == 1
