"""Tests for embedder implementations: Embedder protocol, GeminiEmbedder, OllamaEmbedder."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.embedders.base import Embedder
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini import (
    GeminiEmbedder,
)
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama import (
    OllamaEmbedder,
)


# ---------------------------------------------------------------------------
# Embedder Protocol (base.py)
# ---------------------------------------------------------------------------


class TestEmbedderProtocol:
    def test_valid_implementation_satisfies_protocol(self):
        """A class with embed() and dimension satisfies the Embedder protocol."""

        class MyEmbedder:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.1] * 768 for _ in texts]

            @property
            def dimension(self) -> int:
                return 768

        assert isinstance(MyEmbedder(), Embedder)

    def test_missing_embed_method_fails_protocol(self):
        """A class without embed() does not satisfy the Embedder protocol."""

        class NoEmbed:
            @property
            def dimension(self) -> int:
                return 768

        assert not isinstance(NoEmbed(), Embedder)

    def test_missing_dimension_fails_protocol(self):
        """A class without dimension property does not satisfy the Embedder protocol."""

        class NoDimension:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.1]]

        assert not isinstance(NoDimension(), Embedder)

    def test_gemini_embedder_satisfies_protocol(self):
        embedder = GeminiEmbedder(api_key="test-key")
        assert isinstance(embedder, Embedder)

    def test_ollama_embedder_satisfies_protocol(self):
        embedder = OllamaEmbedder()
        assert isinstance(embedder, Embedder)


# ---------------------------------------------------------------------------
# GeminiEmbedder (gemini.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def gemini():
    return GeminiEmbedder(api_key="test-api-key", model="gemini-embedding-001")


class TestGeminiEmbedderDimension:
    def test_dimension_is_768(self, gemini):
        assert gemini.dimension == 768


class TestGeminiEmbedderEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self, gemini):
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "embeddings": [{"values": v} for v in vectors]
            }
            mock_client.post.return_value = mock_response

            result = await gemini.embed(["hello world", "foo bar"])

        assert result == vectors

    @pytest.mark.asyncio
    async def test_embed_sends_to_batch_endpoint(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [{"values": [0.1]}]}
            mock_client.post.return_value = mock_response

            await gemini.embed(["text"])

        call_args = mock_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.args[0]
        assert "batchEmbedContents" in url

    @pytest.mark.asyncio
    async def test_embed_sends_api_key_as_param(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [{"values": [0.1]}]}
            mock_client.post.return_value = mock_response

            await gemini.embed(["text"])

        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs.get("params", {}).get("key") == "test-api-key"

    @pytest.mark.asyncio
    async def test_embed_uses_retrieval_document_task_type(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [{"values": [0.1]}]}
            mock_client.post.return_value = mock_response

            await gemini.embed(["text"])

        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"

    @pytest.mark.asyncio
    async def test_embed_empty_list_returns_empty(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": []}
            mock_client.post.return_value = mock_response

            result = await gemini.embed([])

        assert result == []

    @pytest.mark.asyncio
    async def test_embed_raises_on_http_error(self, gemini):
        import httpx

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock()
            )
            mock_client.post.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await gemini.embed(["text"])

    @pytest.mark.asyncio
    async def test_embed_includes_model_in_request(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [{"values": [0.1]}]}
            mock_client.post.return_value = mock_response

            await gemini.embed(["text"])

        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["requests"][0]["model"] == "models/gemini-embedding-001"


class TestGeminiEmbedderEmbedQuery:
    @pytest.mark.asyncio
    async def test_embed_query_returns_vector(self, gemini):
        expected = [0.9, 0.8, 0.7]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embedding": {"values": expected}}
            mock_client.post.return_value = mock_response

            result = await gemini.embed_query("search query")

        assert result == expected

    @pytest.mark.asyncio
    async def test_embed_query_uses_retrieval_query_task_type(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embedding": {"values": [0.1]}}
            mock_client.post.return_value = mock_response

            await gemini.embed_query("some query")

        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["taskType"] == "RETRIEVAL_QUERY"

    @pytest.mark.asyncio
    async def test_embed_query_sends_to_embedcontent_endpoint(self, gemini):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embedding": {"values": [0.1]}}
            mock_client.post.return_value = mock_response

            await gemini.embed_query("query")

        url = mock_client.post.call_args.args[0]
        assert "embedContent" in url

    @pytest.mark.asyncio
    async def test_embed_query_raises_on_http_error(self, gemini):
        import httpx

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock()
            )
            mock_client.post.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await gemini.embed_query("query")


# ---------------------------------------------------------------------------
# OllamaEmbedder (ollama.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def ollama():
    return OllamaEmbedder(url="http://localhost:11434", model="nomic-embed-text")


class TestOllamaEmbedderInit:
    def test_strips_trailing_slash_from_url(self):
        embedder = OllamaEmbedder(
            url="http://localhost:11434/", model="nomic-embed-text"
        )
        assert not embedder._url.endswith("/")

    def test_url_without_slash_unchanged(self):
        embedder = OllamaEmbedder(
            url="http://localhost:11434", model="nomic-embed-text"
        )
        assert embedder._url == "http://localhost:11434"

    def test_default_url(self):
        embedder = OllamaEmbedder()
        assert embedder._url == "http://localhost:11434"

    def test_default_model(self):
        embedder = OllamaEmbedder()
        assert embedder._model == "nomic-embed-text"


class TestOllamaEmbedderDimension:
    def test_dimension_is_768(self, ollama):
        assert ollama.dimension == 768


class TestOllamaEmbedderEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self, ollama):
        expected = [[0.1, 0.2], [0.3, 0.4]]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": expected}
            mock_client.post.return_value = mock_response

            result = await ollama.embed(["hello", "world"])

        assert result == expected

    @pytest.mark.asyncio
    async def test_embed_adds_search_document_prefix(self, ollama):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [[0.1], [0.2]]}
            mock_client.post.return_value = mock_response

            await ollama.embed(["first text", "second text"])

        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["input"] == [
            "search_document: first text",
            "search_document: second text",
        ]

    @pytest.mark.asyncio
    async def test_embed_sends_to_api_embed_endpoint(self, ollama):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [[0.1]]}
            mock_client.post.return_value = mock_response

            await ollama.embed(["text"])

        url = mock_client.post.call_args.args[0]
        assert url.endswith("/api/embed")

    @pytest.mark.asyncio
    async def test_embed_sends_model_name(self, ollama):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [[0.1]]}
            mock_client.post.return_value = mock_response

            await ollama.embed(["text"])

        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["model"] == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_embed_raises_on_http_error(self, ollama):
        import httpx

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
            mock_client.post.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await ollama.embed(["text"])

    @pytest.mark.asyncio
    async def test_embed_empty_list(self, ollama):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": []}
            mock_client.post.return_value = mock_response

            result = await ollama.embed([])

        assert result == []


class TestOllamaEmbedderEmbedQuery:
    @pytest.mark.asyncio
    async def test_embed_query_returns_first_vector(self, ollama):
        expected = [0.5, 0.6, 0.7]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [expected]}
            mock_client.post.return_value = mock_response

            result = await ollama.embed_query("what is kubernetes?")

        assert result == expected

    @pytest.mark.asyncio
    async def test_embed_query_uses_search_query_prefix(self, ollama):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [[0.1]]}
            mock_client.post.return_value = mock_response

            await ollama.embed_query("my query")

        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["input"] == ["search_query: my query"]

    @pytest.mark.asyncio
    async def test_embed_query_sends_to_api_embed_endpoint(self, ollama):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"embeddings": [[0.1]]}
            mock_client.post.return_value = mock_response

            await ollama.embed_query("query")

        url = mock_client.post.call_args.args[0]
        assert url.endswith("/api/embed")

    @pytest.mark.asyncio
    async def test_embed_query_raises_on_http_error(self, ollama):
        import httpx

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock()
            )
            mock_client.post.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await ollama.embed_query("query")
