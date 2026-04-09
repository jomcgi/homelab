"""Coverage tests for gardener.py exception and dispatch paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.gardener import Gardener


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


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
    async def test_run_counts_io_error_as_failed(self, tmp_path):
        """A missing file discovered between _discover_raw_files() and _ingest_one()
        is counted as a failure, not an unhandled crash."""
        nonexistent = tmp_path / "inbox" / "ghost.md"
        nonexistent.parent.mkdir(parents=True, exist_ok=True)

        gardener = Gardener(vault_root=tmp_path)

        def patched_discover():
            return [nonexistent]

        gardener._discover_raw_files = patched_discover  # type: ignore[method-assign]
        stats = await gardener.run()

        assert stats.failed == 1
        assert stats.ingested == 0


class TestIngestOneSubprocessFailure:
    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit_propagates_through_run(self, tmp_path):
        """When claude exits non-zero, run() counts it as failed and continues."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        proc_mock = AsyncMock()
        proc_mock.returncode = 1
        proc_mock.communicate = AsyncMock(return_value=(b"", b"some error"))

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            stats = await Gardener(vault_root=tmp_path).run()

        assert stats.failed == 1
        assert stats.ingested == 0
        # Raw file must survive — it was not soft-deleted
        assert (tmp_path / "inbox" / "raw.md").exists()

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
