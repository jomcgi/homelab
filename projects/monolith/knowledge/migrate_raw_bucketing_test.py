"""Tests for the one-shot raw bucketing migration script."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.migrate_raw_bucketing import (
    _grandfather_atoms,
    _grandfather_raws,
    main,
    run_migration,
)
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


class TestSavepointRollback:
    """Verify that savepoint-wrapped inserts roll back individually on failure.

    commit c0158741 wrapped each session.add() group inside begin_nested() so
    that a failure on one file/atom leaves previously-processed rows intact and
    the outer transaction still committable.  These tests exercise that contract
    directly against the two grandfathering helpers.
    """

    def test_grandfather_raws_partial_failure_preserves_first_file(
        self, tmp_path, session
    ):
        """flush() raising IntegrityError on the 2nd file rolls back only that savepoint.

        The first file's RawInput + Note + AtomRawProvenance rows must survive
        in the session, and the session must remain committable after the error.
        """
        # Two files sorted alphabetically so processing order is deterministic.
        _write(
            tmp_path / "_deleted_with_ttl" / "aaa.md",
            "---\ntitle: AAA\n---\nBody A.",
        )
        _write(
            tmp_path / "_deleted_with_ttl" / "bbb.md",
            "---\ntitle: BBB\n---\nBody B.",
        )

        # Count calls to session.flush(); raise on the second invocation so the
        # first file's savepoint commits cleanly and the second one rolls back.
        original_flush = session.flush
        flush_call_count = 0

        def failing_flush(*args, **kwargs):
            nonlocal flush_call_count
            flush_call_count += 1
            if flush_call_count >= 2:
                raise SAIntegrityError(
                    "mock duplicate", {}, Exception("unique constraint violated")
                )
            return original_flush(*args, **kwargs)

        with patch.object(session, "flush", side_effect=failing_flush):
            with pytest.raises(SAIntegrityError):
                _grandfather_raws(tmp_path, session)

        # The outer transaction must still be committable after savepoint rollback.
        session.commit()

        # Exactly one RawInput row (for the first file).
        raws = session.exec(select(RawInput)).all()
        assert len(raws) == 1, f"expected 1 RawInput, got {len(raws)}"

        # Exactly one mirror Note of type "raw".
        notes = session.exec(select(Note).where(Note.type == "raw")).all()
        assert len(notes) == 1, f"expected 1 raw Note, got {len(notes)}"

        # Exactly one raw-sentinel AtomRawProvenance (raw_fk set, atom_fk None).
        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration",
                AtomRawProvenance.atom_fk.is_(None),
            )
        ).all()
        assert len(sentinels) == 1, f"expected 1 sentinel, got {len(sentinels)}"
        assert sentinels[0].raw_fk == raws[0].id

    def test_grandfather_atoms_partial_failure_preserves_first_atom(
        self, tmp_path, session
    ):
        """session.add() raising IntegrityError on the 2nd atom rolls back only that savepoint.

        The first atom's AtomRawProvenance row must survive and the session
        must remain committable after the error.
        """
        # Pre-seed two atoms.  IDs are assigned in insertion order so atom1 is
        # processed first by _grandfather_atoms (SQLite returns rows in rowid
        # order without an ORDER BY).
        atom1 = Note(
            note_id="atom-save-1",
            path="atoms/save-1.md",
            title="Save1",
            content_hash="h1",
            type="atom",
        )
        atom2 = Note(
            note_id="atom-save-2",
            path="atoms/save-2.md",
            title="Save2",
            content_hash="h2",
            type="atom",
        )
        session.add(atom1)
        session.add(atom2)
        session.commit()
        session.refresh(atom1)
        session.refresh(atom2)

        # Count session.add() calls for AtomRawProvenance objects; raise on the
        # second one to trigger savepoint rollback for the second atom.
        original_add = session.add
        prov_add_count = 0

        def failing_add(obj):
            nonlocal prov_add_count
            if isinstance(obj, AtomRawProvenance):
                prov_add_count += 1
                if prov_add_count >= 2:
                    raise SAIntegrityError(
                        "mock duplicate", {}, Exception("unique constraint violated")
                    )
            return original_add(obj)

        with patch.object(session, "add", side_effect=failing_add):
            with pytest.raises(SAIntegrityError):
                _grandfather_atoms(session)

        # The outer transaction must still be committable after savepoint rollback.
        session.commit()

        # Exactly one AtomRawProvenance row (for the first atom processed).
        provs = session.exec(select(AtomRawProvenance)).all()
        assert len(provs) == 1, f"expected 1 provenance row, got {len(provs)}"
        assert provs[0].atom_fk is not None, "provenance row must link to an atom"
        assert provs[0].raw_fk is None, "atom sentinel must not have a raw_fk"
        assert provs[0].gardener_version == "pre-migration"
