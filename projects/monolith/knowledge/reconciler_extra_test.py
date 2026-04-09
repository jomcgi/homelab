"""Additional coverage for the vault reconciler.

Fills gaps not addressed by reconciler_test.py:

1. Advisory-lock skipped_locked path — the ``skipped_locked`` counter in
   ``ReconcileStats`` is incremented when ``_ingest_one`` returns ``False``
   (the PostgreSQL advisory-lock-busy branch).  In the SQLite test fixture
   this branch is never reached; here we exercise it directly by
   monkeypatching ``_ingest_one`` to return ``False``.

2. PermissionError on a *new* (never-indexed) file — the ``_walk`` method
   carries forward a previous hash only if ``rel in previous_indexed``.  For
   a brand-new file that the reconciler has never seen, a ``PermissionError``
   means the file is silently omitted from ``on_disk``; it never enters
   ``to_upsert`` and stats remain zero.  This is the safe/conservative
   behaviour and must not regress.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.models import Note
from knowledge.reconciler import Reconciler, ReconcileStats
from knowledge.store import KnowledgeStore
from sqlmodel import select


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
    p.write_text(content)


# ---------------------------------------------------------------------------
# Advisory-lock skipped_locked path
# ---------------------------------------------------------------------------


class TestSkippedLockedCounter:
    """The skipped_locked stat is incremented when _ingest_one returns False.

    In production the advisory-lock branch is Postgres-only and unreachable in
    SQLite tests. We simulate it by monkeypatching _ingest_one to return False
    so that the run() loop's ``else: skipped_locked += 1`` branch is covered.
    """

    @pytest.mark.asyncio
    async def test_single_file_skipped_locked(self, reconciler, tmp_path):
        """When _ingest_one returns False for one file, skipped_locked == 1."""
        _write(tmp_path, "note.md", "---\nid: note\ntitle: Note\n---\nBody.")

        async def lock_busy(rel_path: str, content_hash: str) -> bool:
            return False  # simulate advisory lock held by another worker

        reconciler._ingest_one = lock_busy  # type: ignore[method-assign]
        result = await reconciler.run()

        assert result == _stats(skipped_locked=1)

    @pytest.mark.asyncio
    async def test_multiple_files_all_skipped_locked(self, reconciler, tmp_path):
        """When every file returns advisory-lock-busy, skipped_locked equals
        the number of files queued for upsert.
        """
        _write(tmp_path, "a.md", "---\nid: a\ntitle: A\n---\nBody A.")
        _write(tmp_path, "b.md", "---\nid: b\ntitle: B\n---\nBody B.")
        _write(tmp_path, "c.md", "---\nid: c\ntitle: C\n---\nBody C.")

        async def lock_busy(rel_path: str, content_hash: str) -> bool:
            return False

        reconciler._ingest_one = lock_busy  # type: ignore[method-assign]
        result = await reconciler.run()

        assert result == _stats(skipped_locked=3)

    @pytest.mark.asyncio
    async def test_mixed_ingested_and_skipped_locked(
        self, reconciler, embed_client, tmp_path
    ):
        """When some files are locked and others are ingested normally the
        counters are tracked independently.
        """
        _write(tmp_path, "good.md", "---\nid: good\ntitle: Good\n---\nBody.")
        _write(tmp_path, "busy.md", "---\nid: busy\ntitle: Busy\n---\nBody.")

        original_ingest = reconciler._ingest_one

        async def partial_lock(rel_path: str, content_hash: str) -> bool:
            if "busy" in rel_path:
                return False
            return await original_ingest(rel_path, content_hash)

        reconciler._ingest_one = partial_lock  # type: ignore[method-assign]
        result = await reconciler.run()

        assert result.upserted == 1
        assert result.skipped_locked == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_skipped_locked_file_not_added_to_db(
        self, reconciler, session, tmp_path
    ):
        """A file that returns False from _ingest_one must NOT be inserted into
        the database — the session is never flushed for it.
        """
        _write(tmp_path, "skip.md", "---\nid: skip\ntitle: Skip\n---\nBody.")

        async def lock_busy(rel_path: str, content_hash: str) -> bool:
            return False

        reconciler._ingest_one = lock_busy  # type: ignore[method-assign]
        await reconciler.run()

        notes = list(session.scalars(select(Note)))
        assert notes == [], (
            "No Note row should be persisted when _ingest_one returns False "
            "(advisory-lock-busy path)"
        )


# ---------------------------------------------------------------------------
# PermissionError on a new (never-indexed) file
# ---------------------------------------------------------------------------


class TestWalkPermissionErrorNewFile:
    """A PermissionError on a file the reconciler has never seen before results
    in the file being silently omitted — it is not counted as failed, upserted,
    or unchanged.

    This contrasts with the *previously-indexed* PermissionError case (covered
    in reconciler_test.py::test_walk_permission_error_preserves_previous_hash)
    where the old hash is carried forward and the file is counted as unchanged.
    """

    @pytest.mark.asyncio
    async def test_permission_error_on_new_file_yields_zero_stats(
        self, reconciler, tmp_path
    ):
        """When a brand-new file raises PermissionError in _walk, all stats
        remain zero — the file is simply not included in the on_disk snapshot.
        """
        target = tmp_path / "_processed" / "brand_new.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nid: new\ntitle: New\n---\nBody.")

        original_read_bytes = Path.read_bytes

        def raise_perm(p: Path) -> bytes:
            if p == target:
                raise PermissionError(f"Permission denied: {p}")
            return original_read_bytes(p)

        with patch.object(Path, "read_bytes", raise_perm):
            result = await reconciler.run()

        # The file was silently skipped — no stat incremented.
        assert result == _stats()

    @pytest.mark.asyncio
    async def test_permission_error_on_new_file_not_in_db(
        self, reconciler, session, tmp_path
    ):
        """A silently-skipped new file must not produce any DB row."""
        target = tmp_path / "_processed" / "silent.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nid: silent\ntitle: Silent\n---\nBody.")

        original_read_bytes = Path.read_bytes

        def raise_perm(p: Path) -> bytes:
            if p == target:
                raise PermissionError(f"Permission denied: {p}")
            return original_read_bytes(p)

        with patch.object(Path, "read_bytes", raise_perm):
            await reconciler.run()

        assert list(session.scalars(select(Note))) == []

    @pytest.mark.asyncio
    async def test_permission_error_new_file_does_not_affect_others(
        self, reconciler, session, tmp_path
    ):
        """A PermissionError on one new file must not prevent other readable
        files from being ingested normally.
        """
        target = tmp_path / "_processed" / "blocked.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nid: blocked\ntitle: Blocked\n---\nBody.")

        _write(
            tmp_path, "readable.md", "---\nid: readable\ntitle: Readable\n---\nBody."
        )

        original_read_bytes = Path.read_bytes

        def raise_perm(p: Path) -> bytes:
            if p == target:
                raise PermissionError(f"Permission denied: {p}")
            return original_read_bytes(p)

        with patch.object(Path, "read_bytes", raise_perm):
            result = await reconciler.run()

        # The readable file is ingested; the blocked one is silently dropped.
        assert result == _stats(upserted=1)
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].note_id == "readable"

    @pytest.mark.asyncio
    async def test_permission_error_new_file_on_subsequent_run_still_skipped(
        self, reconciler, tmp_path
    ):
        """If a new file has a PermissionError every run, it is never indexed
        and no hash is ever stored — it remains silently absent from all cycles.
        """
        target = tmp_path / "_processed" / "always_blocked.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nid: ab\ntitle: Always Blocked\n---\nBody.")

        original_read_bytes = Path.read_bytes

        def raise_perm(p: Path) -> bytes:
            if p == target:
                raise PermissionError(f"Permission denied: {p}")
            return original_read_bytes(p)

        with patch.object(Path, "read_bytes", raise_perm):
            result1 = await reconciler.run()
            result2 = await reconciler.run()

        # Both runs: silently skipped — zero stats.
        assert result1 == _stats()
        assert result2 == _stats()
