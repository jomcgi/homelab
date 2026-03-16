"""Tests for the embedding pipeline entry point."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.config import EmbedderSettings
from projects.blog_knowledge_graph.knowledge_graph.app.embedder_main import (
    _create_embedder,
    run_embedding_pipeline,
)
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini import (
    GeminiEmbedder,
)
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama import (
    OllamaEmbedder,
)


# ---------------------------------------------------------------------------
# _create_embedder
# ---------------------------------------------------------------------------


class TestCreateEmbedder:
    def test_returns_ollama_embedder_by_default(self):
        settings = EmbedderSettings(provider="ollama", ollama_url="http://ollama:11434")
        embedder = _create_embedder(settings)
        assert isinstance(embedder, OllamaEmbedder)

    def test_returns_gemini_embedder_when_configured(self):
        settings = EmbedderSettings(provider="gemini", gemini_api_key="key123")
        embedder = _create_embedder(settings)
        assert isinstance(embedder, GeminiEmbedder)

    def test_ollama_embedder_uses_configured_url(self):
        settings = EmbedderSettings(
            provider="ollama", ollama_url="http://my-ollama:11434"
        )
        embedder = _create_embedder(settings)
        assert isinstance(embedder, OllamaEmbedder)
        assert "my-ollama" in embedder._url

    def test_ollama_embedder_uses_configured_model(self):
        settings = EmbedderSettings(
            provider="ollama", ollama_model="custom-embed-model"
        )
        embedder = _create_embedder(settings)
        assert isinstance(embedder, OllamaEmbedder)
        assert embedder._model == "custom-embed-model"

    def test_gemini_embedder_uses_configured_api_key(self):
        settings = EmbedderSettings(provider="gemini", gemini_api_key="secret-key")
        embedder = _create_embedder(settings)
        assert isinstance(embedder, GeminiEmbedder)
        assert embedder._api_key == "secret-key"

    def test_gemini_embedder_uses_configured_model(self):
        settings = EmbedderSettings(
            provider="gemini", gemini_model="gemini-embedding-exp"
        )
        embedder = _create_embedder(settings)
        assert isinstance(embedder, GeminiEmbedder)
        assert embedder._model == "gemini-embedding-exp"

    def test_unknown_provider_falls_back_to_ollama(self):
        # Any non-"gemini" provider defaults to Ollama
        settings = EmbedderSettings(provider="unknown-provider")
        embedder = _create_embedder(settings)
        assert isinstance(embedder, OllamaEmbedder)


# ---------------------------------------------------------------------------
# run_embedding_pipeline
# ---------------------------------------------------------------------------


@pytest.fixture
def embedder_settings():
    return EmbedderSettings(
        s3_endpoint="http://localhost:8333",
        s3_bucket="test-bucket",
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_collection",
        provider="ollama",
        ollama_url="http://localhost:11434",
        chunk_max_tokens=512,
        chunk_min_tokens=50,
    )


def _make_mock_storage(hashes=None, content="# Title\n\nSome content.", meta=None):
    storage = MagicMock()
    storage.list_all_hashes.return_value = hashes or []
    storage.get_content.return_value = content
    storage.get_meta.return_value = meta or {
        "source_type": "html",
        "source_url": "https://example.com/post",
        "title": "Test Post",
        "author": "Author",
        "published_at": "2025-01-15T00:00:00",
    }
    return storage


def _make_mock_qdrant(already_embedded=False):
    qdrant = AsyncMock()
    qdrant.ensure_collection = AsyncMock()
    qdrant.has_content_hash = AsyncMock(return_value=already_embedded)
    qdrant.upsert_chunks = AsyncMock()
    return qdrant


def _make_mock_embedder(vector_dim=3):
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * vector_dim])
    embedder.dimension = vector_dim
    return embedder


class TestRunEmbeddingPipelineSkip:
    @pytest.mark.asyncio
    async def test_skips_already_embedded_documents(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        mock_storage = _make_mock_storage(hashes=["hash1", "hash2"])
        mock_qdrant = _make_mock_qdrant(already_embedded=True)
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        # Neither upsert nor embed should be called
        mock_qdrant.upsert_chunks.assert_not_called()
        mock_embedder.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_documents_completes_without_error(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        mock_storage = _make_mock_storage(hashes=[])
        mock_qdrant = _make_mock_qdrant()
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        mock_qdrant.upsert_chunks.assert_not_called()


class TestRunEmbeddingPipelineEmbed:
    @pytest.mark.asyncio
    async def test_embeds_new_document_and_upserts(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        mock_storage = _make_mock_storage(hashes=["newhash"])
        mock_qdrant = _make_mock_qdrant(already_embedded=False)

        vectors = [[0.1, 0.2, 0.3]]
        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(return_value=vectors)

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        mock_embedder.embed.assert_called()
        mock_qdrant.upsert_chunks.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_ensure_collection_on_startup(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        mock_storage = _make_mock_storage(hashes=[])
        mock_qdrant = _make_mock_qdrant()
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        mock_qdrant.ensure_collection.assert_called_once_with(
            vector_size=embedder_settings.vector_size
        )


class TestRunEmbeddingPipelineEdgeCases:
    @pytest.mark.asyncio
    async def test_skips_document_with_missing_content(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        mock_storage = _make_mock_storage(hashes=["missinghash"])
        mock_storage.get_content.return_value = None  # missing content

        mock_qdrant = _make_mock_qdrant(already_embedded=False)
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        mock_qdrant.upsert_chunks.assert_not_called()
        mock_embedder.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_document_with_missing_meta(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        mock_storage = _make_mock_storage(hashes=["nometahash"])
        mock_storage.get_meta.return_value = None  # missing metadata

        mock_qdrant = _make_mock_qdrant(already_embedded=False)
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        mock_qdrant.upsert_chunks.assert_not_called()
        mock_embedder.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_document_when_no_chunks_produced(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        # Very short content that produces no chunks (empty string)
        mock_storage = _make_mock_storage(hashes=["emptyhash"], content="")
        mock_qdrant = _make_mock_qdrant(already_embedded=False)
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.chunk_markdown",
                return_value=[],
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        mock_qdrant.upsert_chunks.assert_not_called()

    @pytest.mark.asyncio
    async def test_batches_embed_calls_for_large_document(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        # 40 chunks should trigger 2 batches (batch_size=32)
        num_chunks = 40
        mock_chunks = [
            {
                "content_hash": "bighash",
                "chunk_index": i,
                "chunk_text": f"Chunk text {i}",
                "section_header": "# Title",
                "source_url": "https://example.com",
                "source_type": "html",
                "title": "Big Doc",
                "author": None,
                "published_at": None,
            }
            for i in range(num_chunks)
        ]
        mock_storage = _make_mock_storage(hashes=["bighash"])
        mock_qdrant = _make_mock_qdrant(already_embedded=False)
        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2]] * 32)

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.chunk_markdown",
                return_value=mock_chunks,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        # 40 chunks / batch_size 32 = 2 calls
        assert mock_embedder.embed.call_count == 2

    @pytest.mark.asyncio
    async def test_meta_fields_passed_to_chunk_markdown(
        self, embedder_settings, monkeypatch
    ):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        meta = {
            "source_type": "rss",
            "source_url": "https://blog.example.com/post",
            "title": "RSS Post",
            "author": "Blog Author",
            "published_at": "2025-06-01T00:00:00",
        }
        mock_storage = _make_mock_storage(
            hashes=["rsshash"],
            content="# Post\n\nContent here.",
            meta=meta,
        )
        mock_qdrant = _make_mock_qdrant(already_embedded=False)
        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(return_value=[[0.1]])

        chunk_calls = []

        def capture_chunk_markdown(**kwargs):
            chunk_calls.append(kwargs)
            return [
                {
                    "content_hash": "rsshash",
                    "chunk_index": 0,
                    "chunk_text": "# Post\n\nContent here.",
                    "section_header": "# Post",
                    "source_url": kwargs["source_url"],
                    "source_type": kwargs["source_type"],
                    "title": kwargs["title"],
                    "author": kwargs.get("author"),
                    "published_at": kwargs.get("published_at"),
                }
            ]

        with (
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.S3Storage",
                return_value=mock_storage,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.QdrantClient",
                return_value=mock_qdrant,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main._create_embedder",
                return_value=mock_embedder,
            ),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.embedder_main.chunk_markdown",
                side_effect=capture_chunk_markdown,
            ),
        ):
            await run_embedding_pipeline(embedder_settings)

        assert len(chunk_calls) == 1
        assert chunk_calls[0]["source_type"] == "rss"
        assert chunk_calls[0]["source_url"] == "https://blog.example.com/post"
        assert chunk_calls[0]["title"] == "RSS Post"
        assert chunk_calls[0]["author"] == "Blog Author"
