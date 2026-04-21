"""BDD tests for knowledge domain public API functions."""

from unittest.mock import patch

from shared.testing.markers import covers_public

import knowledge


class TestPublicFunctions:
    @covers_public("knowledge.search_notes")
    def test_search_notes_returns_results(self, session):
        from shared.testing.plugin import deterministic_embedding

        embedding = deterministic_embedding("test query")
        result = knowledge.search_notes(session, query_embedding=embedding)
        assert isinstance(result, list)

    @covers_public("knowledge.get_store")
    def test_get_store_returns_store_instance(self, session):
        store = knowledge.get_store(session)
        assert store is not None
        assert hasattr(store, "search_notes_with_context")

    @covers_public("knowledge.get_embedding_client")
    def test_get_embedding_client_returns_client(self):
        with patch("shared.embedding.EmbeddingClient") as mock_cls:
            client = knowledge.get_embedding_client()
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value
