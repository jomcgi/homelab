"""Tests for move_phase() OSError on file read.

raw_ingest.py move_phase() catches OSError when read_text() fails and
continues to the next file (lines 69-73):

    try:
        content = source.read_text(encoding="utf-8")
    except OSError as read_err:
        logger.warning("move_phase: failed to read %s: %s", source, read_err)
        continue

This branch is not covered by any existing test file — raw_ingest_test.py
only exercises the happy paths.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from knowledge.raw_ingest import MovePhaseStats, move_phase


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


_NOW = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)


class TestMovePhaseOSError:
    """move_phase() silently skips files that fail to read with OSError."""

    def test_oserror_on_read_skips_file_and_logs_warning(self, tmp_path, caplog):
        """A file that raises OSError during read_text is skipped with a warning."""
        _write(tmp_path / "inbox" / "bad.md", "---\ntitle: Bad\n---\nContent.")

        original_read_text = Path.read_text

        def raise_for_bad(p: Path, *args, **kwargs) -> str:
            if p.name == "bad.md":
                raise OSError("permission denied")
            return original_read_text(p, *args, **kwargs)

        with (
            patch.object(Path, "read_text", raise_for_bad),
            caplog.at_level(logging.WARNING, logger="monolith.knowledge.raw_ingest"),
        ):
            stats = move_phase(vault_root=tmp_path, now=_NOW)

        # The unreadable file was not moved.
        assert stats.moved == 0
        assert stats.deduped == 0
        # A warning was emitted for the bad file.
        assert any(
            "move_phase" in r.message and "failed" in r.message for r in caplog.records
        )

    def test_oserror_skipped_file_does_not_count_as_moved(self, tmp_path):
        """An OSError'd file increments neither moved nor deduped."""
        _write(tmp_path / "inbox" / "bad.md", "Body.")

        original_read_text = Path.read_text

        def always_raise(p: Path, *args, **kwargs) -> str:
            raise OSError("disk error")

        with patch.object(Path, "read_text", always_raise):
            stats = move_phase(vault_root=tmp_path, now=_NOW)

        assert isinstance(stats, MovePhaseStats)
        assert stats.moved == 0
        assert stats.deduped == 0

    def test_good_file_moved_despite_bad_file_oserror(self, tmp_path):
        """move_phase continues processing after an OSError — good files are moved."""
        # Sorted order: a_bad.md comes before b_good.md
        _write(tmp_path / "inbox" / "a_bad.md", "---\ntitle: Bad\n---\nBad body.")
        _write(tmp_path / "inbox" / "b_good.md", "---\ntitle: Good\n---\nGood body.")

        original_read_text = Path.read_text

        def raise_for_bad(p: Path, *args, **kwargs) -> str:
            if p.name == "a_bad.md":
                raise OSError("permission denied")
            return original_read_text(p, *args, **kwargs)

        with patch.object(Path, "read_text", raise_for_bad):
            stats = move_phase(vault_root=tmp_path, now=_NOW)

        # Good file was moved; bad file was skipped.
        assert stats.moved == 1
        assert stats.deduped == 0
        # The good file has been relocated to _raw/.
        assert not (tmp_path / "inbox" / "b_good.md").exists()
        raw_files = list((tmp_path / "_raw").rglob("*.md"))
        assert len(raw_files) == 1

    def test_oserror_message_includes_file_path(self, tmp_path, caplog):
        """The warning message includes the path of the unreadable file."""
        bad_file = tmp_path / "inbox" / "secret.md"
        _write(bad_file, "---\ntitle: Secret\n---\nPrivate.")

        original_read_text = Path.read_text

        def raise_for_bad(p: Path, *args, **kwargs) -> str:
            if p.name == "secret.md":
                raise OSError("access denied")
            return original_read_text(p, *args, **kwargs)

        with (
            patch.object(Path, "read_text", raise_for_bad),
            caplog.at_level(logging.WARNING, logger="monolith.knowledge.raw_ingest"),
        ):
            move_phase(vault_root=tmp_path, now=_NOW)

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        # At least one warning should mention the file path.
        assert any("secret.md" in msg for msg in warning_messages)
