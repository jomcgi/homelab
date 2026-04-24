-- knowledge.gaps: enforce UNIQUE(note_id).
--
-- PR #2194's migration enforced UNIQUE(term), but two terms can slugify to
-- the same note_id (e.g. "Outside-In TDD" and "Outside In TDD" both →
-- outside-in-tdd). The reconciler queries Gap rows by note_id and crashes
-- on MultipleResultsFound when collisions exist.
--
-- Dedup keeping the earliest row per note_id, then add the constraint as
-- the projection-layer guarantee. See
-- docs/plans/2026-04-24-gap-classifier-hotfix-design.md.

-- 1. Dedup by note_id, keeping the earliest row per slug.
WITH winners AS (
  SELECT MIN(id) AS id
  FROM knowledge.gaps
  WHERE note_id IS NOT NULL
  GROUP BY note_id
)
DELETE FROM knowledge.gaps
WHERE note_id IS NOT NULL
  AND id NOT IN (SELECT id FROM winners);

-- 2. Drop the non-unique index in favor of the constraint's auto-index.
DROP INDEX IF EXISTS knowledge.gaps_note_id;

-- 3. The new invariant.
ALTER TABLE knowledge.gaps
  ADD CONSTRAINT gaps_note_id_unique UNIQUE (note_id);
