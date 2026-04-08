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
