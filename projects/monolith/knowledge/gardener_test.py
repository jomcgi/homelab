"""Tests for the knowledge gardener."""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    def test_finds_md_files_outside_processed_and_deleted(self, tmp_path):
        _write(tmp_path, "inbox/new-note.md", "---\ntitle: New\n---\nBody.")
        _write(tmp_path, "_processed/existing.md", "---\nid: e\ntitle: E\n---\nBody.")
        _write(
            tmp_path,
            "_deleted_with_ttl/old.md",
            "---\nttl: 2026-01-01T00:00:00Z\n---\nBody.",
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
    async def test_cap_limits_ingest_to_max_files(self, tmp_path):
        """run() processes at most max_files_per_run raw files per cycle,
        leaving the remainder for a future tick."""
        for i in range(5):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody {i}.")
        gardener = Gardener(vault_root=tmp_path, max_files_per_run=2)
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()
        assert len(calls) == 2
        assert stats.ingested == 2
        assert stats.failed == 0
        # The remaining 3 files must still be on disk waiting for the next tick.
        remaining = sorted(
            p.name for p in (tmp_path / "inbox").glob("*.md") if p.is_file()
        )
        assert len(remaining) == 5  # fake ingest doesn't soft-delete

    @pytest.mark.asyncio
    async def test_cap_disabled_when_zero_or_negative(self, tmp_path):
        """max_files_per_run <= 0 disables the cap."""
        for i in range(3):
            _write(tmp_path, f"inbox/note-{i}.md", f"---\ntitle: N{i}\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, max_files_per_run=0)
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()
        assert len(calls) == 3
        assert stats.ingested == 3


class TestTtlCleanup:
    def test_deletes_expired_files(self, tmp_path):
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _write(
            tmp_path, "_deleted_with_ttl/old.md", f'---\nttl: "{expired}"\n---\nBody.'
        )
        gardener = Gardener(vault_root=tmp_path)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "old.md").exists()

    def test_keeps_non_expired_files(self, tmp_path):
        future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
        _write(
            tmp_path, "_deleted_with_ttl/recent.md", f'---\nttl: "{future}"\n---\nBody.'
        )
        gardener = Gardener(vault_root=tmp_path)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0
        assert (tmp_path / "_deleted_with_ttl" / "recent.md").exists()

    def test_handles_missing_ttl_frontmatter(self, tmp_path):
        _write(tmp_path, "_deleted_with_ttl/no-ttl.md", "---\ntitle: Oops\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path)
        cleaned = gardener._cleanup_ttl()
        # No ttl = don't delete (conservative)
        assert cleaned == 0

    def test_handles_empty_deleted_dir(self, tmp_path):
        gardener = Gardener(vault_root=tmp_path)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0

    def test_treats_naive_expired_datetime_as_utc(self, tmp_path):
        # Naive ISO datetime in the past (no tz suffix)
        expired_naive = (
            (datetime.now(timezone.utc) - timedelta(hours=1))
            .replace(tzinfo=None)
            .isoformat()
        )
        _write(
            tmp_path,
            "_deleted_with_ttl/naive.md",
            f'---\nttl: "{expired_naive}"\n---\nBody.',
        )
        gardener = Gardener(vault_root=tmp_path)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "naive.md").exists()

    def test_skips_corrupt_ttl_but_cleans_expired_sibling(self, tmp_path):
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _write(
            tmp_path,
            "_deleted_with_ttl/valid.md",
            f'---\nttl: "{expired}"\n---\nValid.',
        )
        _write(
            tmp_path,
            "_deleted_with_ttl/corrupt.md",
            "---\nttl: not-a-datetime\n---\nCorrupt.",
        )
        gardener = Gardener(vault_root=tmp_path)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "valid.md").exists()
        assert (tmp_path / "_deleted_with_ttl" / "corrupt.md").exists()


class TestSoftDelete:
    def test_moves_file_with_existing_frontmatter_and_injects_ttl(self, tmp_path):
        _write(
            tmp_path,
            "inbox/note.md",
            "---\ntitle: Hello\ntags: [a, b]\n---\nBody text.\n",
        )
        gardener = Gardener(vault_root=tmp_path)
        source = tmp_path / "inbox" / "note.md"
        gardener._soft_delete(source)

        assert not source.exists()
        dest = tmp_path / "_deleted_with_ttl" / "inbox" / "note.md"
        assert dest.exists()
        content = dest.read_text()
        assert "ttl:" in content
        assert "title: Hello" in content
        # Body preserved
        assert "Body text." in content

    def test_adds_frontmatter_to_file_without_any(self, tmp_path):
        _write(tmp_path, "inbox/plain.md", "Just body, no frontmatter.\n")
        gardener = Gardener(vault_root=tmp_path)
        source = tmp_path / "inbox" / "plain.md"
        gardener._soft_delete(source)

        dest = tmp_path / "_deleted_with_ttl" / "inbox" / "plain.md"
        assert dest.exists()
        content = dest.read_text()
        assert content.startswith("---\n")
        assert "ttl:" in content
        assert "Just body, no frontmatter." in content

    def test_overwrites_existing_ttl(self, tmp_path):
        """If the file already has a ttl (e.g. already soft-deleted), new ttl wins."""
        old_ttl = "2020-01-01T00:00:00+00:00"
        _write(
            tmp_path,
            "inbox/retry.md",
            f'---\nttl: "{old_ttl}"\ntitle: X\n---\nBody.\n',
        )
        gardener = Gardener(vault_root=tmp_path)
        source = tmp_path / "inbox" / "retry.md"
        gardener._soft_delete(source)

        dest = tmp_path / "_deleted_with_ttl" / "inbox" / "retry.md"
        content = dest.read_text()
        # Old ttl must not be present
        assert old_ttl not in content
        assert "ttl:" in content
        assert content.count("ttl:") == 1


class TestIngestOneClaude:
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
    async def test_soft_deletes_after_notes_created(self, tmp_path):
        """Raw file is moved to _deleted_with_ttl/ if claude creates notes in _processed/."""
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

        assert not note.exists()
        deleted = list((vault / "_deleted_with_ttl").rglob("*.md"))
        assert len(deleted) == 1

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


class TestRunFailurePath:
    @pytest.mark.asyncio
    async def test_continues_after_mid_run_failure(self, tmp_path):
        """run() continues processing files even when one raises an exception."""
        for name in ("after.md", "before.md", "middle.md"):
            _write(tmp_path, name, f"---\ntitle: {name}\n---\nBody.")

        gardener = Gardener(vault_root=tmp_path)
        calls: list[Path] = []

        async def fake_ingest(path: Path) -> None:
            calls.append(path)
            if path.name == "middle.md":
                raise RuntimeError("simulated ingest failure")

        gardener._ingest_one = fake_ingest  # type: ignore[method-assign]
        stats = await gardener.run()

        assert len(calls) == 3
        assert stats.ingested == 2
        assert stats.failed == 1
