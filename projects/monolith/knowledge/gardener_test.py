"""Tests for the knowledge gardener."""

import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.gardener import (
    Gardener,
    _slugify,
    _split_frontmatter,
)


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestDiscoverRawFiles:
    def test_finds_md_files_outside_processed_and_raw(self, tmp_path):
        _write(tmp_path, "inbox/new-note.md", "---\ntitle: New\n---\nBody.")
        _write(tmp_path, "_processed/existing.md", "---\nid: e\ntitle: E\n---\nBody.")
        _write(
            tmp_path,
            "_raw/2026/04/09/abc-old.md",
            "---\ntitle: Old\n---\nBody.",
        )
        gardener = Gardener(vault_root=tmp_path)
        raw = gardener._discover_raw_files()
        assert len(raw) == 1
        assert raw[0].name == "new-note.md"

    def test_ignores_non_md_files(self, tmp_path):
        _write(tmp_path, "inbox/image.png", "not markdown")
        _write(tmp_path, "inbox/note.md", "---\ntitle: Note\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path)
        raw = gardener._discover_raw_files()
        assert len(raw) == 1

    def test_ignores_dotfiles_and_dot_directories(self, tmp_path):
        _write(tmp_path, ".obsidian/config.md", "config")
        _write(tmp_path, "inbox/.hidden.md", "hidden")
        _write(tmp_path, "inbox/visible.md", "---\ntitle: V\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path)
        raw = gardener._discover_raw_files()
        assert len(raw) == 1


class TestMaxFilesPerRun:
    @pytest.mark.asyncio
    async def test_cap_limits_ingest_to_max_files(self, tmp_path, session):
        """run() processes at most max_files_per_run raw files per cycle,
        leaving the remainder for a future tick."""
        for i in range(5):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody {i}.")
        gardener = Gardener(vault_root=tmp_path, max_files_per_run=2, session=session)
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()
        assert len(calls) == 2
        assert stats.ingested == 2
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_cap_disabled_when_zero_or_negative(self, tmp_path, session):
        """max_files_per_run <= 0 disables the cap."""
        for i in range(3):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, max_files_per_run=0, session=session)
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()
        assert len(calls) == 3
        assert stats.ingested == 3


class TestIngestOneClaude:
    @pytest.mark.asyncio
    async def test_prompt_includes_full_raw_content_for_frontmatter_only_note(
        self, tmp_path
    ):
        """Frontmatter-only notes (e.g. book refs) must include the raw YAML in the prompt.

        If only `body` is passed, Claude receives an empty string and has nothing
        to decompose, causing timeouts and producing no notes.
        """
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "book.md"
        raw = (
            "---\n"
            "title: The Staff Engineer's Path\n"
            "author: Tanya Reilly\n"
            "description: A book about staff engineering.\n"
            "isbn13: 9781098118709\n"
            "---\n"
        )
        note.write_text(raw)
        processed = vault / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "staff-path.md").write_text(
                "---\nid: staff-path\ntitle: Staff Path\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch(
            "asyncio.create_subprocess_exec", return_value=proc_mock
        ) as mock_exec:
            await Gardener(vault_root=vault)._ingest_one(note)

        args = mock_exec.call_args[0]
        # The prompt is passed via the -p flag as the last positional arg
        p_idx = list(args).index("-p")
        prompt = args[p_idx + 1]
        assert "Tanya Reilly" in prompt, "frontmatter author must appear in prompt"
        assert "9781098118709" in prompt, "frontmatter isbn must appear in prompt"
        assert "A book about staff engineering." in prompt, (
            "description must appear in prompt"
        )

    @pytest.mark.asyncio
    async def test_spawns_claude_with_correct_flags(self, tmp_path):
        """_ingest_one spawns claude with --dangerously-skip-permissions and cwd=vault_root."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\nsome content")
        processed = vault / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch(
            "asyncio.create_subprocess_exec", return_value=proc_mock
        ) as mock_exec:
            await Gardener(vault_root=vault)._ingest_one(note)

        args = mock_exec.call_args[0]
        kwargs = mock_exec.call_args[1]
        assert args[0] == "claude"
        assert "--print" in args
        assert "--dangerously-skip-permissions" in args
        assert "--allowedTools" in args
        allowed_idx = list(args).index("--allowedTools")
        allowed_tools = args[allowed_idx + 1]
        assert "Bash" in allowed_tools
        assert "Write" in allowed_tools
        assert kwargs.get("cwd") == vault
        assert kwargs.get("env", {}).get("HOME") == "/tmp"

    @pytest.mark.asyncio
    async def test_raw_file_stays_in_place_after_decomposition(self, tmp_path):
        """Raw file stays in _raw/ after successful decomposition (no soft delete)."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")
        processed = vault / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            await Gardener(vault_root=vault)._ingest_one(note)

        # Raw file stays in place (no soft delete to _deleted_with_ttl/)
        assert note.exists()

    @pytest.mark.asyncio
    async def test_leaves_raw_when_no_notes_created(self, tmp_path):
        """Raw file stays if claude exits 0 but writes no notes."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            await Gardener(vault_root=vault)._ingest_one(note)

        assert note.exists()

    @pytest.mark.asyncio
    async def test_passes_home_tmp_in_env(self, tmp_path):
        """_ingest_one passes env kwarg with HOME=/tmp and inherits os.environ keys."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\nsome content")
        processed = vault / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch(
            "asyncio.create_subprocess_exec", return_value=proc_mock
        ) as mock_exec:
            await Gardener(vault_root=vault)._ingest_one(note)

        kwargs = mock_exec.call_args[1]
        env = kwargs.get("env")
        assert env is not None, "env kwarg must be passed to create_subprocess_exec"
        assert env.get("HOME") == "/tmp"
        # os.environ keys must be inherited (spot-check PATH which is always set)
        assert "PATH" in env
        assert env.get("PATH") == os.environ.get("PATH")

    @pytest.mark.asyncio
    async def test_logs_stdout_when_no_notes_created(self, tmp_path, caplog):
        """When claude exits 0 but creates no notes, the warning log includes stdout content."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(return_value=(b"some debug output", b""))

        with caplog.at_level(logging.WARNING, logger="monolith.knowledge.gardener"):
            with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
                await Gardener(vault_root=vault)._ingest_one(note)

        assert note.exists()
        assert "some debug output" in caplog.text

    @pytest.mark.asyncio
    async def test_stdout_included_in_no_notes_warning(self, tmp_path, caplog):
        """When claude exits 0 but creates no notes, stdout is included in warning log."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(
            return_value=(b"I refused to create files.", b"")
        )

        with caplog.at_level(logging.WARNING, logger="monolith.knowledge.gardener"):
            with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
                await Gardener(vault_root=vault)._ingest_one(note)

        assert note.exists()
        assert "I refused to create files." in caplog.text

    @pytest.mark.asyncio
    async def test_stdout_truncated_at_500_chars_in_no_notes_warning(
        self, tmp_path, caplog
    ):
        """stdout is truncated to 500 chars in the no-notes warning to avoid huge logs."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        long_stdout = b"x" * 600  # Exceeds the 500-char cap

        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(return_value=(long_stdout, b""))

        with caplog.at_level(logging.WARNING, logger="monolith.knowledge.gardener"):
            with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
                await Gardener(vault_root=vault)._ingest_one(note)

        # The full 600-char string must NOT appear; only the first 500 chars are logged
        assert "x" * 501 not in caplog.text
        assert "x" * 500 in caplog.text

    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self, tmp_path):
        """RuntimeError is raised when claude exits with non-zero status."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = AsyncMock()
        proc_mock.returncode = 1
        proc_mock.communicate = AsyncMock(return_value=(b"", b"auth error"))

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with pytest.raises(RuntimeError, match="claude exited 1"):
                await Gardener(vault_root=vault)._ingest_one(note)

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self, tmp_path):
        """RuntimeError is raised and subprocess killed when wait_for times out."""
        import asyncio as _asyncio

        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = MagicMock()
        proc_mock.returncode = None
        proc_mock.kill = MagicMock()
        proc_mock.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("asyncio.wait_for", side_effect=_asyncio.TimeoutError):
                with pytest.raises(RuntimeError, match="timed out"):
                    await Gardener(vault_root=vault)._ingest_one(note)

        proc_mock.kill.assert_called_once()
        proc_mock.wait.assert_awaited_once()


class TestSlugify:
    def test_ascii_text(self):
        assert _slugify("Hello World") == "hello-world"

    def test_unicode_nfkd_strips_accents(self):
        assert _slugify("Héllo") == "hello"

    def test_empty_string_returns_note(self):
        assert _slugify("") == "note"

    def test_multiple_special_chars_collapse_to_single_hyphen(self):
        assert _slugify("Hello!! World") == "hello-world"


class TestSplitFrontmatter:
    def test_valid_frontmatter_splits_correctly(self):
        raw = "---\ntitle: Test\n---\nBody"
        meta, body = _split_frontmatter(raw)
        assert meta == {"title": "Test"}
        assert body == "Body"

    def test_no_frontmatter_returns_empty_dict_and_raw(self):
        raw = "No frontmatter"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_unclosed_frontmatter_returns_empty_dict_and_raw(self):
        raw = "---\ntitle: Test\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_non_dict_yaml_returns_empty_dict_and_raw(self):
        raw = "---\n- item1\n- item2\n---\nBody"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_invalid_yaml_returns_empty_dict_and_raw(self):
        raw = "---\n: invalid: yaml:\n---\nBody"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_title_with_unquoted_colon_parses(self):
        raw = "---\ntitle: Concept: Important Idea\ntype: atom\n---\nBody"
        meta, body = _split_frontmatter(raw)
        assert meta == {"title": "Concept: Important Idea", "type": "atom"}
        assert body == "Body"


class TestRunFailurePath:
    @pytest.mark.asyncio
    async def test_continues_after_mid_run_failure(self, tmp_path, session):
        """run() continues processing files even when one raises an exception."""
        for name in ("after.md", "before.md", "middle.md"):
            _write(tmp_path, name, f"---\ntitle: {name}\n---\nBody.")

        gardener = Gardener(vault_root=tmp_path, session=session)
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)
            if "middle" in path.name:
                raise RuntimeError("simulated ingest failure")

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()

        assert len(calls) == 3
        assert stats.ingested == 2
        assert stats.failed == 1


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


class TestGardenerSkipsAlreadyProcessedRaws:
    def test_raws_with_current_version_provenance_are_skipped(self, tmp_path, session):
        from knowledge.gardener import GARDENER_VERSION
        from knowledge.models import AtomRawProvenance, RawInput

        raw = RawInput(
            raw_id="r1",
            path="_raw/2026/04/09/r1-n.md",
            source="vault-drop",
            content="Body.",
            content_hash="r1",
        )
        session.add(raw)
        session.flush()
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                gardener_version=GARDENER_VERSION,
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        to_process = gardener._raws_needing_decomposition()
        assert [r.raw_id for r in to_process] == []

    def test_grandfathered_sentinel_blocks_decomposition(self, tmp_path, session):
        from knowledge.models import AtomRawProvenance, RawInput

        raw = RawInput(
            raw_id="r2",
            path="_raw/grandfathered/r2-n.md",
            source="grandfathered",
            content="Body.",
            content_hash="r2",
        )
        session.add(raw)
        session.flush()
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                gardener_version="pre-migration",
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        assert gardener._raws_needing_decomposition() == []

    def test_new_raw_is_surfaced(self, tmp_path, session):
        from knowledge.models import RawInput

        raw = RawInput(
            raw_id="r3",
            path="_raw/2026/04/09/r3-n.md",
            source="vault-drop",
            content="Body.",
            content_hash="r3",
        )
        session.add(raw)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        surfaced = gardener._raws_needing_decomposition()
        assert [r.raw_id for r in surfaced] == ["r3"]


class TestIngestOneRecordsPendingProvenance:
    @pytest.mark.asyncio
    async def test_inserts_pending_provenance_for_new_files(self, tmp_path, session):
        """After claude produces atoms, the gardener records
        pending atom_raw_provenance rows keyed by derived_note_id."""
        from knowledge.gardener import GARDENER_VERSION
        from knowledge.models import AtomRawProvenance, RawInput

        (tmp_path / "_raw" / "2026" / "04" / "09").mkdir(parents=True)
        raw_rel_path = "_raw/2026/04/09/r1-n.md"
        (tmp_path / raw_rel_path).write_text("Body.", encoding="utf-8")
        (tmp_path / "_processed").mkdir()

        raw = RawInput(
            raw_id="r1",
            path=raw_rel_path,
            source="vault-drop",
            content="Body.",
            content_hash="r1",
        )
        session.add(raw)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)

        async def fake_subprocess(prompt: str) -> None:
            (tmp_path / "_processed" / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nBody.\n",
                encoding="utf-8",
            )

        gardener._run_claude_subprocess = fake_subprocess  # type: ignore[method-assign]

        await gardener._ingest_one(tmp_path / raw_rel_path)

        rows = session.exec(select(AtomRawProvenance)).all()
        assert len(rows) == 1
        assert rows[0].raw_fk == raw.id
        assert rows[0].atom_fk is None
        assert rows[0].derived_note_id == "hello"
        assert rows[0].gardener_version == GARDENER_VERSION


class TestGardenerRunPhases:
    @pytest.mark.asyncio
    async def test_run_invokes_move_then_reconcile_then_decompose(
        self, tmp_path, session
    ):
        from knowledge.models import RawInput

        (tmp_path / "inbox").mkdir()
        (tmp_path / "inbox" / "note.md").write_text(
            "---\ntitle: Note\n---\nBody.", encoding="utf-8"
        )

        gardener = Gardener(vault_root=tmp_path, session=session)
        gardener._ingest_one = AsyncMock()

        stats = await gardener.run()

        assert not (tmp_path / "inbox" / "note.md").exists()
        raw_files = list((tmp_path / "_raw").rglob("*.md"))
        assert len(raw_files) == 1
        raws_in_db = session.exec(select(RawInput)).all()
        assert len(raws_in_db) == 1
        assert gardener._ingest_one.call_count == 1
        assert stats.ingested == 1
