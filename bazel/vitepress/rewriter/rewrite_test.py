"""Tests for the VitePress link rewriter.

Covers resolve_link, remap_link, rewrite_file, and the LINK_PATTERN regex.
"""

import os
import tempfile
from pathlib import Path

import pytest

from bazel.vitepress.rewriter.rewrite import (
    LINK_PATTERN,
    remap_link,
    resolve_link,
    rewrite_file,
)


# ---------------------------------------------------------------------------
# resolve_link
# ---------------------------------------------------------------------------


class TestResolveLink:
    def test_http_skipped(self):
        assert resolve_link("http://example.com", "docs") is None

    def test_https_skipped(self):
        assert resolve_link("https://example.com/foo", "docs") is None

    def test_mailto_skipped(self):
        assert resolve_link("mailto:foo@bar.com", "docs") is None

    def test_anchor_only_skipped(self):
        assert resolve_link("#section", "docs") is None

    def test_anchor_hash_only_skipped(self):
        # Link target that is just "#" with nothing after
        assert resolve_link("#", "docs") is None

    def test_simple_relative(self):
        result = resolve_link("README.md", "docs/services")
        assert result == "docs/services/README.md"

    def test_parent_relative(self):
        result = resolve_link("../other/README.md", "docs/services")
        assert result == "docs/other/README.md"

    def test_nested_parent(self):
        result = resolve_link("../../root.md", "a/b/c")
        assert result == "a/root.md"

    def test_anchor_stripped_for_resolution(self):
        # The anchor fragment must not affect the resolved path
        result = resolve_link("../README.md#section", "docs/services")
        assert result == "docs/README.md"

    def test_from_root_dir(self):
        result = resolve_link("README.md", "")
        assert result == "README.md"

    def test_removes_leading_dotslash(self):
        result = resolve_link("./foo.md", "")
        assert result == "foo.md"

    def test_forward_slashes_normalised(self):
        result = resolve_link("sub/file.md", "a/b")
        assert "\\" not in result
        assert "/" in result

    def test_same_dir_link(self):
        result = resolve_link("other.md", "docs")
        assert result == "docs/other.md"

    def test_deep_relative(self):
        result = resolve_link("foo/bar/baz.md", "root")
        assert result == "root/foo/bar/baz.md"


# ---------------------------------------------------------------------------
# remap_link
# ---------------------------------------------------------------------------


class TestRemapLink:
    def test_exact_match(self):
        path_map = {"docs/README.md": "guide/intro.md"}
        assert remap_link("docs/README.md", path_map) == "guide/intro.md"

    def test_prefix_match_with_remainder(self):
        path_map = {"docs/services": "guide/services"}
        result = remap_link("docs/services/ships.md", path_map)
        assert result == "guide/services/ships.md"

    def test_longest_prefix_wins(self):
        path_map = {
            "docs": "base",
            "docs/services": "guide/services",
        }
        result = remap_link("docs/services/ships.md", path_map)
        assert result == "guide/services/ships.md"

    def test_shorter_prefix_used_when_no_longer_match(self):
        path_map = {"docs": "base"}
        result = remap_link("docs/README.md", path_map)
        assert result == "base/README.md"

    def test_no_match_returns_none(self):
        path_map = {"other/path": "mapped"}
        assert remap_link("docs/README.md", path_map) is None

    def test_empty_path_map_returns_none(self):
        assert remap_link("docs/README.md", {}) is None

    def test_exact_match_no_remainder(self):
        path_map = {"docs/guide": "guide"}
        assert remap_link("docs/guide", path_map) == "guide"

    def test_single_component_path(self):
        path_map = {"README.md": "intro.md"}
        assert remap_link("README.md", path_map) == "intro.md"

    def test_deeply_nested_prefix(self):
        path_map = {"a/b/c": "x/y/z"}
        result = remap_link("a/b/c/d/e.md", path_map)
        assert result == "x/y/z/d/e.md"


# ---------------------------------------------------------------------------
# rewrite_file
# ---------------------------------------------------------------------------


class TestRewriteFile:
    def test_external_http_link_unchanged(self):
        content = "See [example](https://example.com) for details."
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert result == content
        assert warnings == []

    def test_external_http_link_with_path_unchanged(self):
        content = "Visit [docs](http://docs.example.com/guide) here."
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert result == content
        assert warnings == []

    def test_anchor_only_link_unchanged(self):
        content = "Jump to [section](#heading)."
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert result == content
        assert warnings == []

    def test_image_not_processed(self):
        # Images use ![...](url) — must NOT be rewritten
        content = "![alt text](images/foo.png)"
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert result == content
        assert warnings == []

    def test_link_not_in_pathmap_stripped(self):
        content = "See [Service](../services/README.md) for details."
        result, warnings = rewrite_file(content, "docs/guide", {}, "/tmp")
        # Markup removed, display text preserved
        assert "[Service](../services/README.md)" not in result
        assert "Service" in result
        assert len(warnings) == 1
        assert "stripped" in warnings[0]

    def test_link_not_found_in_assembled_tree_stripped(self):
        path_map = {"docs/services/README.md": "guide/services.md"}
        content = "See [Services](README.md)."
        with tempfile.TemporaryDirectory() as tmpdir:
            # Target file does NOT exist
            result, warnings = rewrite_file(content, "docs/services", path_map, tmpdir)
        assert "[Services](README.md)" not in result
        assert "Services" in result
        assert len(warnings) == 1
        assert "stripped" in warnings[0]

    def test_valid_link_rewritten_to_absolute(self):
        path_map = {"docs/services/README.md": "guide/services.md"}
        content = "See [Services](README.md)."
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "guide" / "services.md"
            target.parent.mkdir(parents=True)
            target.write_text("content")
            result, warnings = rewrite_file(content, "docs/services", path_map, tmpdir)
        assert result == "See [Services](/guide/services.md)."
        assert warnings == []

    def test_anchor_preserved_on_rewritten_link(self):
        path_map = {"docs/README.md": "guide/intro.md"}
        content = "See [Intro](README.md#setup)."
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "guide" / "intro.md"
            target.parent.mkdir(parents=True)
            target.write_text("content")
            result, warnings = rewrite_file(content, "docs", path_map, tmpdir)
        assert result == "See [Intro](/guide/intro.md#setup)."
        assert warnings == []

    def test_multiple_valid_links_all_rewritten(self):
        path_map = {"docs/a.md": "guide/a.md", "docs/b.md": "guide/b.md"}
        content = "[A](a.md) and [B](b.md) and [ext](https://x.com)."
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("a.md", "b.md"):
                p = Path(tmpdir) / "guide" / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("content")
            result, warnings = rewrite_file(content, "docs", path_map, tmpdir)
        assert "[A](/guide/a.md)" in result
        assert "[B](/guide/b.md)" in result
        assert "[ext](https://x.com)" in result
        assert warnings == []

    def test_multiple_warnings_accumulated(self):
        content = "[A](a.md) and [B](b.md)."
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert len(warnings) == 2
        # Display text kept for both
        assert "A" in result
        assert "B" in result

    def test_empty_content(self):
        result, warnings = rewrite_file("", "docs", {}, "/tmp")
        assert result == ""
        assert warnings == []

    def test_content_without_links(self):
        content = "# Title\n\nSome text without any links.\n"
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert result == content
        assert warnings == []

    def test_mixed_internal_and_external_links(self):
        # External stays unchanged; internal with no mapping gets stripped
        content = "[ext](https://example.com) and [int](local.md)."
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        assert "[ext](https://example.com)" in result
        assert "[int](local.md)" not in result
        assert "int" in result
        assert len(warnings) == 1

    def test_link_with_empty_display_text(self):
        # Edge case: [](url) — display text is empty
        path_map = {}
        content = "[](page.md)"
        result, warnings = rewrite_file(content, "docs", {}, "/tmp")
        # No mapping → stripped; empty display text → empty string
        assert "[](page.md)" not in result
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# LINK_PATTERN regex
# ---------------------------------------------------------------------------


class TestLinkPattern:
    def test_matches_regular_link(self):
        m = LINK_PATTERN.search("[text](url)")
        assert m is not None
        assert m.group(1) == "text"
        assert m.group(2) == "url"

    def test_does_not_match_image(self):
        # Images have ! before [
        m = LINK_PATTERN.search("![alt](url)")
        assert m is None

    def test_matches_link_after_image_on_same_line(self):
        # Only the link (not the image) should be captured
        text = "![img](img.png) [link](page.md)"
        matches = LINK_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0] == ("link", "page.md")

    def test_empty_display_text_matched(self):
        m = LINK_PATTERN.search("[](url)")
        assert m is not None

    def test_link_with_anchor(self):
        m = LINK_PATTERN.search("[text](page.md#section)")
        assert m is not None
        assert m.group(2) == "page.md#section"

    def test_multiple_links_found(self):
        text = "[a](url1) and [b](url2)"
        matches = LINK_PATTERN.findall(text)
        assert len(matches) == 2
        assert matches[0] == ("a", "url1")
        assert matches[1] == ("b", "url2")

    def test_external_url_matched_by_pattern(self):
        # Pattern matches; resolve_link skips it — but pattern itself matches
        m = LINK_PATTERN.search("[text](https://example.com)")
        assert m is not None
        assert m.group(2) == "https://example.com"
