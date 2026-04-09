"""Tests for wikilink extraction."""

from knowledge.links import Link, extract


class TestExtract:
    def test_empty_body(self):
        assert extract("") == []

    def test_simple_link(self):
        assert extract("See [[Foo]].") == [Link(target="Foo", display=None)]

    def test_link_with_display(self):
        assert extract("See [[Foo|the foo]].") == [
            Link(target="Foo", display="the foo")
        ]

    def test_dedupe_preserves_first_order(self):
        body = "[[A]] then [[B]] then [[A]]"
        assert [link.target for link in extract(body)] == ["A", "B"]

    def test_fenced_code_block_excluded(self):
        body = "Intro [[Real]]\n\n```\n[[Fake]]\n```\n\nOutro [[AlsoReal]]"
        assert [link.target for link in extract(body)] == ["Real", "AlsoReal"]

    def test_inline_code_excluded(self):
        body = "Real [[A]] but `[[B]]` is code."
        assert [link.target for link in extract(body)] == ["A"]

    def test_unterminated_link_ignored(self):
        body = "[[unterminated and [[Real]]"
        assert [link.target for link in extract(body)] == ["Real"]

    def test_heading_link_extracts_note_name(self):
        """[[note#heading]] links to the note, not the heading anchor.

        Obsidian's [[Note#Heading]] syntax points at a section within a note.
        The graph edge should resolve to the note itself so target_id matches
        the note's note_id, not an ephemeral section anchor.
        """
        assert extract("See [[note#heading]].") == [Link(target="note", display=None)]

    def test_block_reference_extracts_note_name(self):
        """[[note^block-id]] links to the note, not the block reference.

        Obsidian's [[Note^block-id]] syntax points at a specific block inside a
        note. Like heading links, only the note name is relevant for graph edges.
        """
        assert extract("See [[note^block-id]].") == [Link(target="note", display=None)]

    def test_multiple_wikilinks_on_same_line(self):
        """All wikilinks on the same line are extracted left-to-right."""
        body = "See [[Alpha]] and [[Beta]] and [[Gamma]] on one line."
        assert [link.target for link in extract(body)] == ["Alpha", "Beta", "Gamma"]

    def test_anchor_only_link_is_skipped(self):
        """[[#heading]] with no note name produces no Link.

        After stripping the anchor the target becomes an empty string, which
        the extractor silently drops. An anchor-only link cannot resolve to a
        note_id, so it must not appear in the output.
        """
        assert extract("See [[#Introduction]].") == []

    def test_anchor_only_link_among_valid_links(self):
        """[[#heading]] is filtered out while normal links around it survive."""
        body = "[[RealNote]] and [[#section]] and [[AnotherNote]]"
        assert [link.target for link in extract(body)] == ["RealNote", "AnotherNote"]

    def test_heading_anchor_with_display_text(self):
        """[[note#heading|Display]] strips the anchor but keeps the display text."""
        result = extract("See [[Design Notes#Summary|summary section]].")
        assert result == [Link(target="Design Notes", display="summary section")]

    def test_block_ref_with_display_text(self):
        """[[note^block|Display]] strips the block ref but keeps the display text."""
        result = extract("See [[My Note^abc123|that block]].")
        assert result == [Link(target="My Note", display="that block")]

    def test_display_text_without_anchor(self):
        """[[note|Display]] with no anchor already worked; this pins the behaviour."""
        result = extract("See [[Project Plan|the plan]].")
        assert result == [Link(target="Project Plan", display="the plan")]
