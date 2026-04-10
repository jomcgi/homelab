# Knowledge Raw Bucketing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the knowledge pipeline so every raw input is preserved forever in `_raw/` + `knowledge.raw_inputs`, derived atoms track provenance back to source raws via `knowledge.atom_raw_provenance`, and the existing TTL-based raw expiry is removed.

**Architecture:** Three-phase crash-safe gardener loop — Phase A atomically renames vault-root drops into `_raw/YYYY/MM/DD/<hash>-<slug>.md`, Phase B idempotently reconciles `_raw/` into `raw_inputs` + mirror rows in `notes` (type=`raw`), Phase C decomposes raws via the existing Claude CLI subprocess and records provenance via a `derived_from_raw` frontmatter key that the gardener resolves on the next cycle. Pre-migration data is grandfathered via sentinel provenance rows during a one-shot offline migration.

**Tech Stack:** Python asyncio, SQLModel + SQLAlchemy, Postgres (via Atlas migrations), pgvector, existing Claude CLI subprocess flow, Bazel `py_test` targets, `bb remote test --config=ci`.

**Reference design:** `docs/plans/2026-04-09-knowledge-raw-bucketing-design.md`

---

## Conventions

All tasks follow TDD. Each task is a tight loop: write a failing test → run it → implement → run until green → commit. Use `bb remote test //projects/monolith:<target> --config=ci` — never `pytest` locally. Commit messages use Conventional Commits (the `commit-msg` hook enforces it).

Test targets live in the single monolithic `projects/monolith/BUILD` file. Follow the existing pattern: `py_test(name = "knowledge_<name>_test", srcs = ["knowledge/<name>_test.py"], imports = ["."], deps = [":monolith_backend"])`.

After adding or renaming any Python file, run `format` (vendored tool from `./bootstrap.sh`) to regenerate BUILD file entries — don't hand-edit the BUILD unless `format` refuses to pick something up.

Schema migrations live in `projects/monolith/chart/migrations/` with a `YYYYMMDDHHMMSS_name.sql` filename. After editing migrations, run `format` — it regenerates `atlas.sum`.

---

## Task 1: Schema migration — `raw_inputs` + `atom_raw_provenance` tables

**Files:**

- Create: `projects/monolith/chart/migrations/20260410000000_raw_bucketing_schema.sql`

**Step 1: Write the migration SQL**

```sql
-- knowledge raw bucketing: immutable raw inputs + atom provenance.
--
-- raw_inputs        — one row per ingested raw file under /vault/_raw/
-- atom_raw_provenance — many-to-many link between atoms/facts/active notes
--                       and the raw inputs they derive from, versioned by
--                       gardener_version for future reprocessing.

CREATE TABLE knowledge.raw_inputs (
    id             BIGSERIAL    PRIMARY KEY,
    raw_id         TEXT         NOT NULL UNIQUE,  -- sha256 of body; stable identity
    path           TEXT         NOT NULL UNIQUE,  -- vault-relative, e.g. "_raw/2026/04/09/abcd-my-note.md"
    source         TEXT         NOT NULL,         -- 'vault-drop' | 'insert-api' | 'web-share' | 'discord' | 'grandfathered'
    original_path  TEXT,                          -- pre-move path, if known
    content        TEXT         NOT NULL,         -- full markdown body
    content_hash   TEXT         NOT NULL,         -- sha256; matches raw_id
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    extra          JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX raw_inputs_source     ON knowledge.raw_inputs (source);
CREATE INDEX raw_inputs_created_at ON knowledge.raw_inputs (created_at DESC);

-- Many-to-many provenance link. Both sides nullable to support sentinel rows:
--   (atom_fk = real, raw_fk = NULL, version = 'pre-migration')
--       → grandfathered atom with unknown source raw
--   (atom_fk = NULL, raw_fk = real, version = 'pre-migration')
--       → raw already decomposed by a previous gardener run
--   (atom_fk = NULL, raw_fk = real, version != 'pre-migration',
--    derived_note_id IS NOT NULL)
--       → gardener produced this atom but it's not yet in knowledge.notes;
--         the next cycle resolves derived_note_id → atom_fk.
CREATE TABLE knowledge.atom_raw_provenance (
    id                BIGSERIAL    PRIMARY KEY,
    atom_fk           BIGINT       REFERENCES knowledge.notes(id) ON DELETE CASCADE,
    raw_fk            BIGINT       REFERENCES knowledge.raw_inputs(id) ON DELETE CASCADE,
    derived_note_id   TEXT,                       -- pending-resolution note_id when atom_fk IS NULL
    gardener_version  TEXT         NOT NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (atom_fk IS NOT NULL OR raw_fk IS NOT NULL)
);

-- One "real" edge per (atom, raw) pair.
CREATE UNIQUE INDEX atom_raw_provenance_real
    ON knowledge.atom_raw_provenance (atom_fk, raw_fk)
    WHERE atom_fk IS NOT NULL AND raw_fk IS NOT NULL;

-- One grandfather sentinel per atom.
CREATE UNIQUE INDEX atom_raw_provenance_atom_sentinel
    ON knowledge.atom_raw_provenance (atom_fk)
    WHERE raw_fk IS NULL AND gardener_version = 'pre-migration';

-- One "already processed" sentinel per raw.
CREATE UNIQUE INDEX atom_raw_provenance_raw_sentinel
    ON knowledge.atom_raw_provenance (raw_fk)
    WHERE atom_fk IS NULL AND gardener_version = 'pre-migration' AND derived_note_id IS NULL;

-- Pending-resolution rows: one per (raw, derived_note_id, version).
CREATE UNIQUE INDEX atom_raw_provenance_pending
    ON knowledge.atom_raw_provenance (raw_fk, derived_note_id, gardener_version)
    WHERE atom_fk IS NULL AND derived_note_id IS NOT NULL;

CREATE INDEX atom_raw_provenance_raw_fk  ON knowledge.atom_raw_provenance (raw_fk);
CREATE INDEX atom_raw_provenance_atom_fk ON knowledge.atom_raw_provenance (atom_fk);
CREATE INDEX atom_raw_provenance_version ON knowledge.atom_raw_provenance (gardener_version);
```

**Step 2: Regenerate atlas.sum**

Run: `format`
Expected: `atlas.sum` updates with a hash entry for the new file; no other changes.

**Step 3: Commit**

```bash
git add projects/monolith/chart/migrations/20260410000000_raw_bucketing_schema.sql \
        projects/monolith/chart/migrations/atlas.sum
git commit -m "feat(knowledge): add raw_inputs and atom_raw_provenance schema"
```

---

## Task 2: SQLModel classes for `RawInput` and `AtomRawProvenance`

**Files:**

- Modify: `projects/monolith/knowledge/models.py`
- Modify: `projects/monolith/knowledge/models_test.py`

**Step 1: Write failing tests**

Append to `projects/monolith/knowledge/models_test.py`:

```python
def test_raw_input_roundtrip(session):
    from knowledge.models import RawInput

    ri = RawInput(
        raw_id="abc123",
        path="_raw/2026/04/09/abc1-my-note.md",
        source="vault-drop",
        original_path="inbox/my-note.md",
        content="# Hello\n\nBody.",
        content_hash="abc123",
    )
    session.add(ri)
    session.commit()

    loaded = session.get(RawInput, ri.id)
    assert loaded is not None
    assert loaded.raw_id == "abc123"
    assert loaded.source == "vault-drop"
    assert loaded.extra == {}


def test_atom_raw_provenance_roundtrip(session):
    from knowledge.models import AtomRawProvenance, Note, RawInput

    note = Note(
        note_id="hello-world",
        path="_processed/atoms/hello-world.md",
        title="Hello World",
        content_hash="def456",
        type="atom",
    )
    raw = RawInput(
        raw_id="abc123",
        path="_raw/2026/04/09/abc1-my-note.md",
        source="vault-drop",
        content="Body.",
        content_hash="abc123",
    )
    session.add_all([note, raw])
    session.commit()

    prov = AtomRawProvenance(
        atom_fk=note.id,
        raw_fk=raw.id,
        gardener_version="claude-sonnet-4-6@v1",
    )
    session.add(prov)
    session.commit()

    loaded = session.get(AtomRawProvenance, prov.id)
    assert loaded is not None
    assert loaded.atom_fk == note.id
    assert loaded.raw_fk == raw.id
```

(The `session` fixture already exists in the knowledge tests via `conftest.py` — verify by grepping before you start.)

**Step 2: Run the test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_models_test --config=ci`
Expected: FAIL — `RawInput` and `AtomRawProvenance` don't exist yet.

**Step 3: Add the SQLModel classes**

Append to `projects/monolith/knowledge/models.py`:

```python
class RawInput(SQLModel, table=True):
    __tablename__ = "raw_inputs"
    __table_args__ = {"schema": "knowledge", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    raw_id: str = Field(sa_column=Column(String, nullable=False, unique=True))
    path: str = Field(unique=True)
    source: str
    original_path: str | None = None
    content: str
    content_hash: str
    created_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict, sa_column=Column(_JSONB))


class AtomRawProvenance(SQLModel, table=True):
    __tablename__ = "atom_raw_provenance"
    __table_args__ = {"schema": "knowledge", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    atom_fk: int | None = Field(default=None, foreign_key="knowledge.notes.id")
    raw_fk: int | None = Field(default=None, foreign_key="knowledge.raw_inputs.id")
    derived_note_id: str | None = None
    gardener_version: str
    created_at: datetime | None = None
```

**Step 4: Run test to verify it passes**

Run: `bb remote test //projects/monolith:knowledge_models_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/models.py \
        projects/monolith/knowledge/models_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add RawInput and AtomRawProvenance SQLModels"
```

---

## Task 3: Content-hash + raw-path helpers

**Files:**

- Create: `projects/monolith/knowledge/raw_paths.py`
- Create: `projects/monolith/knowledge/raw_paths_test.py`

**Step 1: Write failing tests**

```python
"""Tests for raw path + content hash helpers."""

from datetime import datetime, timezone
from pathlib import Path

from knowledge.raw_paths import (
    compute_raw_id,
    raw_target_path,
    RAW_ROOT_NAME,
    GRANDFATHERED_SUBDIR,
)


def test_compute_raw_id_is_sha256_of_bytes():
    content = "# Hello\n\nBody."
    expected = (
        "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969"
    )
    assert compute_raw_id(content) == expected


def test_compute_raw_id_is_stable_across_calls():
    content = "foo"
    assert compute_raw_id(content) == compute_raw_id(content)


def test_raw_target_path_uses_date_and_hash_prefix():
    created_at = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
    raw_id = "abcdef1234567890" + "0" * 48  # valid-length sha256
    p = raw_target_path(
        vault_root=Path("/vault"),
        raw_id=raw_id,
        title="My Cool Note!",
        created_at=created_at,
    )
    assert p == Path("/vault/_raw/2026/04/09/abcdef12-my-cool-note.md")


def test_raw_target_path_grandfathered_uses_flat_subdir():
    raw_id = "abcdef1234567890" + "0" * 48
    p = raw_target_path(
        vault_root=Path("/vault"),
        raw_id=raw_id,
        title="Old Note",
        grandfathered=True,
    )
    assert p == Path("/vault/_raw/grandfathered/abcdef12-old-note.md")


def test_raw_target_path_handles_title_with_only_punctuation():
    raw_id = "fedcba9876543210" + "0" * 48
    p = raw_target_path(
        vault_root=Path("/vault"),
        raw_id=raw_id,
        title="???",
        created_at=datetime(2026, 4, 9, tzinfo=timezone.utc),
    )
    # Slug falls back to "note"
    assert p.name == "fedcba98-note.md"


def test_raw_root_name_constant():
    assert RAW_ROOT_NAME == "_raw"
    assert GRANDFATHERED_SUBDIR == "grandfathered"
```

**Step 2: Run and verify fail**

Add the `py_test` target first (via `format`), then:
Run: `bb remote test //projects/monolith:knowledge_raw_paths_test --config=ci`
Expected: FAIL — module does not exist.

**Step 3: Implement**

```python
"""Helpers for computing raw IDs and target paths under _raw/."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from knowledge.gardener import _slugify

RAW_ROOT_NAME = "_raw"
GRANDFATHERED_SUBDIR = "grandfathered"
_HASH_PREFIX_LEN = 8


def compute_raw_id(content: str) -> str:
    """Return sha256 hex digest of content encoded as UTF-8."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def raw_target_path(
    *,
    vault_root: Path,
    raw_id: str,
    title: str,
    created_at: datetime | None = None,
    grandfathered: bool = False,
) -> Path:
    """Build the target path under vault_root/_raw/ for a raw input.

    Ongoing ingests go under _raw/YYYY/MM/DD/<hash-prefix>-<slug>.md;
    grandfathered files go under _raw/grandfathered/<hash-prefix>-<slug>.md.
    """
    prefix = raw_id[:_HASH_PREFIX_LEN]
    slug = _slugify(title)
    filename = f"{prefix}-{slug}.md"

    if grandfathered:
        return vault_root / RAW_ROOT_NAME / GRANDFATHERED_SUBDIR / filename

    if created_at is None:
        raise ValueError("created_at is required unless grandfathered=True")
    y = f"{created_at.year:04d}"
    m = f"{created_at.month:02d}"
    d = f"{created_at.day:02d}"
    return vault_root / RAW_ROOT_NAME / y / m / d / filename
```

**Step 4: Run test — verify pass**

Run: `bb remote test //projects/monolith:knowledge_raw_paths_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/raw_paths.py \
        projects/monolith/knowledge/raw_paths_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add raw path and content hash helpers"
```

---

## Task 4: Phase A — `move_phase` atomic rename into `_raw/`

**Files:**

- Create: `projects/monolith/knowledge/raw_ingest.py`
- Create: `projects/monolith/knowledge/raw_ingest_test.py`

**Step 1: Write failing tests**

```python
"""Tests for raw ingest Phase A (move) and Phase B (reconcile)."""

from datetime import datetime, timezone
from pathlib import Path

from knowledge.raw_ingest import MovePhaseStats, move_phase


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestMovePhase:
    def test_moves_vault_root_md_into_raw_tree(self, tmp_path):
        _write(tmp_path / "inbox" / "note.md", "---\ntitle: Note\n---\nBody.")
        now = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
        stats = move_phase(vault_root=tmp_path, now=now)
        assert stats.moved == 1
        assert stats.deduped == 0
        assert not (tmp_path / "inbox" / "note.md").exists()
        date_dir = tmp_path / "_raw" / "2026" / "04" / "09"
        targets = list(date_dir.glob("*.md"))
        assert len(targets) == 1
        assert targets[0].read_text(encoding="utf-8").startswith("---")

    def test_skips_files_already_under_managed_dirs(self, tmp_path):
        _write(tmp_path / "_raw" / "2026" / "04" / "09" / "abc-note.md", "x")
        _write(tmp_path / "_processed" / "atoms" / "a.md", "y")
        _write(tmp_path / "_deleted_with_ttl" / "old.md", "z")
        stats = move_phase(
            vault_root=tmp_path,
            now=datetime(2026, 4, 9, tzinfo=timezone.utc),
        )
        assert stats.moved == 0

    def test_dedup_deletes_source_when_target_exists(self, tmp_path):
        content = "---\ntitle: Dup\n---\nSame body."
        _write(tmp_path / "inbox" / "a.md", content)
        _write(tmp_path / "inbox" / "b.md", content)  # identical content → same raw_id
        now = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
        stats = move_phase(vault_root=tmp_path, now=now)
        # First gets moved, second is deduped (source deleted).
        assert stats.moved == 1
        assert stats.deduped == 1
        remaining = list((tmp_path / "inbox").glob("*.md"))
        assert remaining == []

    def test_ignores_dotfiles_and_dot_dirs(self, tmp_path):
        _write(tmp_path / ".obsidian" / "config.md", "x")
        _write(tmp_path / "inbox" / ".hidden.md", "y")
        _write(tmp_path / "inbox" / "visible.md", "---\ntitle: V\n---\nB")
        stats = move_phase(
            vault_root=tmp_path,
            now=datetime(2026, 4, 9, tzinfo=timezone.utc),
        )
        assert stats.moved == 1
```

**Step 2: Run test — verify fail**

Add the `py_test` target via `format`, then:
Run: `bb remote test //projects/monolith:knowledge_raw_ingest_test --config=ci`
Expected: FAIL — module does not exist.

**Step 3: Implement Phase A**

```python
"""Raw ingest pipeline: Phase A (move) and Phase B (reconcile)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from knowledge import frontmatter
from knowledge.raw_paths import (
    GRANDFATHERED_SUBDIR,
    RAW_ROOT_NAME,
    compute_raw_id,
    raw_target_path,
)

logger = logging.getLogger("monolith.knowledge.raw_ingest")

_EXCLUDED_TOP_LEVEL = {RAW_ROOT_NAME, "_processed", "_deleted_with_ttl", ".obsidian", ".trash"}


@dataclass(frozen=True)
class MovePhaseStats:
    moved: int
    deduped: int


def _discover_vault_root_drops(vault_root: Path) -> list[Path]:
    """Find .md files outside managed directories."""
    drops: list[Path] = []
    if not vault_root.exists():
        return drops
    for entry in vault_root.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.name in _EXCLUDED_TOP_LEVEL:
            continue
        if entry.is_file():
            if entry.suffix == ".md":
                drops.append(entry)
            continue
        if entry.is_dir():
            for p in entry.rglob("*.md"):
                rel = p.relative_to(vault_root)
                if any(part.startswith(".") for part in rel.parts):
                    continue
                drops.append(p)
    return sorted(drops)


def move_phase(*, vault_root: Path, now: datetime) -> MovePhaseStats:
    """Atomically move vault-root .md drops into _raw/YYYY/MM/DD/.

    Idempotent: if the target already exists (same content_hash) the
    source is deleted as a dedup.
    """
    moved = 0
    deduped = 0
    for source in _discover_vault_root_drops(vault_root):
        try:
            content = source.read_text(encoding="utf-8")
        except OSError as read_err:
            logger.warning("move_phase: failed to read %s: %s", source, read_err)
            continue

        raw_id = compute_raw_id(content)
        try:
            meta, _ = frontmatter.parse(content)
            title = meta.title or source.stem
        except Exception:
            title = source.stem

        target = raw_target_path(
            vault_root=vault_root,
            raw_id=raw_id,
            title=title,
            created_at=now,
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            # Same content already captured — delete source.
            source.unlink()
            deduped += 1
            continue

        source.replace(target)  # atomic rename within the same filesystem
        moved += 1

    return MovePhaseStats(moved=moved, deduped=deduped)
```

**Step 4: Run test — verify pass**

Run: `bb remote test //projects/monolith:knowledge_raw_ingest_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/raw_ingest.py \
        projects/monolith/knowledge/raw_ingest_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add raw ingest phase A (move)"
```

---

## Task 5: Phase B — `reconcile_raw_phase` DB mirror

**Files:**

- Modify: `projects/monolith/knowledge/raw_ingest.py`
- Modify: `projects/monolith/knowledge/raw_ingest_test.py`

**Step 1: Write failing tests**

Append to `raw_ingest_test.py`:

```python
import pytest

from knowledge.models import Note, RawInput
from knowledge.raw_ingest import (
    ReconcileRawStats,
    reconcile_raw_phase,
)
from sqlmodel import select


class TestReconcileRawPhase:
    def test_inserts_raw_input_and_mirror_note_row(self, tmp_path, session):
        raw_file = (
            tmp_path / "_raw" / "2026" / "04" / "09" / "abc1-my-note.md"
        )
        raw_file.parent.mkdir(parents=True)
        raw_file.write_text(
            "---\ntitle: My Note\nsource: vault-drop\n---\nBody.",
            encoding="utf-8",
        )

        stats = reconcile_raw_phase(
            vault_root=tmp_path, session=session
        )
        session.commit()

        assert stats.inserted == 1
        assert stats.skipped == 0

        rows = session.exec(select(RawInput)).all()
        assert len(rows) == 1
        assert rows[0].path == "_raw/2026/04/09/abc1-my-note.md"
        assert rows[0].source == "vault-drop"

        notes = session.exec(select(Note).where(Note.type == "raw")).all()
        assert len(notes) == 1
        assert notes[0].note_id == rows[0].raw_id

    def test_is_idempotent(self, tmp_path, session):
        raw_file = (
            tmp_path / "_raw" / "2026" / "04" / "09" / "abc1-my-note.md"
        )
        raw_file.parent.mkdir(parents=True)
        raw_file.write_text("---\ntitle: N\n---\nBody.", encoding="utf-8")

        reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()
        stats = reconcile_raw_phase(vault_root=tmp_path, session=session)
        session.commit()

        assert stats.inserted == 0
        assert stats.skipped == 1
        assert len(session.exec(select(RawInput)).all()) == 1

    def test_missing_raw_dir_is_noop(self, tmp_path, session):
        stats = reconcile_raw_phase(vault_root=tmp_path, session=session)
        assert stats.inserted == 0
        assert stats.skipped == 0
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_raw_ingest_test --config=ci`
Expected: FAIL — `reconcile_raw_phase` does not exist.

**Step 3: Implement Phase B**

Append to `raw_ingest.py`:

```python
from sqlmodel import Session, select

from knowledge.models import Note, RawInput


@dataclass(frozen=True)
class ReconcileRawStats:
    inserted: int
    skipped: int


def _infer_source(meta_source: str | None, rel_parts: tuple[str, ...]) -> str:
    if meta_source:
        return meta_source
    if GRANDFATHERED_SUBDIR in rel_parts:
        return "grandfathered"
    return "vault-drop"


def reconcile_raw_phase(*, vault_root: Path, session: Session) -> ReconcileRawStats:
    """Mirror _raw/ contents into knowledge.raw_inputs + notes(type='raw').

    Idempotent on path: already-reconciled files are skipped.
    """
    raw_root = vault_root / RAW_ROOT_NAME
    if not raw_root.exists():
        return ReconcileRawStats(inserted=0, skipped=0)

    inserted = 0
    skipped = 0

    existing_paths = set(
        session.exec(select(RawInput.path)).all()
    )

    for file_path in sorted(raw_root.rglob("*.md")):
        rel = file_path.relative_to(vault_root).as_posix()
        if rel in existing_paths:
            skipped += 1
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as read_err:
            logger.warning("reconcile_raw_phase: failed to read %s: %s", file_path, read_err)
            continue

        try:
            meta, _body = frontmatter.parse(content)
        except Exception:
            meta = None

        raw_id = compute_raw_id(content)
        title = (meta.title if meta and meta.title else file_path.stem)
        source = _infer_source(
            meta.source if meta else None,
            file_path.relative_to(vault_root).parts,
        )
        original_path = None
        if meta and meta.extra:
            original_path = meta.extra.get("original_path")

        ri = RawInput(
            raw_id=raw_id,
            path=rel,
            source=source,
            original_path=original_path,
            content=content,
            content_hash=raw_id,
        )
        session.add(ri)

        note = Note(
            note_id=raw_id,
            path=rel,
            title=title,
            content_hash=raw_id,
            type="raw",
            source=source,
        )
        session.add(note)
        inserted += 1

    return ReconcileRawStats(inserted=inserted, skipped=skipped)
```

**Step 4: Run test — verify pass**

Run: `bb remote test //projects/monolith:knowledge_raw_ingest_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/raw_ingest.py \
        projects/monolith/knowledge/raw_ingest_test.py
git commit -m "feat(knowledge): add raw ingest phase B (DB reconcile)"
```

---

## Task 6: Gardener decomposition skip query

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Modify: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write failing tests**

Add to `gardener_test.py`:

```python
class TestGardenerSkipsAlreadyProcessedRaws:
    def test_raws_with_current_version_provenance_are_skipped(
        self, tmp_path, session
    ):
        """A raw with an atom_raw_provenance row matching current
        gardener_version must not be re-decomposed."""
        from knowledge.gardener import Gardener, GARDENER_VERSION
        from knowledge.models import AtomRawProvenance, RawInput

        raw = RawInput(
            raw_id="r1",
            path="_raw/2026/04/09/r1-n.md",
            source="vault-drop",
            content="Body.",
            content_hash="r1",
        )
        session.add(raw)
        session.flush()
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                gardener_version=GARDENER_VERSION,
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        to_process = gardener._raws_needing_decomposition()
        assert [r.raw_id for r in to_process] == []

    def test_grandfathered_sentinel_blocks_decomposition(
        self, tmp_path, session
    ):
        from knowledge.gardener import Gardener
        from knowledge.models import AtomRawProvenance, RawInput

        raw = RawInput(
            raw_id="r2",
            path="_raw/grandfathered/r2-n.md",
            source="grandfathered",
            content="Body.",
            content_hash="r2",
        )
        session.add(raw)
        session.flush()
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                gardener_version="pre-migration",
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        assert gardener._raws_needing_decomposition() == []

    def test_new_raw_is_surfaced(self, tmp_path, session):
        from knowledge.gardener import Gardener
        from knowledge.models import RawInput

        raw = RawInput(
            raw_id="r3",
            path="_raw/2026/04/09/r3-n.md",
            source="vault-drop",
            content="Body.",
            content_hash="r3",
        )
        session.add(raw)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        surfaced = gardener._raws_needing_decomposition()
        assert [r.raw_id for r in surfaced] == ["r3"]
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: FAIL — `GARDENER_VERSION`, `session` kwarg, `_raws_needing_decomposition` don't exist.

**Step 3: Implement**

At the top of `gardener.py` add:

```python
from sqlalchemy import and_, not_, or_
from sqlmodel import Session, select

from knowledge.models import AtomRawProvenance, Note, RawInput

# Version stamp recorded on every provenance row the gardener produces.
# Bump this when the prompt or model changes to trigger a manual reprocess
# of existing raws (reprocess tooling is deferred — see design doc).
GARDENER_VERSION = "claude-sonnet-4-6@v1"
```

Modify the `Gardener.__init__` to accept an optional `session: Session | None`:

```python
def __init__(
    self,
    *,
    vault_root: Path,
    max_files_per_run: int = _DEFAULT_MAX_FILES_PER_RUN,
    claude_bin: str = "claude",
    session: Session | None = None,
) -> None:
    ...
    self.session = session
```

Add the query method:

```python
def _raws_needing_decomposition(self) -> list[RawInput]:
    """Return raws that have no current-version provenance and no sentinel.

    A raw is eligible for (re)decomposition when it has zero rows in
    atom_raw_provenance that either match GARDENER_VERSION or are the
    'pre-migration' sentinel marking it as already processed.
    """
    if self.session is None:
        return []

    handled_subq = (
        select(AtomRawProvenance.raw_fk)
        .where(AtomRawProvenance.raw_fk.is_not(None))
        .where(
            or_(
                AtomRawProvenance.gardener_version == GARDENER_VERSION,
                AtomRawProvenance.gardener_version == "pre-migration",
            )
        )
        .subquery()
    )
    stmt = (
        select(RawInput)
        .where(not_(RawInput.id.in_(select(handled_subq.c.raw_fk))))
        .order_by(RawInput.created_at.asc().nullslast(), RawInput.id.asc())
    )
    return list(self.session.exec(stmt).all())
```

**Step 4: Run test — verify pass**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/gardener.py \
        projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): gardener skips already-processed raws via provenance query"
```

---

## Task 7: Gardener loop rewrite — A→B→C, remove TTL

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Modify: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write failing test**

```python
class TestGardenerRunPhases:
    @pytest.mark.asyncio
    async def test_run_invokes_move_then_reconcile_then_decompose(
        self, tmp_path, session
    ):
        """Full loop: a vault-root drop ends up in _raw/, in the DB, and
        decomposed exactly once."""
        from knowledge.gardener import Gardener
        from knowledge.models import RawInput
        from sqlmodel import select

        (tmp_path / "inbox").mkdir()
        (tmp_path / "inbox" / "note.md").write_text(
            "---\ntitle: Note\n---\nBody.", encoding="utf-8"
        )

        gardener = Gardener(vault_root=tmp_path, session=session)
        gardener._ingest_one = AsyncMock()  # stub decomposition

        stats = await gardener.run()

        # Moved into _raw/.
        assert not (tmp_path / "inbox" / "note.md").exists()
        raw_files = list((tmp_path / "_raw").rglob("*.md"))
        assert len(raw_files) == 1

        # In the DB.
        assert len(session.exec(select(RawInput)).all()) == 1

        # Decomposed.
        assert gardener._ingest_one.call_count == 1

        # No TTL cleanup field anymore.
        assert stats.ingested == 1
        assert not hasattr(stats, "ttl_cleaned") or stats.ttl_cleaned == 0
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: FAIL.

**Step 3: Refactor `Gardener.run`**

Replace the current `run` implementation:

```python
async def run(self) -> GardenStats:
    """Run one gardening cycle: move → reconcile → decompose."""
    from knowledge.raw_ingest import move_phase, reconcile_raw_phase

    now = datetime.now(timezone.utc)
    move_stats = move_phase(vault_root=self.vault_root, now=now)

    reconcile_stats = None
    if self.session is not None:
        reconcile_stats = reconcile_raw_phase(
            vault_root=self.vault_root, session=self.session
        )
        self.session.commit()

    raws = self._raws_needing_decomposition()
    if self.max_files_per_run > 0 and len(raws) > self.max_files_per_run:
        logger.info(
            "gardener: %d raws need decomposition, capping to %d",
            len(raws),
            self.max_files_per_run,
        )
        raws = raws[: self.max_files_per_run]

    ingested = 0
    failed = 0
    for raw in raws:
        try:
            await self._ingest_one(self.vault_root / raw.path)
            ingested += 1
        except Exception:
            logger.exception("gardener: failed to ingest %s", raw.path)
            failed += 1

    stats = GardenStats(
        ingested=ingested,
        failed=failed,
        moved=move_stats.moved,
        deduped=move_stats.deduped,
        reconciled=(reconcile_stats.inserted if reconcile_stats else 0),
    )
    logger.info(
        "knowledge.garden: moved=%d deduped=%d reconciled=%d ingested=%d failed=%d",
        stats.moved, stats.deduped, stats.reconciled, stats.ingested, stats.failed,
    )
    return stats
```

Update `GardenStats`:

```python
@dataclass(frozen=True)
class GardenStats:
    ingested: int
    failed: int
    moved: int = 0
    deduped: int = 0
    reconciled: int = 0
```

Delete `_cleanup_ttl`, `_soft_delete`, the `_TTL_HOURS` constant, and the `self.deleted_root` assignment. Remove `"_deleted_with_ttl"` from `_EXCLUDED_DIRS` (the folder no longer exists post-migration; leaving the exclusion is harmless but dead).

**Step 4: Update existing gardener tests**

Several existing tests (`TestDiscoverRawFiles`, `TestMaxFilesPerRun`, any TTL tests) will break because:

- `_discover_raw_files` is no longer called by `run()`.
- `GardenStats` no longer has `ttl_cleaned`.
- Tests that write raw files into `inbox/` and expect `_ingest_one` to be called without any `session` will need to pass a session.

For each broken test, either:

- Update the test to pass `session=session` and pre-populate `RawInput` rows, or
- Delete tests that specifically exercised removed functionality (`_cleanup_ttl` / `_soft_delete`).

Run: `bb remote test //projects/monolith:knowledge_gardener_test //projects/monolith:knowledge_gardener_coverage_test --config=ci`
Expected: Fix until all PASS. Keep test count roughly stable — don't silently delete coverage.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/gardener.py \
        projects/monolith/knowledge/gardener_test.py \
        projects/monolith/knowledge/gardener_coverage_test.py
git commit -m "refactor(knowledge): gardener loop becomes move then reconcile then decompose"
```

---

## Task 8: Prompt update + pending provenance capture after Claude subprocess

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Modify: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write failing test**

The test stubs out `_ingest_one`'s internals by monkeypatching a small seam. Refactor the subprocess invocation out into a private method `_run_claude_subprocess(prompt)` so the test can replace it with an `AsyncMock` that just writes a fake produced file.

```python
class TestIngestOneRecordsPendingProvenance:
    @pytest.mark.asyncio
    async def test_inserts_pending_provenance_for_new_files(
        self, tmp_path, session
    ):
        """After claude produces atoms, the gardener records
        pending atom_raw_provenance rows keyed by derived_note_id."""
        from knowledge.gardener import Gardener, GARDENER_VERSION
        from knowledge.models import AtomRawProvenance, RawInput
        from sqlmodel import select

        (tmp_path / "_raw" / "2026" / "04" / "09").mkdir(parents=True)
        raw_rel_path = "_raw/2026/04/09/r1-n.md"
        (tmp_path / raw_rel_path).write_text("Body.", encoding="utf-8")
        (tmp_path / "_processed").mkdir()

        raw = RawInput(
            raw_id="r1",
            path=raw_rel_path,
            source="vault-drop",
            content="Body.",
            content_hash="r1",
        )
        session.add(raw)
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)

        async def fake_subprocess(prompt: str) -> None:
            (tmp_path / "_processed" / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nBody.\n",
                encoding="utf-8",
            )

        gardener._run_claude_subprocess = fake_subprocess  # type: ignore[method-assign]

        await gardener._ingest_one(tmp_path / raw_rel_path)
        session.commit()

        rows = session.exec(select(AtomRawProvenance)).all()
        assert len(rows) == 1
        assert rows[0].raw_fk == raw.id
        assert rows[0].atom_fk is None
        assert rows[0].derived_note_id == "hello"
        assert rows[0].gardener_version == GARDENER_VERSION
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: FAIL — provenance rows not inserted; method `_run_claude_subprocess` does not yet exist as a seam.

**Step 3: Implement**

1. Extract the existing claude subprocess logic from `_ingest_one` into a new async method `_run_claude_subprocess(self, prompt: str) -> None` that kicks off the subprocess, waits for it, and raises on non-zero exit or timeout. Everything in the current `_ingest_one` between "build prompt" and "diff before/after" moves into this method.

2. After the subprocess completes and the `after - before` diff is taken, parse each new file's frontmatter and insert a pending provenance row:

```python
new_files = sorted(after - before)
if not new_files:
    logger.warning(
        "gardener: claude produced no notes for %s; leaving raw file in place",
        path,
    )
    return

if self.session is not None:
    raw_row = self.session.exec(
        select(RawInput).where(
            RawInput.path == str(path.relative_to(self.vault_root))
        )
    ).first()
    if raw_row is not None:
        for new_file in new_files:
            try:
                meta, _ = frontmatter.parse(
                    new_file.read_text(encoding="utf-8")
                )
                note_id = meta.id
            except Exception:
                continue
            if not note_id:
                continue
            self.session.add(
                AtomRawProvenance(
                    raw_fk=raw_row.id,
                    derived_note_id=note_id,
                    gardener_version=GARDENER_VERSION,
                )
            )
        self.session.commit()
```

3. **Remove** the `self._soft_delete(path)` call at the end of `_ingest_one`. Raws stay in `_raw/` forever now.

4. Update `_CLAUDE_PROMPT_HEADER` to instruct Claude to stamp the source raw_id in each produced note as `derived_from_raw: <raw_id>` (belt-and-braces audit breadcrumb):

```python
_CLAUDE_PROMPT_HEADER = """\
You are a knowledge gardener. Decompose the raw note below into atomic knowledge artifacts.

Source raw_id: {raw_id}
Include `derived_from_raw: {raw_id}` as a frontmatter field in every note you create.

Steps:
...
"""
```

Pass `raw_id` into the `.format(...)` call — read it by looking up the `RawInput` row via `path`.

**Step 4: Run test — verify pass**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/gardener.py \
        projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): gardener records pending provenance after decomposition"
```

---

## Task 9: Pending provenance resolver

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Modify: `projects/monolith/knowledge/gardener_test.py`

At the start of each cycle, resolve any pending rows (`atom_fk IS NULL AND derived_note_id IS NOT NULL`) by looking up `knowledge.notes.note_id = derived_note_id` and populating `atom_fk`.

**Step 1: Write failing test**

```python
class TestResolvePendingProvenance:
    def test_resolves_note_id_to_atom_fk(self, tmp_path, session):
        from knowledge.gardener import Gardener, GARDENER_VERSION
        from knowledge.models import AtomRawProvenance, Note, RawInput
        from sqlmodel import select

        raw = RawInput(
            raw_id="r1",
            path="_raw/2026/04/09/r1.md",
            source="vault-drop",
            content="Body.",
            content_hash="r1",
        )
        note = Note(
            note_id="hello",
            path="_processed/atoms/hello.md",
            title="Hello",
            content_hash="h1",
            type="atom",
        )
        session.add_all([raw, note])
        session.flush()
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                derived_note_id="hello",
                gardener_version=GARDENER_VERSION,
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        resolved = gardener._resolve_pending_provenance()
        session.commit()

        assert resolved == 1
        rows = session.exec(select(AtomRawProvenance)).all()
        assert len(rows) == 1
        assert rows[0].atom_fk == note.id
        assert rows[0].derived_note_id is None

    def test_leaves_unresolved_when_note_missing(self, tmp_path, session):
        from knowledge.gardener import Gardener, GARDENER_VERSION
        from knowledge.models import AtomRawProvenance, RawInput
        from sqlmodel import select

        raw = RawInput(
            raw_id="r1",
            path="_raw/2026/04/09/r1.md",
            source="vault-drop",
            content="Body.",
            content_hash="r1",
        )
        session.add(raw)
        session.flush()
        session.add(
            AtomRawProvenance(
                raw_fk=raw.id,
                derived_note_id="ghost",
                gardener_version=GARDENER_VERSION,
            )
        )
        session.commit()

        gardener = Gardener(vault_root=tmp_path, session=session)
        assert gardener._resolve_pending_provenance() == 0
        row = session.exec(select(AtomRawProvenance)).first()
        assert row.atom_fk is None
        assert row.derived_note_id == "ghost"
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: FAIL.

**Step 3: Implement + wire into `run()`**

```python
def _resolve_pending_provenance(self) -> int:
    if self.session is None:
        return 0
    pending = self.session.exec(
        select(AtomRawProvenance).where(
            and_(
                AtomRawProvenance.atom_fk.is_(None),
                AtomRawProvenance.derived_note_id.is_not(None),
            )
        )
    ).all()
    resolved = 0
    for row in pending:
        note = self.session.exec(
            select(Note).where(Note.note_id == row.derived_note_id)
        ).first()
        if note is None:
            continue
        row.atom_fk = note.id
        row.derived_note_id = None
        self.session.add(row)
        resolved += 1
    return resolved
```

Add a call to `_resolve_pending_provenance()` at the top of `Gardener.run()` (before the move phase) and include its count in `GardenStats` (add a `resolved` field, defaulting to 0).

**Step 4: Run — verify pass**

Run: `bb remote test //projects/monolith:knowledge_gardener_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/gardener.py \
        projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): resolve pending atom_raw_provenance rows each cycle"
```

---

## Task 10: Wire session into `garden_handler`

**Files:**

- Modify: `projects/monolith/knowledge/service.py`
- Modify: `projects/monolith/knowledge/service_test.py`

**Step 1: Write failing test**

Find the existing `service_test.py` garden handler test and add:

```python
@pytest.mark.asyncio
async def test_garden_handler_passes_session_to_gardener(
    session, monkeypatch, tmp_path
):
    """garden_handler must hand the DB session to the Gardener so
    provenance can be recorded."""
    import knowledge.service as svc
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

    captured: dict = {}

    class FakeGardener:
        def __init__(self, *, vault_root, max_files_per_run, session):
            captured["session"] = session
            captured["vault_root"] = vault_root

        async def run(self):
            from knowledge.gardener import GardenStats
            return GardenStats(ingested=0, failed=0)

    monkeypatch.setattr("knowledge.gardener.Gardener", FakeGardener)

    await svc.garden_handler(session)
    assert captured["session"] is session
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: FAIL — session not passed.

**Step 3: Implement**

In `service.py` `garden_handler`, pass `session=session` to the `Gardener(...)` constructor. Update the log `extra` dict to include `moved`, `deduped`, `reconciled`, `resolved` and drop `ttl_cleaned`.

**Step 4: Run — verify pass**

Run: `bb remote test //projects/monolith:knowledge_service_test //projects/monolith:knowledge_service_coverage_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/service.py \
        projects/monolith/knowledge/service_test.py
git commit -m "feat(knowledge): garden_handler wires session into Gardener"
```

---

## Task 11: One-shot grandfathering migration script

**Files:**

- Create: `projects/monolith/knowledge/migrate_raw_bucketing.py`
- Create: `projects/monolith/knowledge/migrate_raw_bucketing_test.py`

**Step 1: Write failing tests**

```python
"""Tests for the one-shot raw bucketing migration script."""

from pathlib import Path

import pytest
from sqlmodel import select

from knowledge.migrate_raw_bucketing import run_migration
from knowledge.models import AtomRawProvenance, Note, RawInput


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestRunMigration:
    def test_moves_deleted_ttl_files_into_raw_grandfathered(
        self, tmp_path, session
    ):
        _write(
            tmp_path / "_deleted_with_ttl" / "inbox" / "old.md",
            "---\ntitle: Old\nttl: 2026-04-09T00:00:00Z\noriginal_path: inbox/old.md\n---\nBody.",
        )

        run_migration(vault_root=tmp_path, session=session)
        session.commit()

        # _deleted_with_ttl removed.
        assert not (tmp_path / "_deleted_with_ttl").exists()
        # Moved into _raw/grandfathered.
        gf = tmp_path / "_raw" / "grandfathered"
        files = list(gf.glob("*.md"))
        assert len(files) == 1
        # ttl stripped, original_path stripped.
        body = files[0].read_text(encoding="utf-8")
        assert "ttl:" not in body
        assert "original_path:" not in body

        # raw_inputs row + mirror note row + raw sentinel provenance row.
        raws = session.exec(select(RawInput)).all()
        assert len(raws) == 1
        assert raws[0].source == "grandfathered"
        assert raws[0].original_path == "inbox/old.md"

        mirror = session.exec(
            select(Note).where(Note.type == "raw")
        ).all()
        assert len(mirror) == 1

        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration"
            )
        ).all()
        raw_sentinels = [s for s in sentinels if s.atom_fk is None]
        assert len(raw_sentinels) == 1
        assert raw_sentinels[0].raw_fk == raws[0].id

    def test_grandfathers_existing_atoms(self, tmp_path, session):
        atom = Note(
            note_id="pre-existing",
            path="_processed/atoms/pre-existing.md",
            title="Pre",
            content_hash="h",
            type="atom",
        )
        session.add(atom)
        session.commit()

        run_migration(vault_root=tmp_path, session=session)
        session.commit()

        atom_sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.atom_fk == atom.id,
                AtomRawProvenance.gardener_version == "pre-migration",
            )
        ).all()
        assert len(atom_sentinels) == 1
        assert atom_sentinels[0].raw_fk is None

    def test_is_idempotent(self, tmp_path, session):
        _write(
            tmp_path / "_deleted_with_ttl" / "old.md",
            "---\ntitle: Old\n---\nBody.",
        )
        atom = Note(
            note_id="a",
            path="_processed/atoms/a.md",
            title="A",
            content_hash="h",
            type="atom",
        )
        session.add(atom)
        session.commit()

        run_migration(vault_root=tmp_path, session=session)
        session.commit()
        run_migration(vault_root=tmp_path, session=session)
        session.commit()

        raws = session.exec(select(RawInput)).all()
        assert len(raws) == 1
        sentinels = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.gardener_version == "pre-migration"
            )
        ).all()
        # One raw sentinel + one atom sentinel.
        assert len(sentinels) == 2
```

**Step 2: Run — verify fail**

Run: `bb remote test //projects/monolith:knowledge_migrate_raw_bucketing_test --config=ci`
Expected: FAIL — script doesn't exist.

**Step 3: Implement**

```python
"""One-shot migration: grandfather _deleted_with_ttl/ raws and existing atoms.

Intended to run once, offline, inside a maintenance window. Idempotent on
re-run: all inserts are guarded by existence checks so interrupted runs
can be resumed safely.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import yaml
from sqlmodel import Session, select

from knowledge import frontmatter
from knowledge.models import AtomRawProvenance, Note, RawInput
from knowledge.raw_paths import (
    GRANDFATHERED_SUBDIR,
    RAW_ROOT_NAME,
    compute_raw_id,
    raw_target_path,
)

logger = logging.getLogger("monolith.knowledge.migrate_raw_bucketing")

_PRE_MIGRATION = "pre-migration"
_DELETED_ROOT_NAME = "_deleted_with_ttl"
_STRIPPED_FRONTMATTER_KEYS = {"ttl", "original_path"}


def _strip_frontmatter_keys(content: str, keys: set[str]) -> str:
    if not content.startswith("---"):
        return content
    lines = content.splitlines(keepends=True)
    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end = i
            break
    if end is None:
        return content
    block = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        meta = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return content
    if not isinstance(meta, dict):
        return content
    for k in keys:
        meta.pop(k, None)
    if not meta:
        return body
    return f"---\n{yaml.safe_dump(meta, sort_keys=False).rstrip()}\n---\n{body}"


def _grandfather_raws(vault_root: Path, session: Session) -> int:
    deleted_root = vault_root / _DELETED_ROOT_NAME
    if not deleted_root.exists():
        return 0
    inserted = 0
    for src in sorted(deleted_root.rglob("*.md")):
        raw_content = src.read_text(encoding="utf-8")
        meta, _ = frontmatter.parse(raw_content)
        original_path = (meta.extra.get("original_path") if meta else None)
        stripped = _strip_frontmatter_keys(raw_content, _STRIPPED_FRONTMATTER_KEYS)
        raw_id = compute_raw_id(stripped)
        title = (meta.title if meta and meta.title else src.stem)
        target = raw_target_path(
            vault_root=vault_root,
            raw_id=raw_id,
            title=title,
            grandfathered=True,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(stripped, encoding="utf-8")
        src.unlink()

        rel = target.relative_to(vault_root).as_posix()
        existing = session.exec(
            select(RawInput).where(RawInput.raw_id == raw_id)
        ).first()
        if existing is None:
            raw_row = RawInput(
                raw_id=raw_id,
                path=rel,
                source="grandfathered",
                original_path=original_path,
                content=stripped,
                content_hash=raw_id,
            )
            session.add(raw_row)
            session.flush()
            session.add(
                Note(
                    note_id=raw_id,
                    path=rel,
                    title=title,
                    content_hash=raw_id,
                    type="raw",
                    source="grandfathered",
                )
            )
            session.add(
                AtomRawProvenance(
                    raw_fk=raw_row.id,
                    gardener_version=_PRE_MIGRATION,
                )
            )
            inserted += 1

    shutil.rmtree(deleted_root, ignore_errors=True)
    return inserted


def _grandfather_atoms(session: Session) -> int:
    atoms = session.exec(
        select(Note).where(Note.type.in_(["atom", "fact", "active"]))
    ).all()
    inserted = 0
    for atom in atoms:
        existing = session.exec(
            select(AtomRawProvenance).where(
                AtomRawProvenance.atom_fk == atom.id,
                AtomRawProvenance.raw_fk.is_(None),
                AtomRawProvenance.gardener_version == _PRE_MIGRATION,
            )
        ).first()
        if existing is not None:
            continue
        session.add(
            AtomRawProvenance(
                atom_fk=atom.id,
                gardener_version=_PRE_MIGRATION,
            )
        )
        inserted += 1
    return inserted


def run_migration(*, vault_root: Path, session: Session) -> None:
    """Execute the one-shot raw bucketing migration. Idempotent."""
    raws = _grandfather_raws(vault_root, session)
    atoms = _grandfather_atoms(session)
    logger.info(
        "raw-bucketing migration: grandfathered raws=%d atoms=%d",
        raws, atoms,
    )
```

**Step 4: Run — verify pass**

Run: `bb remote test //projects/monolith:knowledge_migrate_raw_bucketing_test --config=ci`
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/migrate_raw_bucketing.py \
        projects/monolith/knowledge/migrate_raw_bucketing_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add one-shot raw bucketing migration script"
```

---

## Task 12: Migration script CLI entrypoint

**Files:**

- Modify: `projects/monolith/knowledge/migrate_raw_bucketing.py`

**Step 1: Add a `main()` + `__main__` block**

Append to `migrate_raw_bucketing.py`:

```python
def main() -> None:
    import argparse
    import os

    from sqlalchemy import create_engine

    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-root", default=os.environ.get("VAULT_ROOT", "/vault"))
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()

    if not args.dsn:
        raise SystemExit("--dsn or DATABASE_URL is required")

    logging.basicConfig(level=logging.INFO)
    engine = create_engine(args.dsn)
    with Session(engine) as session:
        run_migration(vault_root=Path(args.vault_root), session=session)
        session.commit()


if __name__ == "__main__":
    main()
```

No new test needed — `run_migration` is already covered. This is a thin CLI wrapper.

**Step 2: Commit**

```bash
git add projects/monolith/knowledge/migrate_raw_bucketing.py
git commit -m "feat(knowledge): add CLI entrypoint for raw bucketing migration"
```

---

## Task 13: PR + execution

**Step 1: Push and create PR**

```bash
git push -u origin feat/knowledge-raw-bucketing
gh pr create --title "feat(knowledge): raw bucketing + provenance tracking" --body "$(cat <<'EOF'
## Summary

- Immutable `_raw/` bucket + `knowledge.raw_inputs` table preserves every ingested note forever
- Many-to-many `knowledge.atom_raw_provenance` with `gardener_version` enables future reprocessing
- Gardener loop becomes move → reconcile → decompose, all crash-safe
- One-shot grandfathering migration handles `_deleted_with_ttl/` contents + existing atoms
- Ties out to design: `docs/plans/2026-04-09-knowledge-raw-bucketing-design.md`

## Test plan

- [ ] `bb remote test //projects/monolith/... --config=ci`
- [ ] Locally render chart: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml`
- [ ] Dry-run migration script against a DB snapshot
EOF
)"
```

**Step 2: Wait for CI + merge**

Poll: `gh pr view --json state,mergeStateStatus`

**Step 3: Run maintenance window**

Runbook (executed manually, outside this plan):

1. Set `backend.replicas: 0` in `projects/monolith/deploy/values.yaml`, commit + PR + merge.
2. Wait for ArgoCD to scale the monolith pod to 0.
3. Port-forward Postgres; run `python -m knowledge.migrate_raw_bucketing --vault-root /path/to/mounted/vault --dsn postgres://...`.
4. Verify: `SELECT source, COUNT(*) FROM knowledge.raw_inputs GROUP BY source;` and `SELECT gardener_version, COUNT(*) FROM knowledge.atom_raw_provenance GROUP BY gardener_version;`.
5. Set `backend.replicas: 1`, commit + PR + merge.
6. Watch the first gardener cycle via the scheduler logs — expect `moved=N reconciled=N ingested=0` if only grandfathered data exists (the sentinels block decomposition).

---

## Open decisions deferred

- **Search type filter UI** — default search excludes `type='raw'`; exposing a toggle is future work
- **Manual reprocessing command** — the DB machinery is in place (query `WHERE gardener_version != :current`), the CLI/API wrapper is deferred
- **Vault `_raw/` size monitoring** — add an alert once the table reaches some reasonable threshold; not for this PR
