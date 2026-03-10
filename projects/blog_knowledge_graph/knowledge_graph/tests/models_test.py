"""Tests for shared models and content_hash."""

from projects.blog_knowledge_graph.knowledge_graph.app.models import content_hash


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_content_different_hash(self):
        assert content_hash("hello") != content_hash("world")

    def test_returns_hex_string(self):
        h = content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_string(self):
        h = content_hash("")
        assert len(h) == 64
