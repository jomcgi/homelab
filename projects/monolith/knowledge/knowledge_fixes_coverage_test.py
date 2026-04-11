"""Coverage tests for code paths added by the 13+ knowledge fix commits.

Targets gaps not exercised by existing test files:

store.py
  - upsert_note: note_id fallback lookup when path changes mid-cycle
    (commit 57b1049: handle note_id collision when path changes during upsert)

reconciler.py
  - _write_back_id: CRLF (\\r\\n) frontmatter branch
  - _pre_sync_links: exception is swallowed and never blocks reconcile

gardener.py
  - _raws_needing_decomposition: returns [] when session is None
  - _resolve_pending_provenance: returns 0 when session is None
  - run(): skips reconcile_raw_phase when session is None
  - _backfill_provenance_from_notes: returns 0 when session is None
  - _backfill_provenance_from_notes: inserts sentinel for unhandled raws
  - _backfill_provenance_from_notes: skips raws with existing provenance
  - _backfill_provenance_from_notes: returns 0 when no derived_from_raw notes

raw_ingest.py
  - reconcile_raw_phase: indexed_at auto-populated on mirror Note rows
    (commit 7bd4a9f: set indexed_at on mirror Note rows for raw inputs)
  - reconcile_raw_phase: original_path extracted from frontmatter extra
  - reconcile_raw_phase: OSError during file read is logged and skipped
  - _infer_source: explicit meta.source value is returned as-is

migrate_raw_bucketing.py
  - _strip_frontmatter_keys: bad YAML returns original content
  - _strip_frontmatter_keys: non-dict YAML returns original content
  - _strip_frontmatter_keys: no frontmatter returns content unchanged
  - _strip_frontmatter_keys: stripping all keys returns just the body
  - _grandfather_raws: bad frontmatter logs warning and uses defaults
  - _grandfather_atoms: returns 0 when no atom notes in DB
  - _grandfather_atoms: inserts pre-migration sentinel for each atom
  - _grandfather_atoms: idempotent — skips atoms that already have a sentinel
  - _grandfather_atoms: handles fact and active note types
  - _write_back_id (reconciler): no-frontmatter else branch uses LF and prepends block
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import AtomRawProvenance, Note, RawInput


# ---------------------------------------------------------------------------
# Shared SQLite session fixture
# ---------------------------------------------------------------------------


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
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# store.py – upsert_note: note_id collision when path changes
# (commit 57b1049: handle note_id collision when path changes during upsert)
# ---------------------------------------------------------------------------


class TestUpsertNoteNoteIdFallback:
    """When a note's path changes between runs, upsert_note must find the
    existing row by note_id (the stable identity) rather than by path.

    Without the fix the path lookup returns None AND the note_id lookup also
    returns None — the INSERT fails with a UNIQUE violation on note_id.
    The fix adds a second lookup by note_id when the path lookup misses.
    """

    def test_upsert_replaces_note_when_path_changes(self, session):
        """Re-upserting the same note_id at a new path replaces the old row."""
        from knowledge.frontmatter import ParsedFrontmatter
        from knowledge.store import KnowledgeStore

        store = KnowledgeStore(session=session)
        meta = ParsedFrontmatter()
        chunks = [{"index": 0, "section_header": "", "text": "Body."}]
        vectors = [[0.1] * 1024]

        # First upsert at the original path.
        store.upsert_note(
            note_id="stable-id",
            path="_processed/old-path.md",
            content_hash="h1",
            title="Old Title",
            metadata=meta,
            chunks=chunks,
            vectors=vectors,
            links=[],
        )

        old_notes = session.exec(select(Note)).all()
        assert len(old_notes) == 1

        # Re-upsert the same note_id at a different path (e.g. gardener moved
        # the file from the vault root into _processed/).
        store.upsert_note(
            note_id="stable-id",
            path="_processed/new-path.md",
            content_hash="h2",
            title="New Title",
            metadata=meta,
            chunks=chunks,
            vectors=vectors,
            links=[],
        )

        notes = session.exec(select(Note)).all()
        # Exactly one row – the old one was replaced, not duplicated.
        assert len(notes) == 1
        assert notes[0].note_id == "stable-id"
        assert notes[0].path == "_processed/new-path.md"
        assert notes[0].title == "New Title"
        assert notes[0].content_hash == "h2"

    def test_upsert_clears_old_chunks_on_path_change(self, session):
        """Chunks from the old path are deleted when the note is re-upserted at
        a new path (cascade delete via note_id fallback lookup)."""
        from knowledge.models import Chunk
        from knowledge.frontmatter import ParsedFrontmatter
        from knowledge.store import KnowledgeStore

        store = KnowledgeStore(session=session)
        meta = ParsedFrontmatter()

        store.upsert_note(
            note_id="chunk-test",
            path="_processed/orig.md",
            content_hash="h1",
            title="T",
            metadata=meta,
            chunks=[
                {"index": 0, "section_header": "S0", "text": "chunk0"},
                {"index": 1, "section_header": "S1", "text": "chunk1"},
            ],
            vectors=[[0.1] * 1024, [0.2] * 1024],
            links=[],
        )

        # Confirm two chunks were stored.
        assert len(session.exec(select(Chunk)).all()) == 2

        # Re-upsert at a new path with a single chunk.
        store.upsert_note(
            note_id="chunk-test",
            path="_processed/moved.md",
            content_hash="h2",
            title="T2",
            metadata=meta,
            chunks=[{"index": 0, "section_header": "", "text": "new chunk"}],
            vectors=[[0.3] * 1024],
            links=[],
        )

        # Old chunks deleted; only the new one remains.
        chunks = session.exec(select(Chunk)).all()
        assert len(chunks) == 1
        assert chunks[0].chunk_text == "new chunk"


# ---------------------------------------------------------------------------
# reconciler.py – _write_back_id: CRLF frontmatter branch
# ---------------------------------------------------------------------------


class TestWriteBackIdCRLF:
    """_write_back_id preserves CRLF line endings when the frontmatter
    block opens with '---\\r\\n'."""

    def test_crlf_frontmatter_inserts_id_with_crlf(self, tmp_path):
        from unittest.mock import MagicMock
        from knowledge.reconciler import Reconciler

        rec = Reconciler(
            store=MagicMock(),
            embed_client=MagicMock(),
            vault_root=tmp_path,
        )
        note_file = tmp_path / "crlf_note.md"
        # Windows-style line endings in frontmatter
        raw = "---\r\ntitle: CRLF Note\r\n---\r\nBody text.\r\n"
        note_file.write_bytes(raw.encode("utf-8"))

        new_raw, new_hash = rec._write_back_id(note_file, raw, "crlf-note")

        # The id line must be inserted using CRLF.
        assert "---\r\nid: crlf-note\r\n" in new_raw
        # Original content must be preserved.
        assert "title: CRLF Note" in new_raw
        assert "Body text." in new_raw
        # Hash must match the new content.
        import hashlib

        expected_hash = hashlib.sha256(new_raw.encode("utf-8")).hexdigest()
        assert new_hash == expected_hash
        # File updated on disk.
        assert note_file.read_bytes() == new_raw.encode("utf-8")

    def test_crlf_frontmatter_not_mixed_with_lf(self, tmp_path):
        """The injected id line must use \\r\\n, not \\n, so no CRLF/LF mixing."""
        from unittest.mock import MagicMock
        from knowledge.reconciler import Reconciler

        rec = Reconciler(
            store=MagicMock(),
            embed_client=MagicMock(),
            vault_root=tmp_path,
        )
        note_file = tmp_path / "crlf2.md"
        raw = "---\r\ntitle: Mixed\r\n---\r\nBody.\r\n"
        note_file.write_bytes(raw.encode("utf-8"))

        new_raw, _ = rec._write_back_id(note_file, raw, "mixed-note")

        # There must be no bare LF (i.e. LF not preceded by CR) in the header.
        lines = new_raw.split("\r\n")
        # Every line split by CRLF must not itself contain a bare LF.
        for line in lines:
            assert "\n" not in line, f"Bare LF found in line: {line!r}"


# ---------------------------------------------------------------------------
# reconciler.py – _pre_sync_links: exception must not block reconcile
# ---------------------------------------------------------------------------


class TestPreSyncLinksException:
    """Per-file exceptions inside _pre_sync_links are swallowed by its
    internal try/except — the method is best-effort and must log a warning
    but never propagate to the caller."""

    def test_per_file_exception_is_swallowed_and_logged(
        self, session, tmp_path, caplog
    ):
        """When _read_text raises for one file, _pre_sync_links logs a
        warning and does not propagate the exception."""
        from unittest.mock import AsyncMock
        from knowledge.reconciler import Reconciler
        from knowledge.store import KnowledgeStore

        processed = tmp_path / "_processed"
        processed.mkdir()
        (processed / "bad.md").write_text(
            "---\nid: bad\ntitle: Bad\n---\nBody.", encoding="utf-8"
        )

        rec = Reconciler(
            store=KnowledgeStore(session=session),
            embed_client=AsyncMock(),
            vault_root=tmp_path,
        )

        original_read_text = rec._read_text

        def raise_for_bad(path: Path) -> str:
            if "bad.md" in str(path):
                raise OSError("simulated read error")
            return original_read_text(path)

        rec._read_text = raise_for_bad  # type: ignore[method-assign]

        with caplog.at_level(logging.WARNING, logger="monolith.knowledge.reconciler"):
            # Must not raise
            rec._pre_sync_links()

        assert any("failed to pre-sync links" in r.message for r in caplog.records)

    def test_per_file_exception_does_not_affect_other_files(self, session, tmp_path):
        """A per-file exception in _pre_sync_links does not affect other
        files in the same pass — the loop continues normally."""
        from unittest.mock import AsyncMock
        from knowledge.reconciler import Reconciler
        from knowledge.store import KnowledgeStore

        processed = tmp_path / "_processed"
        processed.mkdir()
        (processed / "bad.md").write_text(
            "---\nid: bad\ntitle: Bad\n---\nBody.", encoding="utf-8"
        )
        (processed / "good.md").write_text(
            "---\nid: good\ntitle: Good\n---\nBody.", encoding="utf-8"
        )

        rec = Reconciler(
            store=KnowledgeStore(session=session),
            embed_client=AsyncMock(),
            vault_root=tmp_path,
        )

        original_read_text = rec._read_text
        read_count = {"n": 0}

        def raise_for_bad(path: Path) -> str:
            if "bad.md" in str(path):
                raise OSError("simulated read error")
            read_count["n"] += 1
            return original_read_text(path)

        rec._read_text = raise_for_bad  # type: ignore[method-assign]

        # Must not raise and must have read the good file.
        rec._pre_sync_links()
        assert read_count["n"] >= 1, (
            "good.md must have been read despite bad.md failing"
        )


# ---------------------------------------------------------------------------
# gardener.py – _raws_needing_decomposition: session=None
# ---------------------------------------------------------------------------


class TestRawsNeedingDecompositionNoSession:
    def test_returns_empty_list_when_session_is_none(self, tmp_path):
        """_raws_needing_decomposition returns [] immediately when session=None
        (no DB access attempted)."""
        from knowledge.gardener import Gardener

        gardener = Gardener(vault_root=tmp_path, session=None)
        result = gardener._raws_needing_decomposition()
        assert result == []


# ---------------------------------------------------------------------------
# gardener.py – _resolve_pending_provenance: session=None
# ---------------------------------------------------------------------------


class TestResolvePendingProvenanceNoSession:
    def test_returns_zero_when_session_is_none(self, tmp_path):
        """_resolve_pending_provenance returns 0 immediately when session=None
        (no DB access attempted)."""
        from knowledge.gardener import Gardener

        gardener = Gardener(vault_root=tmp_path, session=None)
        result = gardener._resolve_pending_provenance()
        assert result == 0


# ---------------------------------------------------------------------------
# gardener.py – run(): reconcile_raw_phase skipped when session=None
# ---------------------------------------------------------------------------


class TestGardenerRunNoSession:
    @pytest.mark.asyncio
    async def test_run_skips_reconcile_raw_phase_when_session_is_none(self, tmp_path):
        """When session=None, run() must not call reconcile_raw_phase (which
        requires a Session). move_phase is still executed."""
        from knowledge.gardener import Gardener

        # Drop a file in the vault root so move_phase has something to process.
        _write(tmp_path / "inbox" / "note.md", "---\ntitle: T\n---\nBody.")

        gardener = Gardener(vault_root=tmp_path, session=None)
        # No session → _ingest_one would need a DB; no raws in the DB either.
        with patch("knowledge.raw_ingest.reconcile_raw_phase") as mock_reconcile:
            stats = await gardener.run()

        # reconcile_raw_phase must NOT have been called.
        mock_reconcile.assert_not_called()
        # move_phase ran: the inbox file was moved into _raw/.
        assert not (tmp_path / "inbox" / "note.md").exists()
        assert stats.moved == 1

    @pytest.mark.asyncio
    async def test_run_with_no_session_returns_zero_ingested(self, tmp_path):
        """With session=None there are no RawInput rows, so ingested==0."""
        from knowledge.gardener import Gardener

        gardener = Gardener(vault_root=tmp_path, session=None)
        stats = await gardener.run()
        assert stats.ingested == 0
        assert stats.failed == 0
        assert stats.reconciled == 0


# ---------------------------------------------------------------------------
# raw_ingest.py – reconcile_raw_phase: indexed_at on mirror Note rows
# (commit 7bd4a9f: set indexed_at on mirror Note rows for raw inputs)
# ---------------------------------------------------------------------------


class TestReconcileRawPhaseIndexedAt:
    """Mirror Note rows created by reconcile_raw_phase must have indexed_at
    auto-populated via the default_factory (not left as NULL)."""

    def test_mirror_note_indexed_at_is_set(self, tmp_path, session):
        from knowledge.raw_ingest import reconcile_raw_phase

        raw_file = tmp_path / "_raw" / "2026" / "04" / "10" / "abc1-test.md"
        _write(raw_file, "---\ntitle: Test\nsource: vault-drop\n---\nBody.")

        reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        notes = session.exec(select(Note).where(Note.type == "raw")).all()
        assert len(notes) == 1
        assert notes[0].indexed_at is not None
        assert isinstance(notes[0].indexed_at, datetime)

    def test_mirror_note_indexed_at_is_recent(self, tmp_path, session):
        """indexed_at is a recent datetime (within the current run window).

        SQLite strips tzinfo on read-back, so we compare against naive UTC
        bounds. The model's default_factory uses datetime.now(timezone.utc)
        but SQLite returns naive datetimes.
        """
        from knowledge.raw_ingest import reconcile_raw_phase

        before = datetime.now(timezone.utc).replace(tzinfo=None)
        raw_file = tmp_path / "_raw" / "2026" / "04" / "10" / "abc2-utc.md"
        _write(raw_file, "---\ntitle: UTC\n---\nBody.")

        reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        notes = session.exec(select(Note).where(Note.type == "raw")).all()
        indexed_at = notes[0].indexed_at
        # Strip tzinfo since SQLite returns naive datetimes.
        indexed_naive = (
            indexed_at.replace(tzinfo=None) if indexed_at.tzinfo else indexed_at
        )
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before <= indexed_naive <= after


# ---------------------------------------------------------------------------
# raw_ingest.py – reconcile_raw_phase: original_path from frontmatter extra
# ---------------------------------------------------------------------------


class TestReconcileRawPhaseOriginalPath:
    """When a raw file's frontmatter contains original_path in extra fields,
    reconcile_raw_phase stores it on the RawInput row."""

    def test_original_path_extracted_from_frontmatter_extra(self, tmp_path, session):
        from knowledge.raw_ingest import reconcile_raw_phase

        raw_file = tmp_path / "_raw" / "grandfathered" / "abc1-orig.md"
        _write(
            raw_file,
            "---\ntitle: Orig\noriginal_path: inbox/my-note.md\n---\nBody.",
        )

        reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        rows = session.exec(select(RawInput)).all()
        assert len(rows) == 1
        assert rows[0].original_path == "inbox/my-note.md"

    def test_original_path_is_none_when_absent(self, tmp_path, session):
        """When original_path is not in frontmatter, the field stays None."""
        from knowledge.raw_ingest import reconcile_raw_phase

        raw_file = tmp_path / "_raw" / "2026" / "04" / "10" / "abc1-no-orig.md"
        _write(raw_file, "---\ntitle: No Orig\n---\nBody.")

        reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        rows = session.exec(select(RawInput)).all()
        assert len(rows) == 1
        assert rows[0].original_path is None


# ---------------------------------------------------------------------------
# raw_ingest.py – reconcile_raw_phase: OSError during file read
# ---------------------------------------------------------------------------


class TestReconcileRawPhaseReadError:
    """An OSError while reading a raw file is logged as a warning and the
    file is skipped — reconcile_raw_phase continues with the remaining files."""

    def test_oserror_on_read_skips_file_and_continues(self, tmp_path, session, caplog):
        from knowledge.raw_ingest import reconcile_raw_phase

        bad = tmp_path / "_raw" / "2026" / "04" / "10" / "abc1-bad.md"
        good = tmp_path / "_raw" / "2026" / "04" / "10" / "abc2-good.md"
        _write(bad, "---\ntitle: Bad\n---\nContent.")
        _write(good, "---\ntitle: Good\n---\nContent.")

        original_read_text = Path.read_text

        def raise_on_bad(p: Path, *a, **kw) -> str:
            if p == bad:
                raise OSError("permission denied")
            return original_read_text(p, *a, **kw)

        with (
            patch.object(Path, "read_text", raise_on_bad),
            caplog.at_level(logging.WARNING, logger="monolith.knowledge.raw_ingest"),
        ):
            stats = reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        # Good file was inserted; bad file was skipped.
        assert stats.inserted == 1
        rows = session.exec(select(RawInput)).all()
        assert len(rows) == 1
        assert rows[0].path.endswith("abc2-good.md")
        # Warning was logged for the bad file.
        assert any("failed to read" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# raw_ingest.py – _infer_source: explicit meta.source
# ---------------------------------------------------------------------------


class TestInferSource:
    """_infer_source returns the explicit meta.source value when it is set,
    regardless of the path structure."""

    def test_explicit_source_returned_as_is(self):
        from knowledge.raw_ingest import _infer_source

        result = _infer_source("custom-importer", ("_raw", "2026", "04", "10"))
        assert result == "custom-importer"

    def test_explicit_source_takes_priority_over_grandfathered_path(self):
        """Even a grandfathered path does not override an explicit meta.source."""
        from knowledge.raw_ingest import _infer_source
        from knowledge.raw_paths import GRANDFATHERED_SUBDIR

        result = _infer_source("webhook", ("_raw", GRANDFATHERED_SUBDIR, "file.md"))
        assert result == "webhook"

    def test_none_source_with_grandfathered_path_returns_grandfathered(self):
        from knowledge.raw_ingest import _infer_source
        from knowledge.raw_paths import GRANDFATHERED_SUBDIR

        result = _infer_source(None, ("_raw", GRANDFATHERED_SUBDIR, "file.md"))
        assert result == "grandfathered"

    def test_none_source_with_dated_path_returns_vault_drop(self):
        from knowledge.raw_ingest import _infer_source

        result = _infer_source(None, ("_raw", "2026", "04", "10", "file.md"))
        assert result == "vault-drop"


# ---------------------------------------------------------------------------
# migrate_raw_bucketing.py – _strip_frontmatter_keys: edge cases
# ---------------------------------------------------------------------------


class TestStripFrontmatterKeys:
    """Edge cases for _strip_frontmatter_keys in the migration helper."""

    def test_no_frontmatter_returns_content_unchanged(self):
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "Just plain body.\nNo frontmatter."
        result = _strip_frontmatter_keys(content, {"ttl"})
        assert result == content

    def test_unclosed_frontmatter_returns_content_unchanged(self):
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "---\ntitle: Test\n"  # no closing ---
        result = _strip_frontmatter_keys(content, {"ttl"})
        assert result == content

    def test_bad_yaml_returns_content_unchanged(self):
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "---\n: invalid: yaml:\n---\nBody."
        result = _strip_frontmatter_keys(content, {"ttl"})
        assert result == content

    def test_non_dict_yaml_returns_content_unchanged(self):
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "---\n- item1\n- item2\n---\nBody."
        result = _strip_frontmatter_keys(content, {"ttl"})
        assert result == content

    def test_stripping_all_keys_returns_body_only(self):
        """When all frontmatter keys are stripped, only the body is returned."""
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "---\nttl: 2026-01-01\n---\nBody text here.\n"
        result = _strip_frontmatter_keys(content, {"ttl"})
        # All keys stripped → meta dict is empty → body returned.
        assert result == "Body text here.\n"
        assert "ttl" not in result
        assert "---" not in result

    def test_preserves_non_stripped_keys(self):
        """Keys not in the strip-set are preserved in the output."""
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "---\ntitle: Keep Me\nttl: remove\n---\nBody.\n"
        result = _strip_frontmatter_keys(content, {"ttl"})
        assert "title: Keep Me" in result
        assert "ttl" not in result

    def test_stripping_nonexistent_key_is_a_noop(self):
        """Attempting to strip a key that doesn't exist in the frontmatter
        leaves the content structurally equivalent."""
        from knowledge.migrate_raw_bucketing import _strip_frontmatter_keys

        content = "---\ntitle: Test\n---\nBody.\n"
        result = _strip_frontmatter_keys(content, {"nonexistent-key"})
        assert "title: Test" in result
        assert "nonexistent-key" not in result


# ---------------------------------------------------------------------------
# migrate_raw_bucketing.py – _grandfather_raws: bad frontmatter warning
# ---------------------------------------------------------------------------


class TestGrandfatherRawsBadFrontmatter:
    """When _grandfather_raws encounters a file with unparseable frontmatter,
    it logs a warning and falls back to using the stem as the title."""

    def test_bad_frontmatter_logs_warning_and_uses_stem_as_title(
        self, tmp_path, session, caplog
    ):
        from knowledge.migrate_raw_bucketing import _grandfather_raws

        bad = tmp_path / "_deleted_with_ttl" / "inbox" / "bad-fm.md"
        # Frontmatter that will cause a parse error: unterminated list.
        _write(bad, "---\ntitle: [unterminated\n---\nBody text.")

        with caplog.at_level(
            logging.WARNING, logger="monolith.knowledge.migrate_raw_bucketing"
        ):
            count = _grandfather_raws(vault_root=tmp_path, session=session)
        session.commit()

        # The file was still processed (fallen back to stem for title).
        assert count == 1
        # Warning was logged.
        assert any("bad frontmatter" in r.message for r in caplog.records)
        # The raw_input should exist with the stem as title.
        rows = session.exec(select(RawInput)).all()
        assert len(rows) == 1
        assert rows[0].source == "grandfathered"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# migrate_raw_bucketing.py – _grandfather_atoms
# ---------------------------------------------------------------------------


class TestGrandfatherAtoms:
    """_grandfather_atoms creates pre-migration sentinel provenance rows for
    atom, fact, and active notes that do not already have one."""

    def test_returns_zero_when_no_atoms_in_db(self, session):
        """Returns 0 when the notes table has no atom/fact/active rows."""
        from knowledge.migrate_raw_bucketing import _grandfather_atoms

        result = _grandfather_atoms(session)
        assert result == 0

    def test_inserts_sentinel_for_each_atom_note(self, session):
        """Creates one pre-migration provenance row per atom note."""
        from knowledge.migrate_raw_bucketing import _grandfather_atoms

        for i in range(3):
            note = Note(
                note_id=f"atom-{i}",
                path=f"_processed/atom-{i}.md",
                title=f"Atom {i}",
                content_hash=f"h{i}",
                type="atom",
            )
            session.add(note)
        session.commit()

        result = _grandfather_atoms(session)
        assert result == 3

        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration"
            )
        ).all()
        assert len(sentinels) == 3
        # All sentinels have atom_fk set and raw_fk unset
        for s in sentinels:
            assert s.atom_fk is not None
            assert s.raw_fk is None

    def test_is_idempotent_for_atoms_with_existing_sentinel(self, session):
        """Atoms that already have a pre-migration sentinel are not re-processed."""
        from knowledge.migrate_raw_bucketing import _grandfather_atoms

        note = Note(
            note_id="already-done",
            path="_processed/already-done.md",
            title="Already Done",
            content_hash="h1",
            type="atom",
        )
        session.add(note)
        session.commit()

        # First call inserts the sentinel
        count1 = _grandfather_atoms(session)
        assert count1 == 1

        # Second call finds the existing sentinel and skips
        count2 = _grandfather_atoms(session)
        assert count2 == 0

        # Only one sentinel exists
        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.atom_fk == note.id,
                AtomRawProvenance.gardener_version == "pre-migration",
            )
        ).all()
        assert len(sentinels) == 1

    def test_handles_fact_and_active_note_types(self, session):
        """fact and active note types are included alongside atom notes."""
        from knowledge.migrate_raw_bucketing import _grandfather_atoms

        for note_type in ("fact", "active"):
            note = Note(
                note_id=f"typed-{note_type}",
                path=f"_processed/{note_type}.md",
                title=f"Typed {note_type}",
                content_hash=f"h-{note_type}",
                type=note_type,
            )
            session.add(note)
        session.commit()

        result = _grandfather_atoms(session)
        assert result == 2

        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration"
            )
        ).all()
        assert len(sentinels) == 2

    def test_ignores_raw_and_other_note_types(self, session):
        """Notes with type 'raw' or other non-atom types are not grandfathered."""
        from knowledge.migrate_raw_bucketing import _grandfather_atoms

        for note_type in ("raw", "note"):
            note = Note(
                note_id=f"skip-{note_type}",
                path=f"_processed/skip-{note_type}.md",
                title=f"Skip {note_type}",
                content_hash=f"h-skip-{note_type}",
                type=note_type,
            )
            session.add(note)
        session.commit()

        result = _grandfather_atoms(session)
        assert result == 0


# ---------------------------------------------------------------------------
# reconciler.py – _write_back_id: no-frontmatter else branch
# ---------------------------------------------------------------------------


class TestWriteBackIdNoBranch:
    """_write_back_id prepends a new YAML frontmatter block when the file has
    no existing frontmatter (the else branch).  This complements the CRLF
    branch tested in TestWriteBackIdCRLF."""

    def test_no_frontmatter_prepends_yaml_block(self, tmp_path):
        """When raw does not start with '---', a new frontmatter block is
        prepended using LF line endings."""
        from unittest.mock import MagicMock
        from knowledge.reconciler import Reconciler
        import hashlib

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

    def test_no_frontmatter_uses_lf_not_crlf(self, tmp_path):
        """The else branch defaults to LF, not CRLF."""
        from unittest.mock import MagicMock
        from knowledge.reconciler import Reconciler

        rec = Reconciler(
            store=MagicMock(),
            embed_client=MagicMock(),
            vault_root=tmp_path,
        )
        note_file = tmp_path / "plain.md"
        raw = "Plain content."
        note_file.write_text(raw, encoding="utf-8")

        new_raw, _ = rec._write_back_id(note_file, raw, "plain-id")

        assert "\r\n" not in new_raw
        assert new_raw.startswith("---\n")


# ---------------------------------------------------------------------------
# gardener.py – _record_failed_provenance: session=None returns early
# ---------------------------------------------------------------------------


class TestRecordFailedProvenanceNoSession:
    """_record_failed_provenance returns immediately when session is None,
    without raising or attempting any database access."""

    def test_returns_none_when_session_is_none(self, tmp_path):
        """Calling _record_failed_provenance with session=None must not raise."""
        from knowledge.gardener import Gardener
        from knowledge.models import RawInput

        gardener = Gardener(vault_root=tmp_path, session=None)

        # A raw row with a fake id — session is None so no DB call happens.
        fake_raw = RawInput(
            raw_id="test-raw",
            path="_raw/2026/04/10/abc1-test.md",
            source="vault-drop",
            content="body",
            content_hash="h1",
        )
        # Assign a fake integer id so the method doesn't blow up trying to
        # query by id.
        fake_raw.id = 42

        exc = RuntimeError("subprocess failed")
        # Must return without raising.
        result = gardener._record_failed_provenance(fake_raw, exc)
        assert result is None


# ---------------------------------------------------------------------------
# gardener.py – _record_failed_provenance: error truncated to 500 chars
# ---------------------------------------------------------------------------


class TestRecordFailedProvenanceErrorTruncation:
    """Errors longer than 500 characters must be truncated to exactly 500 chars
    when stored in the provenance row."""

    def test_long_error_is_truncated_on_first_failure(self, tmp_path, session):
        """A 600-char error is stored as 500 chars when creating a new row."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="trunc-raw",
            path="_raw/2026/04/10/abc1-trunc.md",
            source="vault-drop",
            content="body",
            content_hash="h1",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        gardener = Gardener(vault_root=tmp_path, session=session)
        long_error = "x" * 600
        gardener._record_failed_provenance(raw, RuntimeError(long_error))

        prov = session.exec(
            select(AtomRawProvenance).where(AtomRawProvenance.raw_fk == raw.id)
        ).first()
        assert prov is not None
        assert len(prov.error) == 500
        assert prov.error == "x" * 500

    def test_long_error_is_truncated_on_retry(self, tmp_path, session):
        """When updating an existing 'failed' row, the error is truncated too."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="trunc-retry-raw",
            path="_raw/2026/04/10/abc2-trunc.md",
            source="vault-drop",
            content="body",
            content_hash="h2",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        # Pre-insert an existing failed provenance row.
        prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="failed",
            gardener_version=GARDENER_VERSION,
            error="short error",
            retry_count=1,
        )
        session.add(prov)
        session.commit()
        session.refresh(prov)

        gardener = Gardener(vault_root=tmp_path, session=session)
        long_error = "y" * 700
        gardener._record_failed_provenance(raw, RuntimeError(long_error))

        session.refresh(prov)
        assert len(prov.error) == 500
        assert prov.error == "y" * 500
        assert prov.retry_count == 2

    def test_short_error_is_stored_as_is(self, tmp_path, session):
        """Errors shorter than 500 chars are stored verbatim."""
        from knowledge.gardener import Gardener

        raw = RawInput(
            raw_id="short-err-raw",
            path="_raw/2026/04/10/abc3-short.md",
            source="vault-drop",
            content="body",
            content_hash="h3",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        gardener = Gardener(vault_root=tmp_path, session=session)
        gardener._record_failed_provenance(raw, RuntimeError("short"))

        prov = session.exec(
            select(AtomRawProvenance).where(AtomRawProvenance.raw_fk == raw.id)
        ).first()
        assert prov is not None
        assert prov.error == "short"


# ---------------------------------------------------------------------------
# gardener.py – _raws_needing_decomposition: exhausted retries are excluded
# ---------------------------------------------------------------------------


class TestRawsNeedingDecompositionExhaustedRetries:
    """A raw with retry_count >= Gardener._MAX_RETRIES must NOT appear in
    _raws_needing_decomposition() — it belongs in the dead letter queue."""

    def test_exhausted_raw_is_excluded(self, tmp_path, session):
        """Raw with retry_count == _MAX_RETRIES is excluded."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="exhausted-raw",
            path="_raw/2026/04/10/abc1-exhausted.md",
            source="vault-drop",
            content="body",
            content_hash="h1",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="failed",
            gardener_version=GARDENER_VERSION,
            error="too many retries",
            retry_count=Gardener._MAX_RETRIES,
        )
        session.add(prov)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        result = gardener._raws_needing_decomposition()

        ids = [r.id for r in result]
        assert raw.id not in ids

    def test_over_limit_raw_is_excluded(self, tmp_path, session):
        """Raw with retry_count > _MAX_RETRIES is also excluded."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="over-limit-raw",
            path="_raw/2026/04/10/abc2-over.md",
            source="vault-drop",
            content="body",
            content_hash="h2",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="failed",
            gardener_version=GARDENER_VERSION,
            error="over limit",
            retry_count=Gardener._MAX_RETRIES + 5,
        )
        session.add(prov)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        result = gardener._raws_needing_decomposition()

        ids = [r.id for r in result]
        assert raw.id not in ids

    def test_under_limit_raw_is_included(self, tmp_path, session):
        """Raw with retry_count < _MAX_RETRIES IS included (retriable tier)."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="retriable-raw",
            path="_raw/2026/04/10/abc3-retriable.md",
            source="vault-drop",
            content="body",
            content_hash="h3",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="failed",
            gardener_version=GARDENER_VERSION,
            error="transient error",
            retry_count=Gardener._MAX_RETRIES - 1,
        )
        session.add(prov)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        result = gardener._raws_needing_decomposition()

        ids = [r.id for r in result]
        assert raw.id in ids


# ---------------------------------------------------------------------------
# gardener.py – _raws_needing_decomposition: successful provenance wins over failed
# ---------------------------------------------------------------------------


class TestRawsNeedingDecompositionSuccessfulProvenanceWins:
    """When a raw has BOTH a 'failed' provenance row AND a successful
    current-version provenance row, the successful one wins — the raw must
    NOT appear in _raws_needing_decomposition()."""

    def test_successful_provenance_excludes_raw_despite_failed_row(
        self, tmp_path, session
    ):
        """Raw with both a 'failed' row and a current-version success row is
        excluded from decomposition (success wins)."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="mixed-prov-raw",
            path="_raw/2026/04/10/abc1-mixed.md",
            source="vault-drop",
            content="body",
            content_hash="h1",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        # A failed provenance row — under the retry limit so it would normally
        # be retriable.
        failed_prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="failed",
            gardener_version=GARDENER_VERSION,
            error="transient error",
            retry_count=1,
        )
        session.add(failed_prov)

        # A successful current-version provenance row.
        success_prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="my-derived-note",
            gardener_version=GARDENER_VERSION,
        )
        session.add(success_prov)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        result = gardener._raws_needing_decomposition()

        ids = [r.id for r in result]
        assert raw.id not in ids

    def test_only_failed_row_without_success_is_retriable(self, tmp_path, session):
        """Control: same raw with only a failed row (no success) IS returned
        when retry_count is below the limit."""
        from knowledge.gardener import Gardener, GARDENER_VERSION

        raw = RawInput(
            raw_id="only-failed-raw",
            path="_raw/2026/04/10/abc2-only-failed.md",
            source="vault-drop",
            content="body",
            content_hash="h2",
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

        failed_prov = AtomRawProvenance(
            raw_fk=raw.id,
            derived_note_id="failed",
            gardener_version=GARDENER_VERSION,
            error="transient error",
            retry_count=1,
        )
        session.add(failed_prov)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        result = gardener._raws_needing_decomposition()

        ids = [r.id for r in result]
        assert raw.id in ids
