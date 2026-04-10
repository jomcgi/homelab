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
--       grandfathered atom with unknown source raw
--   (atom_fk = NULL, raw_fk = real, version = 'pre-migration')
--       raw already decomposed by a previous gardener run
--   (atom_fk = NULL, raw_fk = real, version != 'pre-migration',
--    derived_note_id IS NOT NULL)
--       gardener produced this atom but it's not yet in knowledge.notes;
--       the next cycle resolves derived_note_id to atom_fk.
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
