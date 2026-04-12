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
        # Add outdated provenance so _raws_needing_decomposition still
        # picks up this raw (version mismatch with current GARDENER_VERSION).
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
        # Add outdated provenance so _raws_needing_decomposition still
        # picks up this raw (version mismatch with current GARDENER_VERSION).
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


class TestRunClaudeSubprocessDirect:
    """Unit tests for _run_claude_subprocess() in isolation.

    These tests call the method directly (not through _ingest_one) to
    exercise the subprocess plumbing without the frontmatter/provenance
    side-effects of _ingest_one.
    """

    @pytest.mark.asyncio
    async def test_stderr_content_appears_in_nonzero_exit_error(self, tmp_path):
        """The stderr output is decoded and included in the RuntimeError message.

        _run_claude_subprocess raises RuntimeError(f"claude exited N: <stderr[:300]>").
        Callers rely on the stderr being present to diagnose failures.
        """
        proc_mock = AsyncMock()
        proc_mock.returncode = 2
        proc_mock.communicate = AsyncMock(
            return_value=(b"", b"authentication failed: token expired")
        )

        gardener = Gardener(vault_root=tmp_path)
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with pytest.raises(RuntimeError) as exc_info:
                await gardener._run_claude_subprocess("test prompt")

        assert "authentication failed: token expired" in str(exc_info.value)
        assert "claude exited 2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stderr_truncated_at_300_chars_in_error_message(self, tmp_path):
        """stderr is capped at 300 chars in the RuntimeError to avoid giant messages."""
        long_stderr = b"e" * 400  # Exceeds the 300-char cap

        proc_mock = AsyncMock()
        proc_mock.returncode = 1
        proc_mock.communicate = AsyncMock(return_value=(b"", long_stderr))

        gardener = Gardener(vault_root=tmp_path)
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with pytest.raises(RuntimeError) as exc_info:
                await gardener._run_claude_subprocess("test prompt")

        msg = str(exc_info.value)
        # Exactly 300 'e' chars — not 400 — must appear
        assert "e" * 300 in msg
        assert "e" * 301 not in msg

    @pytest.mark.asyncio
    async def test_last_stdout_stored_on_success(self, tmp_path):
        """After a successful subprocess, _last_stdout holds the stdout bytes."""
        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(return_value=(b"subprocess output here", b""))

        gardener = Gardener(vault_root=tmp_path)
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            await gardener._run_claude_subprocess("test prompt")

        assert gardener._last_stdout == b"subprocess output here"

    @pytest.mark.asyncio
    async def test_last_stdout_cleared_before_subprocess(self, tmp_path):
        """_last_stdout is reset to b'' at the start of each _ingest_one call.

        If a previous run stored stdout, it must not bleed into the next run
        so that the no-notes warning uses the current stdout only.
        """
        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(return_value=(b"", b""))
        note = tmp_path / "n.md"
        note.write_text("# T\nbody")

        gardener = Gardener(vault_root=tmp_path)
        gardener._last_stdout = b"stale output from previous run"

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            await gardener._ingest_one(note)

        # After the call, _last_stdout must reflect what the subprocess returned
        # (empty here), not the stale value.
        assert gardener._last_stdout == b""

    @pytest.mark.asyncio
    async def test_timeout_kills_and_raises_directly(self, tmp_path):
        """Calling _run_claude_subprocess directly: TimeoutError → kill → RuntimeError."""
        import asyncio as _asyncio

        proc_mock = MagicMock()
        proc_mock.returncode = None
        proc_mock.kill = MagicMock()
        proc_mock.wait = AsyncMock()

        gardener = Gardener(vault_root=tmp_path)
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("asyncio.wait_for", side_effect=_asyncio.TimeoutError):
                with pytest.raises(RuntimeError, match="timed out after 900s"):
                    await gardener._run_claude_subprocess("a prompt")

        proc_mock.kill.assert_called_once()
        proc_mock.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nonzero_exit_does_not_store_stdout(self, tmp_path):
        """When claude exits non-zero _last_stdout is not updated (exception raised first)."""
        initial = b"previous stdout"

        proc_mock = AsyncMock()
        proc_mock.returncode = 1
        proc_mock.communicate = AsyncMock(return_value=(b"irrelevant stdout", b"err"))

        gardener = Gardener(vault_root=tmp_path)
        gardener._last_stdout = initial

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with pytest.raises(RuntimeError):
                await gardener._run_claude_subprocess("test prompt")

        # _last_stdout must NOT be updated when the subprocess fails
        assert gardener._last_stdout == initial


class TestDiscoverRawFilesSymlinks:
    """Verify that _discover_raw_files() handles filesystem symlinks correctly.

    Python's Path.is_file() and Path.is_dir() follow symlinks, so symlinks to
    .md files and directories should behave identically to real files/dirs.
    Broken symlinks (no target) are silently skipped because they return False
    for both is_file() and is_dir().
    """

    def test_symlink_to_md_file_is_included(self, tmp_path):
        """A symlink whose target is an .md file appears in the discovered list."""
        # Real .md file elsewhere on disk
        target = tmp_path / "real_notes" / "real.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Real Note\nbody")

        # Symlink inside the vault root pointing to that file
        link = tmp_path / "linked-note.md"
        link.symlink_to(target)

        gardener = Gardener(vault_root=tmp_path)
        found = gardener._discover_raw_files()

        assert link in found

    def test_symlink_to_non_md_file_is_excluded(self, tmp_path):
        """A symlink pointing to a non-.md file is not included."""
        target = tmp_path / "real_notes" / "image.png"
        target.parent.mkdir(parents=True)
        target.write_text("PNG data")

        link = tmp_path / "linked-image.png"
        link.symlink_to(target)

        gardener = Gardener(vault_root=tmp_path)
        found = gardener._discover_raw_files()

        assert link not in found

    def test_broken_symlink_is_silently_skipped(self, tmp_path):
        """A symlink with no valid target (dangling) does not raise and is excluded."""
        link = tmp_path / "dangling.md"
        link.symlink_to(tmp_path / "nonexistent_target.md")
        # link.target does not exist — is_file()/is_dir() both return False

        gardener = Gardener(vault_root=tmp_path)
        # Must not raise
        found = gardener._discover_raw_files()

        assert link not in found

    def test_symlink_to_directory_is_traversed(self, tmp_path):
        """A symlink to a directory is walked like a regular directory."""
        real_dir = tmp_path / "external_notes"
        real_dir.mkdir()
        (real_dir / "note-a.md").write_text("# A\nbody")
        (real_dir / "note-b.md").write_text("# B\nbody")

        link_dir = tmp_path / "inbox"
        link_dir.symlink_to(real_dir)

        gardener = Gardener(vault_root=tmp_path)
        found = gardener._discover_raw_files()

        names = {p.name for p in found}
        assert "note-a.md" in names
        assert "note-b.md" in names


class TestDeadLetterExhaustionInRunCycle:
    """Verify that once a raw reaches _MAX_RETRIES failures it becomes a dead
    letter and is NOT re-enqueued by subsequent run() cycles.
    """

    @pytest.mark.asyncio
    async def test_exhausted_raw_not_reprocessed_after_max_retries(
        self, tmp_path, session
    ):
        """A raw with retry_count == _MAX_RETRIES is excluded from decomposition.

        Steps:
        1. Create a RawInput with a failed provenance row at exactly _MAX_RETRIES.
        2. Run the gardener cycle.
        3. Assert no ingest attempts are made and ingested/failed are both 0.
        """
        raw_dir = tmp_path / "_raw" / "2026" / "04" / "09"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "exhausted-raw.md"
        raw_file.write_text("---\ntitle: Exhausted\n---\nBody.")

        from knowledge.gardener import GARDENER_VERSION

        raw = RawInput(
            raw_id="exhausted",
            path="_raw/2026/04/09/exhausted-raw.md",
            source="vault-drop",
            content="---\ntitle: Exhausted\n---\nBody.",
            content_hash="exhausted",
        )
        session.add(raw)
        session.flush()
        # Provenance at exactly _MAX_RETRIES — this raw is a dead letter
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                derived_note_id="failed",
                gardener_version=GARDENER_VERSION,
                error="permanent failure",
                retry_count=Gardener._MAX_RETRIES,
            )
        )
        session.commit()

        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener = Gardener(vault_root=tmp_path, session=session)
        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()

        assert len(calls) == 0, "exhausted raw must not be attempted"
        assert stats.ingested == 0
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_retriable_raw_is_processed_before_exhaustion(
        self, tmp_path, session
    ):
        """A raw with retry_count == _MAX_RETRIES - 1 IS still retriable.

        This is the boundary condition: the raw is one failure away from
        exhaustion but has not yet crossed the threshold.
        """
        raw_dir = tmp_path / "_raw" / "2026" / "04" / "09"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "retriable-raw.md"
        raw_file.write_text("---\ntitle: Retriable\n---\nBody.")

        from knowledge.gardener import GARDENER_VERSION

        raw = RawInput(
            raw_id="retriable",
            path="_raw/2026/04/09/retriable-raw.md",
            source="vault-drop",
            content="---\ntitle: Retriable\n---\nBody.",
            content_hash="retriable",
        )
        session.add(raw)
        session.flush()
        # retry_count is one below max — still retriable
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                derived_note_id="failed",
                gardener_version=GARDENER_VERSION,
                error="transient error",
                retry_count=Gardener._MAX_RETRIES - 1,
            )
        )
        session.commit()

        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener = Gardener(vault_root=tmp_path, session=session)
        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()

        assert len(calls) == 1, "raw at _MAX_RETRIES - 1 must still be attempted"
        assert stats.ingested == 1

    @pytest.mark.asyncio
    async def test_error_field_populated_from_timeout_exception(
        self, tmp_path, session
    ):
        """When a timeout RuntimeError propagates to _ingest_one, the error
        field on the failed provenance row contains the timeout message."""
        import asyncio as _asyncio

        from knowledge.gardener import GARDENER_VERSION
        from sqlmodel import select

        raw_dir = tmp_path / "_raw" / "2026" / "04" / "09"
        raw_dir.mkdir(parents=True)
        raw_rel = "_raw/2026/04/09/timeout-raw.md"
        (tmp_path / raw_rel).write_text("Body.")

        raw = RawInput(
            raw_id="timeout-raw",
            path=raw_rel,
            source="vault-drop",
            content="Body.",
            content_hash="timeout-raw",
        )
        session.add(raw)
        session.commit()

        proc_mock = MagicMock()
        proc_mock.returncode = None
        proc_mock.kill = MagicMock()
        proc_mock.wait = AsyncMock()

        gardener = Gardener(vault_root=tmp_path, session=session)
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("asyncio.wait_for", side_effect=_asyncio.TimeoutError):
                with pytest.raises(RuntimeError, match="timed out"):
                    await gardener._ingest_one(tmp_path / raw_rel)

        rows = session.exec(select(AtomRawProvenance)).all()
        assert len(rows) == 1
        prov = rows[0]
        assert prov.derived_note_id == "failed"
        assert prov.error is not None
        assert "timed out" in prov.error
        assert prov.retry_count == 1
        assert prov.gardener_version == GARDENER_VERSION
