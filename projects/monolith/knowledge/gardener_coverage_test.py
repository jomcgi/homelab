"""Coverage tests for gardener.py exception and dispatch paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.gardener import Gardener
from knowledge.models import AtomRawProvenance, RawInput


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


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


class TestIngestOneFileIOError:
    @pytest.mark.asyncio
    async def test_raises_when_file_does_not_exist(self, tmp_path):
        """If the raw file doesn't exist, path.read_text() raises FileNotFoundError
        which propagates out of _ingest_one()."""
        nonexistent = tmp_path / "inbox" / "ghost.md"
        nonexistent.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately do NOT create the file

        with pytest.raises(FileNotFoundError):
            await Gardener(vault_root=tmp_path)._ingest_one(nonexistent)

    @pytest.mark.asyncio
    async def test_run_counts_io_error_as_failed(self, tmp_path, session):
        """A raw in the DB whose file is missing on disk is counted as a
        failure, not an unhandled crash."""
        # Insert a RawInput row pointing to a file that doesn't exist on disk.
        raw = RawInput(
            raw_id="ghost",
            path="_raw/2026/04/09/ghost-note.md",
            source="vault-drop",
            content="Body.",
            content_hash="ghost",
        )
        session.add(raw)
        session.commit()
        # Add outdated provenance so _grandfather_untracked_raws skips this
        # raw but _raws_needing_decomposition still picks it up.
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                derived_note_id="outdated",
                gardener_version="v0-outdated",
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        stats = await gardener.run()

        assert stats.failed == 1
        assert stats.ingested == 0


class TestIngestOneSubprocessFailure:
    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit_propagates_through_run(
        self, tmp_path, session
    ):
        """When claude exits non-zero, run() counts it as failed and continues."""
        raw_dir = tmp_path / "_raw" / "2026" / "04" / "09"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "abc1-test.md"
        raw_file.write_text("---\ntitle: Test\n---\nBody.")

        raw = RawInput(
            raw_id="abc1",
            path="_raw/2026/04/09/abc1-test.md",
            source="vault-drop",
            content="---\ntitle: Test\n---\nBody.",
            content_hash="abc1",
        )
        session.add(raw)
        session.commit()
        # Add outdated provenance so _grandfather_untracked_raws skips this
        # raw but _raws_needing_decomposition still picks it up.
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                derived_note_id="outdated",
                gardener_version="v0-outdated",
            )
        )
        session.commit()

        proc_mock = AsyncMock()
        proc_mock.returncode = 1
        proc_mock.communicate = AsyncMock(return_value=(b"", b"some error"))

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            stats = await Gardener(vault_root=tmp_path, session=session).run()

        assert stats.failed == 1
        assert stats.ingested == 0
        # Raw file must survive
        assert raw_file.exists()

    @pytest.mark.asyncio
    async def test_custom_claude_bin_is_passed_to_subprocess(self, tmp_path):
        """claude_bin override is used as the executable in the subprocess call."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")
        processed = tmp_path / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "note.md").write_text(
                "---\nid: note\ntitle: Note\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch(
            "asyncio.create_subprocess_exec", return_value=proc_mock
        ) as mock_exec:
            await Gardener(
                vault_root=tmp_path, claude_bin="/custom/claude"
            )._ingest_one(tmp_path / "inbox" / "raw.md")

        assert mock_exec.call_args[0][0] == "/custom/claude"
        assert mock_exec.call_args[1].get("cwd") == tmp_path
