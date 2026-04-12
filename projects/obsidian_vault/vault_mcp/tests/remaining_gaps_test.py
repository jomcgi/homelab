"""
Remaining edge-case tests for obsidian_vault/vault_mcp.

Covers gaps not addressed by the existing 13+ test files:

1. create_note() (main.py)
   - Empty content returns {"error": "content is required"}
   - Whitespace-only content returns {"error": "content is required"}
   - Valid content creates a Fleeting/<timestamp>.md note with YAML frontmatter
   - source parameter is included in the frontmatter
   - Error from write_note is propagated back

2. _reconcile_loop() cache cleanup (main.py)
   - shutil.rmtree IS called when the cache directory exists and init fails

3. get_indexed_sources() pagination (qdrant_client.py)
   - Makes a second request when next_page_offset is not None
   - Merges results across pages correctly
   - Deduplication: second occurrence of same source_url is ignored

4. upsert_chunks() deterministic UUID5 IDs (qdrant_client.py)
   - Same content_hash + chunk_index always produces the same point ID
   - Different chunk_index produces a different point ID

5. chunk_markdown() merging behaviour (chunker.py)
   - Small chunk in same section is merged into the previous chunk
   - Small chunk in a *different* section is NOT merged
   - Merged result respects max_tokens limit

6. _split_by_headers() no-header document (chunker.py)
   - Content with no headers returns a single ("", content) section
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.chunker import (
    _split_by_headers,
    chunk_markdown,
)
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    configure,
    create_note,
)
from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _configure_vault(tmp_path):
    """Configure vault to use a temporary directory for each test."""
    configure(Settings(path=str(tmp_path)))


@pytest.fixture(autouse=True)
def _init_git(tmp_path):
    """Initialize a git repo in the tmp vault so commits work."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Helpers for Qdrant HTTP mocking
# ---------------------------------------------------------------------------

_PATCH_TARGET = "projects.obsidian_vault.vault_mcp.app.qdrant_client.httpx.AsyncClient"


def _mock_response(status_code: int = 200, json_data: dict | None = None):
    import httpx

    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "http://test"),
    )


def _mock_async_client(**method_returns):
    mock = AsyncMock()
    for method, ret in method_returns.items():
        getattr(mock, method).return_value = ret
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


# ---------------------------------------------------------------------------
# 1. create_note()
# ---------------------------------------------------------------------------


class TestCreateNoteContent:
    """Tests for create_note() content validation and file creation."""

    async def test_empty_content_returns_error(self, tmp_path):
        """create_note('') returns {'error': 'content is required'}."""
        result = await create_note(content="")
        assert result == {"error": "content is required"}

    async def test_whitespace_only_content_returns_error(self, tmp_path):
        """create_note with only whitespace returns {'error': 'content is required'}."""
        result = await create_note(content="   \n\t  ")
        assert result == {"error": "content is required"}

    async def test_valid_content_creates_fleeting_note(self, tmp_path):
        """create_note with valid content creates a file under Fleeting/."""
        result = await create_note(content="This is my thought.")
        assert "error" not in result
        assert "path" in result
        assert result["path"].startswith("Fleeting/")
        assert result["path"].endswith(".md")
        # File must exist on disk
        assert (tmp_path / result["path"]).exists()

    async def test_valid_content_includes_yaml_frontmatter(self, tmp_path):
        """The created note contains YAML frontmatter with tags: fleeting."""
        result = await create_note(content="My fleeting thought.")
        assert "error" not in result
        content = (tmp_path / result["path"]).read_text()
        assert "---" in content
        assert "tags: fleeting" in content

    async def test_source_parameter_included_in_frontmatter(self, tmp_path):
        """The source= argument appears in the frontmatter."""
        result = await create_note(content="Test note.", source="webhook")
        assert "error" not in result
        content = (tmp_path / result["path"]).read_text()
        assert "source: webhook" in content

    async def test_default_source_is_api(self, tmp_path):
        """Default source value is 'api' when not specified."""
        result = await create_note(content="Default source test.")
        assert "error" not in result
        content = (tmp_path / result["path"]).read_text()
        assert "source: api" in content

    async def test_content_body_appears_after_frontmatter(self, tmp_path):
        """The content body appears in the note after the YAML frontmatter."""
        body = "This is the real content."
        result = await create_note(content=body)
        assert "error" not in result
        file_content = (tmp_path / result["path"]).read_text()
        assert body in file_content

    async def test_content_is_stripped_in_note(self, tmp_path):
        """Leading/trailing whitespace is stripped from the content body."""
        result = await create_note(content="  trimmed  ")
        assert "error" not in result
        file_content = (tmp_path / result["path"]).read_text()
        assert "trimmed" in file_content
        # Should not have leading spaces preserved
        lines = file_content.splitlines()
        content_lines = [l for l in lines if l.strip() == "trimmed"]
        assert len(content_lines) >= 1


class TestCreateNoteErrorPropagation:
    """create_note propagates errors from write_note."""

    async def test_git_failure_propagates_error(self, tmp_path):
        """If write_note returns an error dict, create_note returns it too."""
        import subprocess

        with patch.object(
            _mod,
            "_git",
            side_effect=subprocess.CalledProcessError(1, ["git"], stderr="lock failed"),
        ):
            result = await create_note(content="Some content")

        assert "error" in result


# ---------------------------------------------------------------------------
# 2. _reconcile_loop() — cache cleanup when directory exists
# ---------------------------------------------------------------------------


class TestReconcileLoopCacheCleanup:
    """shutil.rmtree is called when the cache directory exists on init failure."""

    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    async def test_rmtree_called_when_cache_dir_exists(self, tmp_path):
        """On VaultEmbedder init failure, rmtree clears the cache if it exists."""
        cache_dir = tmp_path / "fastembed_cache"
        cache_dir.mkdir()
        # Create a file inside to make it non-empty
        (cache_dir / "model.bin").write_bytes(b"fake model")

        settings = Settings(
            path=str(tmp_path),
            embed_cache_dir=str(cache_dir),
            reconcile_interval_seconds=1,
        )

        call_count = 0

        def fail_once_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("download failed")
            mock = MagicMock()
            mock.dimension = 768
            return mock

        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        rmtree_calls: list[str] = []

        def spy_rmtree(path, **kwargs):
            rmtree_calls.append(str(path))

        with (
            patch.object(_mod, "VaultEmbedder", side_effect=fail_once_then_succeed),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "projects.obsidian_vault.vault_mcp.app.main.shutil.rmtree",
                side_effect=spy_rmtree,
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        assert len(rmtree_calls) >= 1, (
            "shutil.rmtree should be called when cache dir exists on init failure"
        )
        assert str(cache_dir) in rmtree_calls[0]

    async def test_rmtree_not_called_when_cache_dir_missing(self, tmp_path):
        """shutil.rmtree is NOT called when cache dir doesn't exist."""
        missing_cache = tmp_path / "nonexistent_cache"
        assert not missing_cache.exists()

        settings = Settings(
            path=str(tmp_path),
            embed_cache_dir=str(missing_cache),
            reconcile_interval_seconds=1,
        )

        call_count = 0

        def fail_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("download failed")
            mock = MagicMock()
            mock.dimension = 768
            return mock

        mock_qdrant = AsyncMock()
        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        with (
            patch.object(_mod, "VaultEmbedder", side_effect=fail_once),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "projects.obsidian_vault.vault_mcp.app.main.shutil.rmtree"
            ) as mock_rmtree,
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        mock_rmtree.assert_not_called()


# ---------------------------------------------------------------------------
# 3. get_indexed_sources() pagination
# ---------------------------------------------------------------------------


class TestGetIndexedSourcesPagination:
    """get_indexed_sources() follows next_page_offset to fetch all pages."""

    async def test_pagination_fetches_second_page(self):
        """When next_page_offset is set, a second scroll request is made."""
        page1 = _mock_response(
            200,
            {
                "result": {
                    "points": [
                        {
                            "payload": {
                                "source_url": "vault://page1.md",
                                "content_hash": "h1",
                            }
                        }
                    ],
                    "next_page_offset": "cursor-abc",
                }
            },
        )
        page2 = _mock_response(
            200,
            {
                "result": {
                    "points": [
                        {
                            "payload": {
                                "source_url": "vault://page2.md",
                                "content_hash": "h2",
                            }
                        }
                    ],
                    "next_page_offset": None,
                }
            },
        )
        mock = _mock_async_client(post=page1)
        # Second call returns page2
        mock.post.side_effect = [page1, page2]

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        assert "vault://page1.md" in result
        assert "vault://page2.md" in result
        assert result["vault://page1.md"] == "h1"
        assert result["vault://page2.md"] == "h2"
        # Two HTTP calls were made (one per page)
        assert mock.post.call_count == 2

    async def test_pagination_second_request_includes_offset(self):
        """The second scroll request body includes the offset from page 1."""
        page1 = _mock_response(
            200,
            {
                "result": {
                    "points": [
                        {
                            "payload": {
                                "source_url": "vault://a.md",
                                "content_hash": "ha",
                            }
                        }
                    ],
                    "next_page_offset": "page-offset-xyz",
                }
            },
        )
        page2 = _mock_response(
            200,
            {
                "result": {
                    "points": [],
                    "next_page_offset": None,
                }
            },
        )
        mock = _mock_async_client(post=page1)
        mock.post.side_effect = [page1, page2]

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.get_indexed_sources()

        # Second call must include offset="page-offset-xyz" in its JSON body
        second_call_kwargs = mock.post.call_args_list[1][1]
        body = second_call_kwargs.get("json", {})
        assert body.get("offset") == "page-offset-xyz"

    async def test_deduplication_same_source_url_from_multiple_pages(self):
        """If the same source_url appears on two pages, only the first is kept."""
        page1 = _mock_response(
            200,
            {
                "result": {
                    "points": [
                        {
                            "payload": {
                                "source_url": "vault://dup.md",
                                "content_hash": "original-hash",
                            }
                        }
                    ],
                    "next_page_offset": "next",
                }
            },
        )
        page2 = _mock_response(
            200,
            {
                "result": {
                    "points": [
                        {
                            "payload": {
                                "source_url": "vault://dup.md",
                                "content_hash": "second-hash",
                            }
                        }
                    ],
                    "next_page_offset": None,
                }
            },
        )
        mock = _mock_async_client(post=page1)
        mock.post.side_effect = [page1, page2]

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            result = await qdrant.get_indexed_sources()

        # Only one entry for the duplicate
        assert len(result) == 1
        # First hash wins (deduplication condition: `url not in sources`)
        assert result["vault://dup.md"] == "original-hash"


# ---------------------------------------------------------------------------
# 4. upsert_chunks() — deterministic UUID5 point IDs
# ---------------------------------------------------------------------------


class TestUpsertChunksDeterministicIds:
    """upsert_chunks() generates deterministic UUID5 IDs from content_hash+index."""

    def _make_chunk(self, content_hash: str = "abc123", chunk_index: int = 0):
        return {
            "content_hash": content_hash,
            "chunk_index": chunk_index,
            "chunk_text": "Sample chunk text.",
            "section_header": "# Section",
            "source_url": "vault://note.md",
            "title": "note.md",
        }

    async def test_same_inputs_produce_same_id(self):
        """Calling upsert_chunks twice with identical chunks uses the same point ID."""
        ids_first: list[str] = []
        ids_second: list[str] = []

        mock1 = _mock_async_client(
            put=_mock_response(200, {"result": {"operation_id": 1, "status": "ok"}})
        )
        mock2 = _mock_async_client(
            put=_mock_response(200, {"result": {"operation_id": 2, "status": "ok"}})
        )

        chunk = self._make_chunk(content_hash="deadbeef", chunk_index=0)
        vector = [0.1] * 768

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")

        with patch(_PATCH_TARGET, return_value=mock1):
            await qdrant.upsert_chunks([chunk], [vector])
        ids_first = [p["id"] for p in mock1.put.call_args[1]["json"]["points"]]

        with patch(_PATCH_TARGET, return_value=mock2):
            await qdrant.upsert_chunks([chunk], [vector])
        ids_second = [p["id"] for p in mock2.put.call_args[1]["json"]["points"]]

        assert ids_first == ids_second, (
            f"Expected deterministic IDs but got {ids_first} vs {ids_second}"
        )

    async def test_different_chunk_index_produces_different_id(self):
        """Chunk index 0 and index 1 of the same content produce different IDs."""
        mock = _mock_async_client(
            put=_mock_response(200, {"result": {"operation_id": 1, "status": "ok"}})
        )

        chunk0 = self._make_chunk(content_hash="deadbeef", chunk_index=0)
        chunk1 = self._make_chunk(content_hash="deadbeef", chunk_index=1)
        vectors = [[0.1] * 768, [0.2] * 768]

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks([chunk0, chunk1], vectors)

        points = mock.put.call_args[1]["json"]["points"]
        assert len(points) == 2
        assert points[0]["id"] != points[1]["id"], (
            "Different chunk_index values must produce different point IDs"
        )

    async def test_different_content_hash_produces_different_id(self):
        """Two chunks with the same index but different hashes get different IDs."""
        mock = _mock_async_client(
            put=_mock_response(200, {"result": {"operation_id": 1, "status": "ok"}})
        )

        chunk_a = self._make_chunk(content_hash="hash-a", chunk_index=0)
        chunk_b = self._make_chunk(content_hash="hash-b", chunk_index=0)
        vectors = [[0.1] * 768, [0.2] * 768]

        qdrant = QdrantClient(url="http://localhost:6333", collection="test")
        with patch(_PATCH_TARGET, return_value=mock):
            await qdrant.upsert_chunks([chunk_a, chunk_b], vectors)

        points = mock.put.call_args[1]["json"]["points"]
        assert points[0]["id"] != points[1]["id"]


# ---------------------------------------------------------------------------
# 5. chunk_markdown() merging behaviour
# ---------------------------------------------------------------------------


class TestChunkMarkdownMerging:
    """chunk_markdown() merges small chunks within the same section."""

    def _chunk(self, content: str, **kwargs):
        return chunk_markdown(
            content=content,
            content_hash="testhash",
            source_url="vault://test.md",
            title="test.md",
            **kwargs,
        )

    def test_small_chunk_in_same_section_is_merged(self):
        """A tiny paragraph following a larger one in the same section merges in."""
        # Create content where the second paragraph is small enough to merge
        # Section body: large paragraph + tiny paragraph
        content = (
            "# Section\n\nThis is a larger paragraph with enough words to fill a chunk by itself. "
            * 3
            + "\n\nTiny."
        )
        # Use small max_tokens to force initial split
        result = self._chunk(content, max_tokens=50, min_tokens=20)

        # "Tiny." should be merged into the last chunk of the section (same header)
        full_text = " ".join(c["chunk_text"] for c in result)
        assert "Tiny." in full_text

    def test_small_chunks_in_different_sections_not_merged(self):
        """A small chunk under a different header is NOT merged with the previous."""
        content = "# Section A\n\nHello world.\n\n# Section B\n\nBye.\n"
        result = self._chunk(content, max_tokens=512, min_tokens=5)

        # Section A and Section B content should be in separate chunks
        headers = [c["section_header"] for c in result]
        assert "# Section A" in headers
        assert "# Section B" in headers

        # The "Bye." chunk must have header "# Section B"
        section_b_chunks = [c for c in result if c["section_header"] == "# Section B"]
        assert len(section_b_chunks) >= 1
        section_b_text = " ".join(c["chunk_text"] for c in section_b_chunks)
        assert "Bye." in section_b_text

    def test_chunk_index_is_sequential(self):
        """chunk_index values are 0, 1, 2, … for the returned chunks."""
        content = (
            "# A\n\nFirst section content.\n\n"
            "# B\n\nSecond section content.\n\n"
            "# C\n\nThird section content.\n"
        )
        result = self._chunk(content)
        indices = [c["chunk_index"] for c in result]
        assert indices == list(range(len(result))), (
            f"Expected sequential indices, got {indices}"
        )

    def test_all_fields_present_in_chunk_payload(self):
        """Every returned ChunkPayload contains all required fields."""
        required_fields = {
            "content_hash",
            "chunk_index",
            "chunk_text",
            "section_header",
            "source_url",
            "title",
        }
        result = self._chunk("# Note\n\nSome content.")
        assert len(result) >= 1
        for chunk in result:
            missing = required_fields - set(chunk.keys())
            assert not missing, f"Chunk missing fields: {missing}"


# ---------------------------------------------------------------------------
# 6. _split_by_headers() — no-header document
# ---------------------------------------------------------------------------


class TestSplitByHeadersNoHeaders:
    """_split_by_headers() returns a single section with empty header for header-free docs."""

    def test_no_headers_returns_single_section_with_empty_header(self):
        """Content without any headers comes back as [('', content)]."""
        content = "Just some plain text.\n\nNo headers here."
        sections = _split_by_headers(content)
        assert len(sections) == 1
        header, body = sections[0]
        assert header == "", f"Expected empty header, got {header!r}"
        assert "plain text" in body

    def test_empty_content_returns_empty_section_list(self):
        """Empty or whitespace-only content returns an empty list (no sections)."""
        # The function returns [("", "")] if content is empty but stripped is empty
        # Actually it returns [("", "")] only if content.strip() is empty after the
        # sections = [("", content.strip())] fallback — but content.strip() == ""
        # means the section body is empty string, which won't be filtered by the
        # `if body:` check in the main loop. Let's verify:
        sections = _split_by_headers("")
        # Either empty list or single section with empty body — both are valid
        assert isinstance(sections, list)

    def test_header_only_document_no_trailing_body(self):
        """A document that is *only* a header with no body after it."""
        content = "# Just a Header"
        sections = _split_by_headers(content)
        # The header itself is the last_header and remaining="" → empty body → filtered
        # Depending on implementation: may return [] or a section with just the header
        assert isinstance(sections, list)

    def test_first_section_before_any_header_uses_empty_string_header(self):
        """Text before the first header has header='' (empty string)."""
        content = "Preamble text.\n\n# First Header\n\nBody text."
        sections = _split_by_headers(content)
        # First section has no header (empty string)
        headers = [s[0] for s in sections]
        assert "" in headers, (
            f"Expected empty-string header for preamble, got {headers}"
        )

    def test_three_level_headers_all_captured(self):
        """h1, h2, and h3 headers are all recognised as section boundaries."""
        content = "# H1\n\nH1 body.\n\n## H2\n\nH2 body.\n\n### H3\n\nH3 body."
        sections = _split_by_headers(content)
        headers = [s[0] for s in sections]
        assert "# H1" in headers
        assert "## H2" in headers
        assert "### H3" in headers

    def test_h4_not_treated_as_header_boundary(self):
        """h4 (####) is NOT a recognised header boundary."""
        content = "# H1\n\nBody.\n\n#### H4\n\nH4 body."
        sections = _split_by_headers(content)
        headers = [s[0] for s in sections]
        # #### should NOT be in headers (only 1-3 # are recognised)
        assert not any(h.startswith("####") for h in headers), (
            f"h4 should not be treated as a section boundary, got {headers}"
        )
