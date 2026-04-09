"""Tests for the vault reconciler."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Chunk, Note, NoteLink
from knowledge.reconciler import Reconciler, ReconcileStats, _slugify


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


from knowledge.store import KnowledgeStore


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
    p.write_text(content)


def _write_bytes(tmp_path: Path, rel: str, content: bytes) -> None:
    p = tmp_path / "_processed" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


class TestReconciler:
    @pytest.mark.asyncio
    async def test_empty_vault(self, reconciler):
        result = await reconciler.run()
        assert result == _stats()

    @pytest.mark.asyncio
    async def test_adds_one_file_with_id(self, reconciler, session, tmp_path):
        _write(tmp_path, "a.md", "---\nid: a-id\ntitle: A\n---\nBody.")
        result = await reconciler.run()
        assert result == _stats(upserted=1)
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].title == "A"
        assert notes[0].note_id == "a-id"

    @pytest.mark.asyncio
    async def test_missing_id_is_backfilled_to_file(
        self, reconciler, session, tmp_path
    ):
        _write(tmp_path, "a.md", "---\ntitle: Hello World\n---\nBody.")
        await reconciler.run()
        new_raw = (tmp_path / "_processed" / "a.md").read_text()
        assert "id: hello-world" in new_raw
        note = session.scalars(select(Note)).first()
        assert note.note_id == "hello-world"

    @pytest.mark.asyncio
    async def test_readonly_vault_with_missing_id_skips_file(
        self, reconciler, session, tmp_path
    ):
        _write(tmp_path, "a.md", "---\ntitle: Read Only\n---\nBody.")

        def deny(abs_path, raw, note_id):
            # Linux EROFS raises plain OSError(errno=30), not
            # PermissionError. The ingest path must catch the broader
            # OSError type; a previous bug caught only PermissionError
            # and let EROFS tank the whole reconcile cycle.
            raise OSError(30, "Read-only file system")

        reconciler._write_back_id = deny  # type: ignore[method-assign]
        # The read-only error is classified as a partial failure: the
        # outer run() loop catches it, increments stats.failed, and
        # returns normally. A single bad file must not abort the job.
        result = await reconciler.run()
        assert result == _stats(failed=1)
        assert list(session.scalars(select(Note))) == []

    @pytest.mark.asyncio
    async def test_edges_block_persists_typed_links(
        self, reconciler, session, tmp_path
    ):
        _write(
            tmp_path,
            "a.md",
            "---\nid: a\ntitle: A\nedges:\n  refines: [parent]\n  related: [b, c]\n---\nBody.",
        )
        await reconciler.run()
        rows = list(session.scalars(select(NoteLink)))
        assert {(r.kind, r.edge_type, r.target_id) for r in rows} == {
            ("edge", "refines", "parent"),
            ("edge", "related", "b"),
            ("edge", "related", "c"),
        }

    @pytest.mark.asyncio
    async def test_no_changes_skips_embedding(self, reconciler, embed_client, tmp_path):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody.")
        await reconciler.run()
        embed_client.embed_batch.reset_mock()
        result = await reconciler.run()
        assert result == _stats(unchanged=1)
        embed_client.embed_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_edited_body_re_embeds(self, reconciler, tmp_path):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nv1.")
        await reconciler.run()
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nv2.")
        result = await reconciler.run()
        assert result == _stats(upserted=1)

    @pytest.mark.asyncio
    async def test_edited_frontmatter_only_re_embeds(
        self, reconciler, tmp_path, session
    ):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody.")
        await reconciler.run()
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\ntype: paper\n---\nBody.")
        result = await reconciler.run()
        assert result == _stats(upserted=1)
        note = session.scalars(select(Note)).first()
        assert note.type == "paper"

    @pytest.mark.asyncio
    async def test_deletes_removed_file(self, reconciler, tmp_path, session):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody.")
        await reconciler.run()
        (tmp_path / "_processed" / "a.md").unlink()
        result = await reconciler.run()
        assert result == _stats(deleted=1)
        assert list(session.scalars(select(Note))) == []
        assert list(session.scalars(select(Chunk))) == []

    @pytest.mark.asyncio
    async def test_broken_frontmatter_is_skipped_without_overwrite(
        self, reconciler, tmp_path, session
    ):
        # First, ingest a valid version of the file.
        _write(tmp_path, "a.md", "---\nid: a\ntitle: Good\n---\nBody.")
        await reconciler.run()
        assert session.scalars(select(Note)).first().title == "Good"

        # Then corrupt the frontmatter. The reconciler must skip the file
        # and leave the existing row intact — never overwrite with empty
        # defaults.
        _write(tmp_path, "a.md", "---\ntitle: [unterminated\n---\nBody.")
        result = await reconciler.run()
        assert result == _stats(failed=1)
        preserved = session.scalars(select(Note)).first()
        assert preserved.title == "Good"
        assert preserved.note_id == "a"

    @pytest.mark.asyncio
    async def test_broken_frontmatter_on_new_file_is_skipped(
        self, reconciler, tmp_path, session
    ):
        _write(tmp_path, "a.md", "---\ntitle: [unterminated\n---\nBody.")
        result = await reconciler.run()
        assert result == _stats(failed=1)
        assert list(session.scalars(select(Note))) == []

    @pytest.mark.asyncio
    async def test_partial_failure_persists_other_notes(
        self, reconciler, embed_client, tmp_path, session
    ):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody A.")
        _write(tmp_path, "b.md", "---\nid: b\ntitle: B\n---\nBody B.")
        _write(tmp_path, "c.md", "---\nid: c\ntitle: C\n---\nBody C.")

        call = {"n": 0}

        async def flaky(texts):
            call["n"] += 1
            if call["n"] == 2:
                raise RuntimeError("embed boom")
            return [[0.1] * 1024 for _ in texts]

        embed_client.embed_batch.side_effect = flaky
        # A single ingest failure must NOT abort the entire reconcile:
        # the error is logged, counted in stats.failed, and the loop
        # continues to the next file.
        result = await reconciler.run()
        assert result == _stats(upserted=2, failed=1)
        titles = sorted(n.title for n in session.scalars(select(Note)))
        assert "B" not in titles
        assert len(titles) == 2

    @pytest.mark.asyncio
    async def test_body_wikilinks_persist_as_link_kind_rows(
        self, reconciler, session, tmp_path
    ):
        _write(
            tmp_path,
            "a.md",
            "---\nid: a\ntitle: A\n---\n# Title\n\nbody with [[Foo]] and [[Bar|the bar]]\n",
        )
        await reconciler.run()
        rows = list(session.scalars(select(NoteLink)))
        assert len(rows) == 2
        by_target = {r.target_id: r for r in rows}
        assert set(by_target) == {"Foo", "Bar"}
        for r in rows:
            assert r.kind == "link"
            assert r.edge_type is None
        assert by_target["Foo"].target_title is None
        assert by_target["Bar"].target_title == "the bar"

    @pytest.mark.asyncio
    async def test_crlf_file_can_be_ingested_and_id_backfilled(
        self, reconciler, session, tmp_path
    ):
        # Windows-authored notes use CRLF line endings. The file should
        # ingest successfully, and when we backfill a missing id the
        # rewritten file should preserve CRLF.
        _write_bytes(
            tmp_path,
            "crlf.md",
            b"---\r\ntitle: CRLF Backfill\r\n---\r\nBody.\r\n",
        )
        await reconciler.run()
        note = session.scalars(select(Note)).first()
        assert note is not None
        assert note.title == "CRLF Backfill"
        assert note.note_id == "crlf-backfill"
        raw = (tmp_path / "_processed" / "crlf.md").read_bytes()
        assert b"\r\nid: crlf-backfill\r\n" in raw
        # Sanity: no stray LF-only lines introduced.
        assert b"\r\nid: crlf-backfill\n" not in raw

    @pytest.mark.asyncio
    async def test_file_disappears_mid_cycle(self, reconciler, tmp_path):
        _write(tmp_path, "ghost.md", "---\nid: g\ntitle: G\n---\nx.")
        original = reconciler._read_text  # type: ignore[attr-defined]

        def vanish(path):
            raise FileNotFoundError(path)

        reconciler._read_text = vanish  # type: ignore[attr-defined]
        result = await reconciler.run()
        assert result.upserted == 0
        reconciler._read_text = original  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_walk_permission_error_preserves_previous_hash(
        self, reconciler, tmp_path, session
    ):
        """A PermissionError while reading a file in _walk carries forward its
        previous hash so the file is neither deleted nor re-ingested.

        This mirrors test_file_disappears_mid_cycle but targets the _walk phase
        rather than the ingest phase. A transient permission problem on a mounted
        vault (e.g. NFS hiccup) must not cause a stale deletion of the note row.
        """
        _write(tmp_path, "locked.md", "---\nid: locked\ntitle: Locked\n---\nBody.")
        await reconciler.run()
        assert session.scalars(select(Note)).first() is not None

        target = tmp_path / "_processed" / "locked.md"
        original_read_bytes = Path.read_bytes

        def raise_perm(p: Path) -> bytes:
            if p == target:
                raise PermissionError(f"Permission denied: {p}")
            return original_read_bytes(p)

        with patch.object(Path, "read_bytes", raise_perm):
            result = await reconciler.run()

        # Previous hash is carried forward → counted as unchanged, NOT deleted.
        assert result == _stats(unchanged=1)
        # Database row must still exist — a transient read error must not
        # trigger cascade deletion of the knowledge graph node.
        assert session.scalars(select(Note)).first() is not None

    @pytest.mark.asyncio
    async def test_delete_loop_partial_failure_continues(
        self, reconciler, tmp_path, session
    ):
        """When deleting multiple removed notes and one raises, the rest are
        still deleted and the run returns normally with accurate stats.

        The delete loop uses partial-failure isolation: each failure is logged,
        counted in stats.failed, and the loop continues to the next path.
        """
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody A.")
        _write(tmp_path, "b.md", "---\nid: b\ntitle: B\n---\nBody B.")
        await reconciler.run()
        # Remove both files so both paths appear in to_delete.
        (tmp_path / "_processed" / "a.md").unlink()
        (tmp_path / "_processed" / "b.md").unlink()

        original_delete = reconciler.store.delete_note
        calls: list[str] = []

        def failing_delete(path: str) -> None:
            calls.append(path)
            if path.endswith("a.md"):
                raise RuntimeError("delete boom for a.md")
            return original_delete(path)

        reconciler.store.delete_note = failing_delete  # type: ignore[method-assign]
        result = await reconciler.run()
        reconciler.store.delete_note = original_delete  # type: ignore[method-assign]

        # Both paths were attempted; one delete succeeded, one failed.
        assert result == _stats(deleted=1, failed=1)
        assert len(calls) == 2
        # "a" row survives (delete raised); "b" row is gone.
        note_ids = {n.note_id for n in session.scalars(select(Note))}
        assert "a" in note_ids
        assert "b" not in note_ids

    @pytest.mark.asyncio
    async def test_readonly_vault_mixed_files_full_cycle(
        self, reconciler, session, tmp_path
    ):
        """On a read-only vault a reconcile with mixed files (some with IDs,
        some without) processes all readable files and skips only the ones that
        need a backfill — without aborting the entire run.

        Files that already carry a frontmatter `id:` need no write-back and
        must be ingested normally. Files that lack an ID would require a
        write-back; on a read-only mount that OSError is caught and counted
        as a per-file failure while the loop continues.
        """
        _write(tmp_path, "has-id.md", "---\nid: has-id\ntitle: Has ID\n---\nBody.")
        _write(tmp_path, "no-id.md", "---\ntitle: No ID\n---\nBody.")

        def deny(abs_path: Path, raw: str, note_id: str) -> tuple[str, str]:
            raise OSError(30, "Read-only file system")

        reconciler._write_back_id = deny  # type: ignore[method-assign]
        result = await reconciler.run()

        # File with ID ingested; file without ID (needs backfill on r/o vault) skipped.
        assert result == _stats(upserted=1, failed=1)
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].note_id == "has-id"


# ---------------------------------------------------------------------------
# _slugify — direct unit tests
# ---------------------------------------------------------------------------


class TestSlugify:
    """Direct tests for the module-level _slugify helper."""

    def test_simple_lowercase(self):
        """Lowercase ASCII words are joined with hyphens."""
        assert _slugify("hello world") == "hello-world"

    def test_uppercase_is_lowercased(self):
        """Uppercase letters are folded to lowercase."""
        assert _slugify("Hello World") == "hello-world"

    def test_unicode_normalized_to_ascii(self):
        """Accented characters are transliterated; the accent is dropped."""
        assert _slugify("Café") == "cafe"
        assert _slugify("naïve") == "naive"

    def test_all_non_ascii_returns_note(self):
        """If the text produces an empty slug after stripping non-ASCII, 'note' is returned."""
        # CJK characters produce no ASCII output; the sentinel 'note' is returned.
        assert _slugify("日本語") == "note"

    def test_empty_string_returns_note(self):
        """Empty input returns the 'note' sentinel."""
        assert _slugify("") == "note"

    def test_leading_trailing_separators_stripped(self):
        """Leading and trailing hyphens produced by non-alnum chars are stripped."""
        assert _slugify("---foo---") == "foo"

    def test_punctuation_collapsed_to_single_hyphen(self):
        """Multiple consecutive non-alnum characters collapse into a single hyphen."""
        assert _slugify("foo: bar, baz!") == "foo-bar-baz"

    def test_numbers_preserved(self):
        """Digits are treated as alphanumeric and preserved in the slug."""
        assert _slugify("Note 42") == "note-42"

    def test_already_slug_like(self):
        """Input that is already slug-like passes through unchanged."""
        assert _slugify("already-slug") == "already-slug"


# ---------------------------------------------------------------------------
# _write_back_id — no-frontmatter branch
# ---------------------------------------------------------------------------


class TestWriteBackIdNoFrontmatter:
    """Tests for the branch of _write_back_id where the file has no frontmatter."""

    def test_no_frontmatter_wraps_in_new_block(self, reconciler, tmp_path):
        """Plain body with no frontmatter gets a new frontmatter block prepended."""
        target = tmp_path / "plain.md"
        raw = "Just some plain content without any frontmatter.\n"
        target.write_text(raw, encoding="utf-8")

        new_raw, new_hash = reconciler._write_back_id(target, raw, "plain-note")

        assert new_raw.startswith("---\nid: plain-note\n---\n")
        assert "Just some plain content" in new_raw
        assert target.read_text(encoding="utf-8") == new_raw

    def test_no_frontmatter_uses_lf_line_endings(self, reconciler, tmp_path):
        """When there is no existing frontmatter the injected block uses LF, not CRLF."""
        target = tmp_path / "nofm.md"
        raw = "Body.\n"
        target.write_text(raw, encoding="utf-8")

        new_raw, _ = reconciler._write_back_id(target, raw, "my-note")

        assert "\r\n" not in new_raw

    def test_no_frontmatter_hash_matches_written_content(self, reconciler, tmp_path):
        """The returned content_hash equals sha256 of the new file content."""
        import hashlib

        target = tmp_path / "hash_check.md"
        raw = "Some body text.\n"
        target.write_text(raw, encoding="utf-8")

        new_raw, new_hash = reconciler._write_back_id(target, raw, "hash-check")

        expected = hashlib.sha256(new_raw.encode("utf-8")).hexdigest()
        assert new_hash == expected

    @pytest.mark.asyncio
    async def test_no_frontmatter_file_ingested_end_to_end(
        self, reconciler, session, tmp_path
    ):
        """A file with no frontmatter at all is auto-backfilled and ingested."""
        _write(tmp_path, "bare.md", "# Bare Note\n\nJust a body, no frontmatter.\n")
        result = await reconciler.run()

        assert result == _stats(upserted=1)
        note = session.scalars(select(Note)).first()
        assert note is not None
        # Slug is derived from the filename stem ("bare") when there is no title
        # in frontmatter — the _ingest_one path falls back to Path(rel_path).stem.
        assert note.note_id == "bare"
        # Confirm the backfilled id was written to disk.
        written = (tmp_path / "_processed" / "bare.md").read_text()
        assert "id: bare" in written
