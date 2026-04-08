"""Tests for lenient frontmatter parsing."""

from datetime import datetime, timezone

from knowledge.frontmatter import ParsedFrontmatter, parse


class TestParse:
    def test_no_frontmatter_returns_empty_metadata_and_full_body(self):
        meta, body = parse("Just a body.")
        assert meta == ParsedFrontmatter()
        assert body == "Just a body."

    def test_well_formed_frontmatter(self):
        raw = (
            "---\n"
            "title: Attention Is All You Need\n"
            "type: paper\n"
            "tags: [ml, attention]\n"
            "created: 2017-06-12\n"
            "---\n"
            "Body text."
        )
        meta, body = parse(raw)
        assert meta.title == "Attention Is All You Need"
        assert meta.type == "paper"
        assert meta.tags == ["ml", "attention"]
        assert meta.created == datetime(2017, 6, 12, tzinfo=timezone.utc)
        assert body == "Body text."

    def test_tags_as_comma_string(self):
        raw = "---\ntags: ml, attention,  transformers\n---\nx"
        meta, _ = parse(raw)
        assert meta.tags == ["ml", "attention", "transformers"]

    def test_tags_as_space_string(self):
        raw = "---\ntags: ml attention transformers\n---\nx"
        meta, _ = parse(raw)
        assert meta.tags == ["ml", "attention", "transformers"]

    def test_aliases_same_rules_as_tags(self):
        raw = "---\naliases: [Foo, Bar]\n---\nx"
        meta, _ = parse(raw)
        assert meta.aliases == ["Foo", "Bar"]

    def test_invalid_yaml_returns_empty_metadata_and_full_body(self):
        raw = "---\ntitle: [unterminated\n---\nBody text."
        meta, body = parse(raw)
        assert meta == ParsedFrontmatter()
        assert body == raw  # full original content, no body stripping

    def test_invalid_date_yields_none(self):
        raw = "---\ncreated: not-a-date\n---\nx"
        meta, _ = parse(raw)
        assert meta.created is None

    def test_unknown_keys_land_in_extra(self):
        raw = "---\ntitle: T\nauthor: Karpathy\nyear: 2017\n---\nx"
        meta, _ = parse(raw)
        assert meta.title == "T"
        assert meta.extra == {"author": "Karpathy", "year": 2017}

    def test_promoted_keys_never_appear_in_extra(self):
        raw = "---\ntype: paper\nstatus: published\nauthor: K\n---\nx"
        meta, _ = parse(raw)
        assert "type" not in meta.extra
        assert "status" not in meta.extra
        assert meta.extra == {"author": "K"}

    def test_delimiter_not_at_top_is_not_frontmatter(self):
        raw = "Body first.\n\n---\ntitle: T\n---\nMore body."
        meta, body = parse(raw)
        assert meta == ParsedFrontmatter()
        assert body == raw

    def test_id_captured_verbatim(self):
        raw = "---\nid: attention-is-all-you-need\n---\nx"
        meta, _ = parse(raw)
        assert meta.note_id == "attention-is-all-you-need"

    def test_id_missing_returns_none(self):
        raw = "---\ntitle: T\n---\nx"
        meta, _ = parse(raw)
        assert meta.note_id is None

    def test_edges_block_parsed(self):
        raw = (
            "---\n"
            "edges:\n"
            "  refines: [parent-note]\n"
            "  related: [a, b]\n"
            "  contradicts: []\n"
            "---\n"
            "x"
        )
        meta, _ = parse(raw)
        assert meta.edges == {
            "refines": ["parent-note"],
            "related": ["a", "b"],
            # Empty lists are dropped at the parser level.
        }

    def test_edges_unknown_key_dropped_with_warning(self, caplog):
        raw = "---\nedges:\n  refutes: [x]\n  refines: [y]\n---\nz"
        meta, _ = parse(raw)
        assert meta.edges == {"refines": ["y"]}
        assert any("unknown edge type" in r.message for r in caplog.records)

    def test_edges_block_missing_returns_empty_dict(self):
        raw = "---\ntitle: T\n---\nx"
        meta, _ = parse(raw)
        assert meta.edges == {}

    def test_up_key_is_no_longer_recognized(self):
        # `up:` was removed in favor of `edges.refines`. A one-shot vault
        # migration script (out of scope) rewrites legacy `up:` keys.
        # Until then, the parser ignores `up:` and lets it land in `extra`.
        raw = "---\nup: '[[Index]]'\n---\nx"
        meta, _ = parse(raw)
        assert meta.extra == {"up": "[[Index]]"}
