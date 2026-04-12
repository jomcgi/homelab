"""Tests for token-efficient output formatting."""

from pathlib import Path
from unittest.mock import patch

from output import compact_line, write_to_tmpfile, format_edges


class TestCompactLine:
    def test_basic_format(self):
        result = compact_line(42, "some/path.md", "obsidian", "bad JSON", 3)
        assert result == "[42] some/path.md (obsidian) — bad JSON [3 retries]"

    def test_no_error(self):
        result = compact_line(1, "path.md", "youtube", None, 0)
        assert result == "[1] path.md (youtube)"


class TestFormatEdges:
    def test_typed_edges(self):
        edges = [
            {"kind": "edge", "edge_type": "derives_from", "target_id": "note-a"},
            {"kind": "edge", "edge_type": "related", "target_id": "note-b"},
        ]
        result = format_edges(edges)
        assert result == "derives_from→note-a, related→note-b"

    def test_empty(self):
        assert format_edges([]) == ""


class TestWriteToTmpfile:
    def test_writes_content_and_returns_path(self, tmp_path):
        with patch("output.TMPDIR", tmp_path):
            path = write_to_tmpfile("my-note", "# Hello\nWorld")
            assert path.exists()
            assert path.read_text() == "# Hello\nWorld"
            assert "my-note" in path.name

    def test_overwrites_existing(self, tmp_path):
        with patch("output.TMPDIR", tmp_path):
            write_to_tmpfile("note", "v1")
            path = write_to_tmpfile("note", "v2")
            assert path.read_text() == "v2"
