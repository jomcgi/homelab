"""Tests for token-efficient output formatting."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.cli.output import compact_line, format_edges, search_line, write_to_tmpfile


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
        with patch("tools.cli.output.TMPDIR", tmp_path):
            path = write_to_tmpfile("my-note", "# Hello\nWorld")
            assert path.exists()
            assert path.read_text() == "# Hello\nWorld"
            assert "my-note" in path.name

    def test_overwrites_existing(self, tmp_path):
        with patch("tools.cli.output.TMPDIR", tmp_path):
            write_to_tmpfile("note", "v1")
            path = write_to_tmpfile("note", "v2")
            assert path.read_text() == "v2"


class TestSearchLine:
    def test_basic_format_no_edges(self):
        """Score, note_id, title, and type are all present in the output line."""
        result = search_line(0.95, "n1", "Attention Is All You Need", "paper", [])
        assert result == "[0.95] n1 — Attention Is All You Need (paper)"

    def test_score_formatted_to_two_decimal_places(self):
        """Score is always rendered with exactly two decimal places."""
        result = search_line(1.0, "n2", "Some Note", "concept", [])
        assert result.startswith("[1.00]")

    def test_with_typed_edges_appends_edge_line(self):
        """Typed edges are appended as an indented second line."""
        edges = [
            {"kind": "edge", "edge_type": "derives_from", "target_id": "note-a"},
            {"kind": "edge", "edge_type": "related", "target_id": "note-b"},
        ]
        result = search_line(0.80, "n3", "My Note", "note", edges)
        lines = result.splitlines()
        assert len(lines) == 2
        assert lines[0] == "[0.80] n3 — My Note (note)"
        assert "derives_from→note-a" in lines[1]
        assert "related→note-b" in lines[1]

    def test_link_kind_edges_excluded(self):
        """Edges with kind='link' (not 'edge') are filtered out and not shown."""
        edges = [
            {"kind": "link", "edge_type": None, "target_id": "other-note"},
        ]
        result = search_line(0.70, "n4", "Link Note", "note", edges)
        # No edge line appended for plain wikilinks
        assert "\n" not in result
