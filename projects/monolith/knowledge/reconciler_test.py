"""Tests for the vault reconciler."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Chunk, Note, NoteLink
from knowledge.reconciler import Reconciler
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


class TestReconciler:
    @pytest.mark.asyncio
    async def test_empty_vault(self, reconciler):
        result = await reconciler.run()
        assert result == (0, 0, 0)

    @pytest.mark.asyncio
    async def test_adds_one_file_with_id(self, reconciler, session, tmp_path):
        _write(tmp_path, "a.md", "---\nid: a-id\ntitle: A\n---\nBody.")
        result = await reconciler.run()
        assert result == (1, 0, 0)
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
        self, reconciler, session, tmp_path, monkeypatch
    ):
        _write(tmp_path, "a.md", "---\ntitle: Read Only\n---\nBody.")
        target = tmp_path / "_processed" / "a.md"

        original_write = Path.write_text

        def deny(self, *a, **kw):
            if self == target:
                raise PermissionError("read-only fs")
            return original_write(self, *a, **kw)

        monkeypatch.setattr(Path, "write_text", deny)
        # The read-only error is classified as a partial failure: the
        # outer run() loop catches it, continues, and re-raises at the
        # end. The file must NOT have been ingested.
        with pytest.raises(Exception):
            await reconciler.run()
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
        assert result == (0, 0, 1)
        embed_client.embed_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_edited_body_re_embeds(self, reconciler, tmp_path):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nv1.")
        await reconciler.run()
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nv2.")
        result = await reconciler.run()
        assert result == (1, 0, 0)

    @pytest.mark.asyncio
    async def test_edited_frontmatter_only_re_embeds(
        self, reconciler, tmp_path, session
    ):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody.")
        await reconciler.run()
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\ntype: paper\n---\nBody.")
        result = await reconciler.run()
        assert result == (1, 0, 0)
        note = session.scalars(select(Note)).first()
        assert note.type == "paper"

    @pytest.mark.asyncio
    async def test_deletes_removed_file(self, reconciler, tmp_path, session):
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody.")
        await reconciler.run()
        (tmp_path / "_processed" / "a.md").unlink()
        result = await reconciler.run()
        assert result == (0, 1, 0)
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
        assert result == (0, 0, 0)
        preserved = session.scalars(select(Note)).first()
        assert preserved.title == "Good"
        assert preserved.note_id == "a"

    @pytest.mark.asyncio
    async def test_broken_frontmatter_on_new_file_is_skipped(
        self, reconciler, tmp_path, session
    ):
        _write(tmp_path, "a.md", "---\ntitle: [unterminated\n---\nBody.")
        result = await reconciler.run()
        assert result == (0, 0, 0)
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
        with pytest.raises(RuntimeError):
            await reconciler.run()
        titles = sorted(n.title for n in session.scalars(select(Note)))
        assert "B" not in titles
        assert len(titles) == 2

    @pytest.mark.asyncio
    async def test_file_disappears_mid_cycle(self, reconciler, tmp_path):
        _write(tmp_path, "ghost.md", "---\nid: g\ntitle: G\n---\nx.")
        original = reconciler._read_text  # type: ignore[attr-defined]

        def vanish(path):
            raise FileNotFoundError(path)

        reconciler._read_text = vanish  # type: ignore[attr-defined]
        result = await reconciler.run()
        assert result[0] == 0
        reconciler._read_text = original  # type: ignore[attr-defined]
