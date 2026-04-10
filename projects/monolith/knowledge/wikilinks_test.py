"""Tests for the wikilinks Links section generator."""

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.wikilinks import render_links_section, sync_links


def _meta(**kwargs) -> ParsedFrontmatter:
    m = ParsedFrontmatter()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


class TestRenderLinksSection:
    def test_derives_from_produces_up(self):
        meta = _meta(edges={"derives_from": ["book-field-guide"]})
        section = render_links_section(meta)
        assert (
            section
            == "\n## Links\n\nUp: [[_processed/book-field-guide|book-field-guide]]\n"
        )

    def test_refines_used_as_up_when_no_derives_from(self):
        meta = _meta(edges={"refines": ["parent-note"]})
        section = render_links_section(meta)
        assert "Up: [[_processed/parent-note|parent-note]]" in section

    def test_derives_from_takes_priority_over_refines(self):
        meta = _meta(edges={"derives_from": ["source"], "refines": ["parent"]})
        section = render_links_section(meta)
        assert "Up: [[_processed/source|source]]" in section
        assert "refines" not in section
        assert "parent" not in section

    def test_type_hub_fallback_when_no_up_edges(self):
        meta = _meta(type="feedback", edges={"related": ["other"]})
        section = render_links_section(meta)
        assert "Up: [[feedback]]" in section

    def test_type_hub_when_no_edges_at_all(self):
        meta = _meta(type="project")
        section = render_links_section(meta)
        assert section == "\n## Links\n\nUp: [[project]]\n"

    def test_none_when_no_edges_and_no_type(self):
        meta = _meta()
        assert render_links_section(meta) is None

    def test_related_rendered_as_bullets(self):
        meta = _meta(edges={"related": ["note-a", "note-b"]})
        section = render_links_section(meta)
        assert (
            "Related:\n- [[_processed/note-a|note-a]]\n- [[_processed/note-b|note-b]]"
            in section
        )

    def test_all_labelled_edge_types(self):
        meta = _meta(
            edges={
                "derives_from": ["source"],
                "related": ["r"],
                "generalizes": ["g"],
                "contradicts": ["c"],
                "supersedes": ["s"],
            }
        )
        section = render_links_section(meta)
        assert "Up:" in section
        assert "Related:" in section
        assert "Generalizes:" in section
        assert "Contradicts:" in section
        assert "Supersedes:" in section

    def test_multiple_derives_from_targets(self):
        meta = _meta(edges={"derives_from": ["source-a", "source-b"]})
        section = render_links_section(meta)
        assert "Up: [[_processed/source-a|source-a]]" in section
        assert "Up: [[_processed/source-b|source-b]]" in section


class TestSyncLinks:
    def test_appends_section_when_missing(self):
        raw = "---\nid: test\ntype: atom\n---\n\nSome content.\n"
        meta = _meta(type="atom")
        result = sync_links(raw, meta)
        assert result is not None
        assert "## Links" in result
        assert "Up: [[atom]]" in result

    def test_returns_none_when_already_current(self):
        meta = _meta(type="atom")
        raw = "---\nid: test\ntype: atom\n---\n\nSome content.\n\n## Links\n\nUp: [[atom]]\n"
        assert sync_links(raw, meta) is None

    def test_updates_stale_section(self):
        # Edges changed — old Related list is now wrong
        raw = "---\nid: test\n---\n\nContent.\n\n## Links\n\nUp: [[old-parent|old-parent]]\n"
        meta = _meta(edges={"derives_from": ["new-parent"]})
        result = sync_links(raw, meta)
        assert result is not None
        assert "new-parent" in result
        assert "old-parent" not in result

    def test_strips_entire_old_section(self):
        raw = (
            "---\nid: x\n---\n\nBody.\n\n## Links\n\nUp: [[a|a]]\nRelated:\n- [[b|b]]\n"
        )
        meta = _meta(edges={"derives_from": ["c"]})
        result = sync_links(raw, meta)
        assert result is not None
        assert "[[a|a]]" not in result
        assert "[[b|b]]" not in result

    def test_no_section_and_no_edges_returns_none(self):
        raw = "---\nid: x\n---\n\nBody.\n"
        meta = _meta()
        assert sync_links(raw, meta) is None

    def test_idempotent(self):
        meta = _meta(edges={"derives_from": ["src"], "related": ["rel"]})
        raw = "---\nid: x\n---\n\nContent.\n"
        first = sync_links(raw, meta)
        assert first is not None
        assert sync_links(first, meta) is None
