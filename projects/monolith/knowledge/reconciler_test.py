"""Tests for the vault reconciler."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Chunk, Note, NoteLink
from knowledge.reconciler import Reconciler, ReconcileStats


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
