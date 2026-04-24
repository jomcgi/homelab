-- knowledge gaps: stub notes become source of truth.
--
-- PR #2193 shipped the gaps table with (term, source_note_fk) identity.
-- This migration pivots to term-global identity, adds the stub-note link,
-- and dedupes. See docs/plans/2026-04-25-gap-classifier-stub-notes-design.md.

-- 1. Stub ↔ gap connection via string identity (matches
--    AtomRawProvenance.derived_note_id pattern — resolves as soon as the
--    stub lands in knowledge.notes, regardless of order).
ALTER TABLE knowledge.gaps
  ADD COLUMN note_id TEXT;

CREATE INDEX gaps_note_id ON knowledge.gaps (note_id);

-- 2. Collapse (term, source) duplicates to (term). Keep the oldest row
--    per term (earliest discovery timestamp).
WITH winners AS (
  SELECT MIN(id) AS id
  FROM knowledge.gaps
  GROUP BY term
)
DELETE FROM knowledge.gaps
WHERE id NOT IN (SELECT id FROM winners);

-- 3. Swap uniqueness: one gap per term globally.
ALTER TABLE knowledge.gaps
  DROP CONSTRAINT gaps_term_source_note_fk_key;

ALTER TABLE knowledge.gaps
  ADD CONSTRAINT gaps_term_unique UNIQUE (term);

-- 4. source_note_fk loses its authoritative role — stub's referenced_by
--    frontmatter + note_links graph replace it. Nullable for now; dropped
--    in a follow-up migration once the stub pattern is stable.
ALTER TABLE knowledge.gaps
  ALTER COLUMN source_note_fk DROP NOT NULL;
