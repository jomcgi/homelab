"""Additional coverage tests for knowledge/links.py.

Fills gaps identified in the coverage review:
- Anchor-only links ([[#section]], [[^block]]) have an empty target after
  stripping and are silently skipped.
- Display text stripped to "" — [[Note|  ]] yields display="" instead of None.
- Compound anchors ([[Note#section^block]]) work correctly.
"""

from __future__ import annotations

from knowledge.links import Link, extract


class TestAnchorOnlyLinks:
    def test_heading_anchor_only_is_skipped(self):
        """[[#section]] — the target before '#' is '' so the link is dropped."""
        result = extract("See [[#section]].")
        assert result == []

    def test_block_anchor_only_is_skipped(self):
        """[[^block-id]] — the target before '^' is '' so the link is dropped."""
        result = extract("See [[^block-id]].")
        assert result == []

    def test_anchor_only_does_not_prevent_other_links(self):
        """Anchor-only links are skipped without affecting subsequent valid links."""
        result = extract("See [[#heading]] and also [[ValidNote]].")
        assert result == [Link(target="ValidNote", display=None)]

    def test_block_anchor_only_does_not_prevent_other_links(self):
        """[[^block]] skip does not affect other links in the same body."""
        result = extract("[[^abc]] and [[AnotherNote]].")
        assert result == [Link(target="AnotherNote", display=None)]


class TestWhitespaceOnlyDisplayText:
    def test_whitespace_only_display_stripped_to_empty_string(self):
        """[[Note|  ]] yields display='' (stripped whitespace), not None.

        The regex captures a whitespace-only display group; strip() then
        produces '' which is falsy but not None. The current implementation
        passes the stripped result (even if '') rather than converting it to
        None. This test pins that contract.
        """
        result = extract("[[Note|  ]]")
        assert len(result) == 1
        assert result[0].target == "Note"
        # The display is '' (stripped whitespace), not None
        assert result[0].display == ""

    def test_normal_display_text_preserved(self):
        """A non-whitespace display text is stripped and preserved."""
        result = extract("[[Note| the note ]]")
        assert len(result) == 1
        assert result[0].target == "Note"
        assert result[0].display == "the note"


class TestCompoundAnchors:
    def test_note_hash_section_caret_block_resolves_to_note(self):
        """[[Note#section^block]] strips both anchors and resolves to 'Note'."""
        result = extract("See [[Note#section^block]].")
        assert result == [Link(target="Note", display=None)]

    def test_note_with_only_hash_section_resolves_to_note(self):
        """[[Note#section]] resolves to the note name alone."""
        result = extract("See [[Note#section]].")
        assert result == [Link(target="Note", display=None)]

    def test_note_with_only_caret_block_resolves_to_note(self):
        """[[Note^block-id]] resolves to the note name alone."""
        result = extract("See [[Note^block-id]].")
        assert result == [Link(target="Note", display=None)]

    def test_compound_anchor_with_display_text(self):
        """[[Note#section|label]] — display is kept and target is stripped to note."""
        result = extract("[[Note#section|see here]]")
        assert len(result) == 1
        assert result[0].target == "Note"
        assert result[0].display == "see here"

    def test_compound_anchor_deduplicated_by_resolved_target(self):
        """Two links that resolve to the same note are deduplicated."""
        body = "[[Note#intro]] and [[Note#conclusion]]"
        result = extract(body)
        assert len(result) == 1
        assert result[0].target == "Note"
