"""Additional coverage tests for knowledge/reconciler.py.

Fills gaps identified in the coverage review:
- _slugify: empty-string fallback ("note"), Unicode NFKD normalization,
  input that normalises to all non-ASCII.
- _write_back_id else branch: no-frontmatter path.
- _walk missing root: early-return when processed_root does not exist.
- _walk FileNotFoundError race: file deleted between rglob and read_bytes.
- Empty-body fallback: whitespace-only body triggers body-or-title substitution.
- UnicodeDecodeError in _read_text: logged and re-raised; outer loop counts failure.
- Nested rollback failures: the three logger.exception("rollback after ... failed")
  paths are exercised via mock injection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Note
from knowledge.reconciler import Reconciler, ReconcileStats, _slugify
from knowledge.store import KnowledgeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stats(
    *, upserted=0, deleted=0, unchanged=0, failed=0, skipped_locked=0
) -> ReconcileStats:
    return ReconcileStats(
        upserted=upserted,
        deleted=deleted,
        unchanged=unchanged,
        failed=failed,
        skipped_locked=skipped_locked,
    )


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


@pytest.fixture
def embed_client():
    client = AsyncMock()
    client.embed_batch.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
    return client


@pytest.fixture
def reconciler(session, embed_client, tmp_path):
    processed = tmp_path / "_processed"
    processed.mkdir()
    return Reconciler(
        store=KnowledgeStore(session=session),
        embed_client=embed_client,
        vault_root=tmp_path,
    )


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / "_processed" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _write_bytes(tmp_path: Path, rel: str, content: bytes) -> None:
    p = tmp_path / "_processed" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_normal_ascii_title(self):
        assert _slugify("Hello World") == "hello-world"

    def test_empty_string_returns_note(self):
        """Empty input falls back to the literal string 'note'."""
        assert _slugify("") == "note"

    def test_unicode_normalized_to_ascii(self):
        """Unicode characters are NFKD-normalised then ASCII-transcribed."""
        # 'é' decomposes to 'e' + combining acute accent; the accent is
        # dropped by the ASCII encode, leaving 'e'.
        assert _slugify("Café") == "cafe"

    def test_all_non_ascii_falls_back_to_note(self):
        """A title that contains only non-ASCII characters (after NFKD) returns 'note'."""
        # Chinese characters have no ASCII equivalent after NFKD decomposition.
        assert _slugify("中文") == "note"

    def test_leading_trailing_hyphens_stripped(self):
        """Hyphens created from leading/trailing non-alnum chars are stripped."""
        assert _slugify("  --hello--  ") == "hello"

    def test_multiple_spaces_collapsed_to_single_hyphen(self):
        assert _slugify("foo  bar") == "foo-bar"

    def test_numbers_preserved(self):
        assert _slugify("Chapter 2") == "chapter-2"

    def test_special_chars_become_hyphens(self):
        assert _slugify("foo/bar.baz") == "foo-bar-baz"


# ---------------------------------------------------------------------------
# _write_back_id: no-frontmatter (else) branch
# ---------------------------------------------------------------------------


class TestWriteBackIdElseBranch:
    def test_no_frontmatter_prepends_yaml_block(self, tmp_path):
        """When raw does not start with '---', a new frontmatter block is prepended."""
        rec = Reconciler(
            store=MagicMock(),
            embed_client=MagicMock(),
            vault_root=tmp_path,
        )
        note_file = tmp_path / "bare.md"
        raw = "Just plain text.\nNo frontmatter at all.\n"
        note_file.write_text(raw, encoding="utf-8")

        new_raw, new_hash = rec._write_back_id(note_file, raw, "my-note-id")

        assert new_raw.startswith("---\nid: my-note-id\n---\n")
        assert "Just plain text." in new_raw
        # Hash must match the new content
        expected_hash = hashlib.sha256(new_raw.encode("utf-8")).hexdigest()
        assert new_hash == expected_hash
        # File on disk updated
        assert note_file.read_text(encoding="utf-8") == new_raw

    def test_no_frontmatter_uses_lf_line_endings(self, tmp_path):
        """The no-frontmatter else branch always uses LF, not CRLF."""
        rec = Reconciler(
            store=MagicMock(),
            embed_client=MagicMock(),
            vault_root=tmp_path,
        )
        note_file = tmp_path / "plain.md"
        raw = "Plain content."
        note_file.write_text(raw, encoding="utf-8")

        new_raw, _ = rec._write_back_id(note_file, raw, "plain-id")

        # Verify LF not CRLF
        assert "\r\n" not in new_raw


# ---------------------------------------------------------------------------
# _walk: missing processed_root
# ---------------------------------------------------------------------------


class TestWalkMissingRoot:
    @pytest.mark.asyncio
    async def test_walk_returns_empty_when_processed_root_absent(
        self, session, embed_client, tmp_path
    ):
        """_walk returns {} immediately when processed_root does not exist.

        The reconciler fixture always creates processed_root, so this test
        builds a Reconciler without pre-creating it.
        """
        # Do NOT create processed_root
        r = Reconciler(
            store=KnowledgeStore(session=session),
            embed_client=embed_client,
            vault_root=tmp_path,
        )
        assert not r.processed_root.exists()
        result = await r.run()
        assert result == _stats()


# ---------------------------------------------------------------------------
# _walk: FileNotFoundError race between rglob and read_bytes
# ---------------------------------------------------------------------------


class TestWalkFileNotFoundRace:
    @pytest.mark.asyncio
    async def test_walk_skips_file_deleted_after_rglob(
        self, reconciler, tmp_path, session
    ):
        """A FileNotFoundError from read_bytes (file vanished between rglob and
        read) causes the file to be absent from the walk result — it is neither
        re-ingested nor deleted in this cycle.
        """
        _write(tmp_path, "vanish.md", "---\nid: v\ntitle: V\n---\nContent.")
        # First run: ingest the file normally.
        await reconciler.run()
        note = session.scalars(select(Note)).first()
        assert note is not None

        # Second run: simulate the file vanishing between rglob and read_bytes.
        target = tmp_path / "_processed" / "vanish.md"
        original_read_bytes = Path.read_bytes

        def raise_fnf(p: Path) -> bytes:
            if p == target:
                raise FileNotFoundError(f"gone: {p}")
            return original_read_bytes(p)

        with patch.object(Path, "read_bytes", raise_fnf):
            result = await reconciler.run()

        # File not found → absent from walk → neither unchanged nor deleted
        # (the note stays in the DB from the first run because nothing triggered
        # a delete). Stats should show 0 upserted, 0 deleted, 0 unchanged.
        assert result.upserted == 0
        assert result.deleted == 0


# ---------------------------------------------------------------------------
# Empty-body fallback: whitespace-only body triggers body-or-title substitution
# ---------------------------------------------------------------------------


class TestEmptyBodyFallback:
    @pytest.mark.asyncio
    async def test_whitespace_only_body_uses_title_as_chunk_text(
        self, reconciler, session, tmp_path
    ):
        """When the note body is whitespace-only, chunk_markdown returns [].
        _ingest_one then substitutes ``body or title`` as the single chunk text,
        so the title is used for embedding.
        """
        # Body is whitespace only
        _write(tmp_path, "empty.md", "---\nid: empty\ntitle: My Title\n---\n   \n")
        result = await reconciler.run()
        assert result == _stats(upserted=1)
        note = session.scalars(select(Note)).first()
        assert note is not None
        assert note.title == "My Title"

    @pytest.mark.asyncio
    async def test_truly_empty_body_uses_title_as_chunk_text(
        self, reconciler, session, tmp_path
    ):
        """A note with an empty body (no text after frontmatter) also uses the title."""
        _write(tmp_path, "notitle.md", "---\nid: notext\ntitle: Fallback Title\n---\n")
        result = await reconciler.run()
        assert result == _stats(upserted=1)
        note = session.scalars(select(Note)).first()
        assert note is not None
        assert note.title == "Fallback Title"


# ---------------------------------------------------------------------------
# UnicodeDecodeError in _read_text
# ---------------------------------------------------------------------------


class TestUnicodeDecodeError:
    @pytest.mark.asyncio
    async def test_unicode_decode_error_increments_failed(
        self, reconciler, tmp_path
    ):
        """A file with invalid UTF-8 bytes causes _read_text to log a warning
        and re-raise UnicodeDecodeError. The outer run() loop must catch it,
        increment stats.failed, and continue.
        """
        # Write a file with valid UTF-8 text first so it appears in _walk.
        _write(tmp_path, "bad.md", "---\nid: bad\ntitle: Bad\n---\nContent.")
        # Override _read_text to simulate UnicodeDecodeError.
        original_read_text = reconciler._read_text

        def raise_unicode(path: Path) -> str:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        reconciler._read_text = raise_unicode  # type: ignore[method-assign]
        result = await reconciler.run()
        reconciler._read_text = original_read_text  # type: ignore[method-assign]

        assert result.failed == 1
        assert result.upserted == 0


# ---------------------------------------------------------------------------
# Rollback failure paths (nested logger.exception calls)
# ---------------------------------------------------------------------------


class TestRollbackFailurePaths:
    @pytest.mark.asyncio
    async def test_rollback_after_delete_failure_is_logged(
        self, reconciler, tmp_path, session, caplog
    ):
        """When delete_note raises AND session.rollback also raises,
        the nested exception is logged and the run continues normally.
        """
        import logging

        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody.")
        await reconciler.run()
        (tmp_path / "_processed" / "a.md").unlink()

        original_delete = reconciler.store.delete_note

        def boom_delete(path: str) -> None:
            raise RuntimeError("delete boom")

        def boom_rollback() -> None:
            raise RuntimeError("rollback boom")

        reconciler.store.delete_note = boom_delete  # type: ignore[method-assign]
        reconciler.store.session.rollback = boom_rollback  # type: ignore[method-assign]

        with caplog.at_level(logging.ERROR, logger="monolith.knowledge.reconciler"):
            result = await reconciler.run()

        assert result.failed == 1
        assert any("rollback after delete" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_rollback_after_ingest_failure_is_logged(
        self, reconciler, tmp_path, caplog
    ):
        """When embed_batch raises AND session.rollback also raises,
        the nested exception is logged and the run continues normally.
        """
        import logging

        _write(tmp_path, "b.md", "---\nid: b\ntitle: B\n---\nBody.")

        def boom_embed(texts):
            raise RuntimeError("embed boom")

        reconciler.embed_client.embed_batch.side_effect = boom_embed

        def boom_rollback() -> None:
            raise RuntimeError("rollback boom")

        reconciler.store.session.rollback = boom_rollback  # type: ignore[method-assign]

        with caplog.at_level(logging.ERROR, logger="monolith.knowledge.reconciler"):
            result = await reconciler.run()

        assert result.failed == 1
        assert any("rollback after failure" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_rollback_after_frontmatter_error_is_logged(
        self, reconciler, tmp_path, caplog
    ):
        """When frontmatter parsing raises AND session.rollback also raises,
        the nested exception is logged and the run continues normally.
        """
        import logging

        _write(tmp_path, "c.md", "---\ntitle: [unterminated\n---\nBody.")

        def boom_rollback() -> None:
            raise RuntimeError("rollback boom")

        reconciler.store.session.rollback = boom_rollback  # type: ignore[method-assign]

        with caplog.at_level(logging.ERROR, logger="monolith.knowledge.reconciler"):
            result = await reconciler.run()

        assert result.failed == 1
        assert any("rollback after frontmatter" in r.message for r in caplog.records)
