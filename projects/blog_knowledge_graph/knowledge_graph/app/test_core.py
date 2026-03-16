"""Core unit tests for blog_knowledge_graph app modules.

Covers: models, config, chunker, embedders/base, embedders/ollama, embedders/gemini.
All external HTTP/API calls are mocked via unittest.mock.patch.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# models.py
# ---------------------------------------------------------------------------

from projects.blog_knowledge_graph.knowledge_graph.app.models import (
    ChunkPayload,
    Document,
    ScrapeResult,
    SourceConfig,
    content_hash,
)


class TestContentHash:
    def test_returns_sha256_hex_digest(self):
        text = "hello world"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert content_hash(text) == expected

    def test_is_deterministic(self):
        assert content_hash("foo") == content_hash("foo")

    def test_different_inputs_differ(self):
        assert content_hash("abc") != content_hash("xyz")

    def test_returns_64_char_hex_string(self):
        h = content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_string_produces_known_hash(self):
        h = content_hash("")
        assert len(h) == 64

    def test_unicode_content(self):
        h = content_hash("こんにちは世界")
        assert len(h) == 64


class TestDocumentTypedDict:
    def test_happy_path_construction(self):
        from datetime import datetime

        doc: Document = {
            "source_type": "rss",
            "source_url": "https://example.com/feed",
            "title": "Hello World",
            "author": "Jane Doe",
            "published_at": datetime(2025, 1, 1),
            "content": "# Hello\n\nWorld.",
        }
        assert doc["source_type"] == "rss"
        assert doc["title"] == "Hello World"

    def test_optional_author_none(self):
        from datetime import datetime

        doc: Document = {
            "source_type": "html",
            "source_url": "https://example.com",
            "title": "No Author",
            "author": None,
            "published_at": datetime(2025, 6, 1),
            "content": "content",
        }
        assert doc["author"] is None

    def test_optional_published_at_none(self):
        doc: Document = {
            "source_type": "html",
            "source_url": "https://example.com",
            "title": "No Date",
            "author": "Bob",
            "published_at": None,
            "content": "content",
        }
        assert doc["published_at"] is None


class TestSourceConfigTypedDict:
    def test_rss_type(self):
        cfg: SourceConfig = {
            "url": "https://example.com/rss.xml",
            "type": "rss",
            "name": "Example Blog",
        }
        assert cfg["type"] == "rss"

    def test_html_type(self):
        cfg: SourceConfig = {
            "url": "https://example.com",
            "type": "html",
            "name": None,
        }
        assert cfg["type"] == "html"
        assert cfg["name"] is None


class TestScrapeResultTypedDict:
    def test_new_result(self):
        result: ScrapeResult = {
            "url": "https://example.com/post",
            "content_hash": "abc123",
            "is_new": True,
            "title": "New Post",
            "error": None,
        }
        assert result["is_new"] is True
        assert result["error"] is None

    def test_error_result(self):
        result: ScrapeResult = {
            "url": "https://example.com/404",
            "content_hash": None,
            "is_new": False,
            "title": "",
            "error": "HTTP 404",
        }
        assert result["error"] == "HTTP 404"
        assert result["content_hash"] is None


class TestChunkPayloadTypedDict:
    def test_full_construction(self):
        payload: ChunkPayload = {
            "content_hash": "deadbeef",
            "chunk_index": 0,
            "chunk_text": "Some chunk text here.",
            "section_header": "## Introduction",
            "source_url": "https://example.com",
            "source_type": "html",
            "title": "My Article",
            "author": "Alice",
            "published_at": "2025-01-15T00:00:00Z",
        }
        assert payload["chunk_index"] == 0
        assert payload["section_header"] == "## Introduction"

    def test_optional_fields_none(self):
        payload: ChunkPayload = {
            "content_hash": "abc",
            "chunk_index": 1,
            "chunk_text": "text",
            "section_header": "",
            "source_url": "https://example.com",
            "source_type": "rss",
            "title": "Title",
            "author": None,
            "published_at": None,
        }
        assert payload["author"] is None
        assert payload["published_at"] is None


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------

from projects.blog_knowledge_graph.knowledge_graph.app.config import (
    EmbedderSettings,
    McpSettings,
    ScraperSettings,
)


class TestScraperSettingsDefaults:
    def test_default_port(self):
        assert ScraperSettings().port == 8080

    def test_default_s3_bucket(self):
        assert ScraperSettings().s3_bucket == "knowledge"

    def test_default_rate_limit(self):
        assert ScraperSettings().default_rate_limit_seconds == 1.0

    def test_default_retry_attempts(self):
        assert ScraperSettings().retry_attempts == 3

    def test_default_retry_base_delay(self):
        assert ScraperSettings().retry_base_delay == 2.0

    def test_default_slack_webhook_empty(self):
        assert ScraperSettings().slack_webhook_url == ""

    def test_default_slack_notify_mode(self):
        assert ScraperSettings().slack_notify_mode == "summary_only"

    def test_default_sources_yaml_path(self):
        assert ScraperSettings().sources_yaml_path == Path("/config/sources.yaml")

    def test_sources_yaml_path_is_path_instance(self):
        assert isinstance(ScraperSettings().sources_yaml_path, Path)

    def test_default_s3_credentials_empty(self):
        s = ScraperSettings()
        assert s.s3_access_key == ""
        assert s.s3_secret_key == ""


class TestScraperSettingsOverrides:
    def test_port_override(self):
        assert ScraperSettings(port=9090).port == 9090

    def test_s3_bucket_override(self):
        assert ScraperSettings(s3_bucket="my-bucket").s3_bucket == "my-bucket"

    def test_rate_limit_override(self):
        assert ScraperSettings(default_rate_limit_seconds=5.0).default_rate_limit_seconds == 5.0

    def test_retry_attempts_override(self):
        assert ScraperSettings(retry_attempts=5).retry_attempts == 5

    def test_notify_mode_override(self):
        assert ScraperSettings(slack_notify_mode="on_new_content").slack_notify_mode == "on_new_content"


class TestScraperSettingsEnvVars:
    def test_env_prefix_port(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_PORT", "7777")
        assert ScraperSettings().port == 7777

    def test_env_prefix_s3_bucket(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_S3_BUCKET", "env-bucket")
        assert ScraperSettings().s3_bucket == "env-bucket"

    def test_env_prefix_rate_limit(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_DEFAULT_RATE_LIMIT_SECONDS", "2.5")
        assert ScraperSettings().default_rate_limit_seconds == 2.5

    def test_env_prefix_slack_webhook(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_SLACK_WEBHOOK_URL", "https://hooks.slack.com/env")
        assert ScraperSettings().slack_webhook_url == "https://hooks.slack.com/env"


class TestEmbedderSettingsDefaults:
    def test_default_provider(self):
        assert EmbedderSettings().provider == "ollama"

    def test_default_ollama_model(self):
        assert EmbedderSettings().ollama_model == "nomic-embed-text"

    def test_default_gemini_model(self):
        assert EmbedderSettings().gemini_model == "gemini-embedding-001"

    def test_default_vector_size(self):
        assert EmbedderSettings().vector_size == 768

    def test_default_chunk_max_tokens(self):
        assert EmbedderSettings().chunk_max_tokens == 512

    def test_default_chunk_min_tokens(self):
        assert EmbedderSettings().chunk_min_tokens == 50

    def test_default_qdrant_collection(self):
        assert EmbedderSettings().qdrant_collection == "knowledge_graph"

    def test_default_gemini_api_key_empty(self):
        assert EmbedderSettings().gemini_api_key == ""


class TestEmbedderSettingsEnvVars:
    def test_env_prefix_provider(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_PROVIDER", "gemini")
        assert EmbedderSettings().provider == "gemini"

    def test_env_prefix_chunk_max_tokens(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_CHUNK_MAX_TOKENS", "256")
        assert EmbedderSettings().chunk_max_tokens == 256

    def test_env_prefix_gemini_api_key(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_GEMINI_API_KEY", "my-key")
        assert EmbedderSettings().gemini_api_key == "my-key"

    def test_env_prefix_vector_size(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_VECTOR_SIZE", "1536")
        assert EmbedderSettings().vector_size == 1536


class TestMcpSettingsDefaults:
    def test_default_port(self):
        assert McpSettings().port == 8080

    def test_default_provider(self):
        assert McpSettings().provider == "ollama"

    def test_default_qdrant_collection(self):
        assert McpSettings().qdrant_collection == "knowledge_graph"

    def test_default_s3_bucket(self):
        assert McpSettings().s3_bucket == "knowledge"

    def test_default_gemini_api_key_empty(self):
        assert McpSettings().gemini_api_key == ""


class TestMcpSettingsEnvVars:
    def test_env_prefix_port(self, monkeypatch):
        monkeypatch.setenv("MCP_PORT", "9999")
        assert McpSettings().port == 9999

    def test_env_prefix_provider(self, monkeypatch):
        monkeypatch.setenv("MCP_PROVIDER", "gemini")
        assert McpSettings().provider == "gemini"

    def test_env_prefix_qdrant_collection(self, monkeypatch):
        monkeypatch.setenv("MCP_QDRANT_COLLECTION", "custom_col")
        assert McpSettings().qdrant_collection == "custom_col"


# ---------------------------------------------------------------------------
# chunker.py
# ---------------------------------------------------------------------------

from projects.blog_knowledge_graph.knowledge_graph.app.chunker import (
    _estimate_tokens,
    _split_by_headers,
    _split_paragraphs,
    chunk_markdown,
)


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_single_word(self):
        assert _estimate_tokens("hello") >= 1

    def test_approximate_count(self):
        # 9 words * 1.3 = 11 (int)
        tokens = _estimate_tokens("The quick brown fox jumps over the lazy dog")
        assert 9 <= tokens <= 15

    def test_longer_text_more_tokens(self):
        short = _estimate_tokens("hello world")
        long = _estimate_tokens("hello world " * 50)
        assert long > short


class TestSplitByHeaders:
    def test_no_headers_returns_single_section(self):
        sections = _split_by_headers("Plain text with no headers.")
        assert len(sections) == 1
        assert sections[0][0] == ""
        assert sections[0][1] == "Plain text with no headers."

    def test_single_h1_header(self):
        sections = _split_by_headers("# Title\n\nBody text.")
        assert len(sections) == 1
        assert sections[0][0] == "# Title"
        assert "Body text." in sections[0][1]

    def test_h2_header(self):
        sections = _split_by_headers("## Section\n\nContent.")
        assert len(sections) == 1
        assert sections[0][0] == "## Section"

    def test_h3_header(self):
        sections = _split_by_headers("### Sub\n\nText.")
        assert len(sections) == 1
        assert sections[0][0] == "### Sub"

    def test_multiple_headers_split_correctly(self):
        content = "# First\n\nBody one.\n\n## Second\n\nBody two.\n\n### Third\n\nBody three."
        sections = _split_by_headers(content)
        assert len(sections) == 3
        assert sections[0][0] == "# First"
        assert sections[1][0] == "## Second"
        assert sections[2][0] == "### Third"

    def test_h4_not_a_split_point(self):
        content = "# Title\n\nIntro.\n\n#### Detail\n\nDetail text."
        sections = _split_by_headers(content)
        # h4 should not split — all stays under # Title
        assert len(sections) == 1

    def test_content_before_first_header_captured(self):
        content = "Preamble text.\n\n# Header\n\nBody."
        sections = _split_by_headers(content)
        assert any("Preamble text." in s[1] for s in sections)

    def test_empty_body_section_skipped(self):
        content = "# First\n\n# Second\n\nBody."
        sections = _split_by_headers(content)
        # First section has no body — should be skipped
        assert all(s[1] != "" for s in sections)


class TestSplitParagraphs:
    def test_single_paragraph_under_limit(self):
        text = "Short paragraph."
        chunks = _split_paragraphs(text, max_tokens=512)
        assert len(chunks) == 1
        assert chunks[0] == "Short paragraph."

    def test_multiple_paragraphs_combined_when_under_limit(self):
        text = "Para one.\n\nPara two."
        chunks = _split_paragraphs(text, max_tokens=512)
        assert len(chunks) == 1

    def test_overflow_creates_new_chunk(self):
        # Force overflow by setting tiny max_tokens
        long_para = "word " * 100
        text = f"{long_para}\n\n{long_para}"
        chunks = _split_paragraphs(text, max_tokens=10)
        assert len(chunks) >= 2

    def test_code_block_kept_intact(self):
        text = "```python\ndef foo():\n    return 42\n```"
        chunks = _split_paragraphs(text, max_tokens=512)
        assert len(chunks) == 1
        assert "def foo():" in chunks[0]

    def test_empty_input_returns_empty(self):
        chunks = _split_paragraphs("", max_tokens=512)
        assert chunks == []


class TestChunkMarkdown:
    def test_basic_chunking_returns_payloads(self):
        chunks = chunk_markdown(
            content="# Title\n\nSome content here.",
            content_hash="abc123",
            source_url="https://example.com",
            source_type="html",
            title="Test",
        )
        assert len(chunks) >= 1
        assert chunks[0]["content_hash"] == "abc123"

    def test_chunk_indices_are_sequential(self):
        content = "# A\n\nText A.\n\n## B\n\nText B.\n\n### C\n\nText C."
        chunks = chunk_markdown(
            content=content,
            content_hash="hash",
            source_url="https://example.com",
            source_type="html",
            title="Test",
        )
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_empty_content_returns_empty_list(self):
        chunks = chunk_markdown(
            content="",
            content_hash="empty",
            source_url="https://example.com",
            source_type="html",
            title="Empty",
        )
        assert chunks == []

    def test_metadata_propagated_to_all_chunks(self):
        content = "# Header\n\n" + "word " * 200 + "\n\n## Header2\n\n" + "word " * 200
        chunks = chunk_markdown(
            content=content,
            content_hash="meta123",
            source_url="https://example.com/post",
            source_type="rss",
            title="My Title",
            author="Author Name",
            published_at="2025-03-01",
            max_tokens=100,
        )
        for chunk in chunks:
            assert chunk["source_url"] == "https://example.com/post"
            assert chunk["source_type"] == "rss"
            assert chunk["title"] == "My Title"
            assert chunk["author"] == "Author Name"
            assert chunk["published_at"] == "2025-03-01"

    def test_section_header_preserved(self):
        content = "## My Section\n\nContent under section."
        chunks = chunk_markdown(
            content=content,
            content_hash="hdr",
            source_url="https://example.com",
            source_type="html",
            title="Test",
        )
        assert chunks[0]["section_header"] == "## My Section"

    def test_large_content_splits_into_multiple_chunks(self):
        content = "# Big\n\n" + "word " * 300 + "\n\n## Also Big\n\n" + "word " * 300
        chunks = chunk_markdown(
            content=content,
            content_hash="big",
            source_url="https://example.com",
            source_type="html",
            title="Big",
            max_tokens=100,
        )
        assert len(chunks) >= 2

    def test_small_chunks_merged_with_previous(self):
        # "Tiny." is well under min_tokens (50) so it merges with previous
        content = "# A\n\nTiny.\n\n## B\n\nAlso tiny."
        chunks = chunk_markdown(
            content=content,
            content_hash="merge",
            source_url="https://example.com",
            source_type="html",
            title="Test",
            min_tokens=50,
        )
        assert len(chunks) <= 2

    def test_code_block_not_split_across_chunks(self):
        content = (
            "# Code Section\n\n"
            "```python\ndef hello():\n    print('hi')\n```\n\n"
            "After the code block."
        )
        chunks = chunk_markdown(
            content=content,
            content_hash="code",
            source_url="https://example.com",
            source_type="html",
            title="Code Test",
        )
        code_chunks = [c for c in chunks if "def hello():" in c["chunk_text"]]
        assert len(code_chunks) == 1
        assert "print('hi')" in code_chunks[0]["chunk_text"]

    def test_no_headers_treated_as_single_section(self):
        content = "Just plain text without any headers."
        chunks = chunk_markdown(
            content=content,
            content_hash="plain",
            source_url="https://example.com",
            source_type="html",
            title="Plain",
        )
        assert len(chunks) == 1
        assert chunks[0]["section_header"] == ""

    def test_optional_author_none_in_payload(self):
        chunks = chunk_markdown(
            content="# Title\n\nContent.",
            content_hash="noauthor",
            source_url="https://example.com",
            source_type="html",
            title="Test",
            author=None,
            published_at=None,
        )
        assert chunks[0]["author"] is None
        assert chunks[0]["published_at"] is None


# ---------------------------------------------------------------------------
# embedders/base.py — Embedder Protocol
# ---------------------------------------------------------------------------

from projects.blog_knowledge_graph.knowledge_graph.app.embedders.base import Embedder
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini import (
    GeminiEmbedder,
)
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama import (
    OllamaEmbedder,
)


class TestEmbedderProtocol:
    def test_complete_implementation_satisfies_protocol(self):
        class GoodEmbedder:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.1] * 768 for _ in texts]

            @property
            def dimension(self) -> int:
                return 768

        assert isinstance(GoodEmbedder(), Embedder)

    def test_missing_embed_method_fails_protocol(self):
        class MissingEmbed:
            @property
            def dimension(self) -> int:
                return 768

        assert not isinstance(MissingEmbed(), Embedder)

    def test_missing_dimension_fails_protocol(self):
        class MissingDimension:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.1]]

        assert not isinstance(MissingDimension(), Embedder)

    def test_empty_class_fails_protocol(self):
        class Empty:
            pass

        assert not isinstance(Empty(), Embedder)

    def test_ollama_embedder_satisfies_protocol(self):
        assert isinstance(OllamaEmbedder(), Embedder)

    def test_gemini_embedder_satisfies_protocol(self):
        assert isinstance(GeminiEmbedder(api_key="key"), Embedder)


# ---------------------------------------------------------------------------
# embedders/ollama.py
# ---------------------------------------------------------------------------


@pytest.fixture
def ollama():
    return OllamaEmbedder(url="http://localhost:11434", model="nomic-embed-text")


def _make_ollama_mock(return_data: dict):
    """Helper: build a patched httpx.AsyncClient returning return_data."""
    mock_cls = MagicMock()
    mock_client = AsyncMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = return_data
    mock_client.post.return_value = mock_response
    return mock_cls, mock_client


_OLLAMA_PATH = (
    "projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama.httpx.AsyncClient"
)


class TestOllamaEmbedderInit:
    def test_default_url(self):
        assert OllamaEmbedder()._url == "http://localhost:11434"

    def test_default_model(self):
        assert OllamaEmbedder()._model == "nomic-embed-text"

    def test_trailing_slash_stripped(self):
        embedder = OllamaEmbedder(url="http://localhost:11434/")
        assert not embedder._url.endswith("/")

    def test_custom_url_and_model(self):
        embedder = OllamaEmbedder(url="http://custom:11434", model="my-model")
        assert embedder._url == "http://custom:11434"
        assert embedder._model == "my-model"


class TestOllamaEmbedderDimension:
    def test_dimension_is_768(self, ollama):
        assert ollama.dimension == 768


class TestOllamaEmbedderEmbed:
    @pytest.mark.asyncio
    async def test_successful_embed_returns_vectors(self, ollama):
        expected = [[0.1, 0.2], [0.3, 0.4]]
        mock_cls, _ = _make_ollama_mock({"embeddings": expected})
        with patch(_OLLAMA_PATH, mock_cls):
            result = await ollama.embed(["hello", "world"])
        assert result == expected

    @pytest.mark.asyncio
    async def test_embed_adds_search_document_prefix(self, ollama):
        mock_cls, mock_client = _make_ollama_mock({"embeddings": [[0.1], [0.2]]})
        with patch(_OLLAMA_PATH, mock_cls):
            await ollama.embed(["first", "second"])
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["input"] == ["search_document: first", "search_document: second"]

    @pytest.mark.asyncio
    async def test_embed_posts_to_api_embed_endpoint(self, ollama):
        mock_cls, mock_client = _make_ollama_mock({"embeddings": [[0.1]]})
        with patch(_OLLAMA_PATH, mock_cls):
            await ollama.embed(["text"])
        url = mock_client.post.call_args.args[0]
        assert url.endswith("/api/embed")

    @pytest.mark.asyncio
    async def test_embed_sends_model_name(self, ollama):
        mock_cls, mock_client = _make_ollama_mock({"embeddings": [[0.1]]})
        with patch(_OLLAMA_PATH, mock_cls):
            await ollama.embed(["text"])
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["model"] == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_embed_empty_list_returns_empty(self, ollama):
        mock_cls, _ = _make_ollama_mock({"embeddings": []})
        with patch(_OLLAMA_PATH, mock_cls):
            result = await ollama.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_raises_on_http_error(self, ollama):
        import httpx

        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client.post.return_value = mock_response

        with patch(_OLLAMA_PATH, mock_cls):
            with pytest.raises(httpx.HTTPStatusError):
                await ollama.embed(["text"])

    @pytest.mark.asyncio
    async def test_embed_raises_on_connection_error(self, ollama):
        import httpx

        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        with patch(_OLLAMA_PATH, mock_cls):
            with pytest.raises(httpx.ConnectError):
                await ollama.embed(["text"])


class TestOllamaEmbedderEmbedQuery:
    @pytest.mark.asyncio
    async def test_embed_query_returns_first_vector(self, ollama):
        expected = [0.5, 0.6, 0.7]
        mock_cls, _ = _make_ollama_mock({"embeddings": [expected]})
        with patch(_OLLAMA_PATH, mock_cls):
            result = await ollama.embed_query("my query")
        assert result == expected

    @pytest.mark.asyncio
    async def test_embed_query_uses_search_query_prefix(self, ollama):
        mock_cls, mock_client = _make_ollama_mock({"embeddings": [[0.1]]})
        with patch(_OLLAMA_PATH, mock_cls):
            await ollama.embed_query("find me something")
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["input"] == ["search_query: find me something"]

    @pytest.mark.asyncio
    async def test_embed_query_raises_on_http_error(self, ollama):
        import httpx

        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock()
        )
        mock_client.post.return_value = mock_response

        with patch(_OLLAMA_PATH, mock_cls):
            with pytest.raises(httpx.HTTPStatusError):
                await ollama.embed_query("query")


# ---------------------------------------------------------------------------
# embedders/gemini.py
# ---------------------------------------------------------------------------


@pytest.fixture
def gemini():
    return GeminiEmbedder(api_key="test-api-key", model="gemini-embedding-001")


def _make_gemini_mock(return_data: dict):
    """Helper: build a patched httpx.AsyncClient returning return_data."""
    mock_cls = MagicMock()
    mock_client = AsyncMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = return_data
    mock_client.post.return_value = mock_response
    return mock_cls, mock_client


_GEMINI_PATH = (
    "projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini.httpx.AsyncClient"
)


class TestGeminiEmbedderInit:
    def test_stores_api_key(self):
        embedder = GeminiEmbedder(api_key="my-key")
        assert embedder._api_key == "my-key"

    def test_default_model(self):
        embedder = GeminiEmbedder(api_key="key")
        assert embedder._model == "gemini-embedding-001"

    def test_custom_model(self):
        embedder = GeminiEmbedder(api_key="key", model="custom-model")
        assert embedder._model == "custom-model"


class TestGeminiEmbedderDimension:
    def test_dimension_is_768(self, gemini):
        assert gemini.dimension == 768


class TestGeminiEmbedderEmbed:
    @pytest.mark.asyncio
    async def test_successful_embed_returns_vectors(self, gemini):
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_cls, _ = _make_gemini_mock(
            {"embeddings": [{"values": v} for v in vectors]}
        )
        with patch(_GEMINI_PATH, mock_cls):
            result = await gemini.embed(["hello world", "foo bar"])
        assert result == vectors

    @pytest.mark.asyncio
    async def test_embed_uses_batch_endpoint(self, gemini):
        mock_cls, mock_client = _make_gemini_mock(
            {"embeddings": [{"values": [0.1]}]}
        )
        with patch(_GEMINI_PATH, mock_cls):
            await gemini.embed(["text"])
        url = mock_client.post.call_args.args[0]
        assert "batchEmbedContents" in url

    @pytest.mark.asyncio
    async def test_embed_sends_api_key_as_query_param(self, gemini):
        mock_cls, mock_client = _make_gemini_mock(
            {"embeddings": [{"values": [0.1]}]}
        )
        with patch(_GEMINI_PATH, mock_cls):
            await gemini.embed(["text"])
        params = mock_client.post.call_args.kwargs.get("params", {})
        assert params.get("key") == "test-api-key"

    @pytest.mark.asyncio
    async def test_embed_uses_retrieval_document_task_type(self, gemini):
        mock_cls, mock_client = _make_gemini_mock(
            {"embeddings": [{"values": [0.1]}]}
        )
        with patch(_GEMINI_PATH, mock_cls):
            await gemini.embed(["text"])
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"

    @pytest.mark.asyncio
    async def test_embed_includes_model_in_each_request(self, gemini):
        mock_cls, mock_client = _make_gemini_mock(
            {"embeddings": [{"values": [0.1]}]}
        )
        with patch(_GEMINI_PATH, mock_cls):
            await gemini.embed(["text"])
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["requests"][0]["model"] == "models/gemini-embedding-001"

    @pytest.mark.asyncio
    async def test_embed_empty_input_returns_empty(self, gemini):
        mock_cls, _ = _make_gemini_mock({"embeddings": []})
        with patch(_GEMINI_PATH, mock_cls):
            result = await gemini.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_raises_on_api_error(self, gemini):
        import httpx

        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=MagicMock()
        )
        mock_client.post.return_value = mock_response

        with patch(_GEMINI_PATH, mock_cls):
            with pytest.raises(httpx.HTTPStatusError):
                await gemini.embed(["text"])

    @pytest.mark.asyncio
    async def test_embed_raises_on_connection_error(self, gemini):
        import httpx

        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("Network unreachable")

        with patch(_GEMINI_PATH, mock_cls):
            with pytest.raises(httpx.ConnectError):
                await gemini.embed(["text"])

    @pytest.mark.asyncio
    async def test_embed_batch_size_matches_input(self, gemini):
        texts = ["a", "b", "c"]
        vectors = [[float(i)] for i in range(3)]
        mock_cls, mock_client = _make_gemini_mock(
            {"embeddings": [{"values": v} for v in vectors]}
        )
        with patch(_GEMINI_PATH, mock_cls):
            result = await gemini.embed(texts)
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert len(payload["requests"]) == 3
        assert len(result) == 3


class TestGeminiEmbedderEmbedQuery:
    @pytest.mark.asyncio
    async def test_embed_query_returns_vector(self, gemini):
        expected = [0.9, 0.8, 0.7]
        mock_cls, _ = _make_gemini_mock({"embedding": {"values": expected}})
        with patch(_GEMINI_PATH, mock_cls):
            result = await gemini.embed_query("search query")
        assert result == expected

    @pytest.mark.asyncio
    async def test_embed_query_uses_embed_content_endpoint(self, gemini):
        mock_cls, mock_client = _make_gemini_mock({"embedding": {"values": [0.1]}})
        with patch(_GEMINI_PATH, mock_cls):
            await gemini.embed_query("query text")
        url = mock_client.post.call_args.args[0]
        assert "embedContent" in url

    @pytest.mark.asyncio
    async def test_embed_query_uses_retrieval_query_task_type(self, gemini):
        mock_cls, mock_client = _make_gemini_mock({"embedding": {"values": [0.1]}})
        with patch(_GEMINI_PATH, mock_cls):
            await gemini.embed_query("some query")
        payload = mock_client.post.call_args.kwargs.get("json", {})
        assert payload["taskType"] == "RETRIEVAL_QUERY"

    @pytest.mark.asyncio
    async def test_embed_query_raises_on_http_error(self, gemini):
        import httpx

        mock_cls = MagicMock()
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=MagicMock()
        )
        mock_client.post.return_value = mock_response

        with patch(_GEMINI_PATH, mock_cls):
            with pytest.raises(httpx.HTTPStatusError):
                await gemini.embed_query("query")
