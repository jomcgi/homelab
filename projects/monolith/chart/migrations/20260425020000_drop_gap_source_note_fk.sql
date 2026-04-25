-- knowledge.gaps: drop source_note_fk column.
--
-- PR #2194 made source_note_fk nullable when the stub-notes pattern took
-- over as the source of truth for "which notes reference this gap".
-- The stub's referenced_by frontmatter list (and the note_links graph)
-- replace it. After running in production for a release cycle without
-- any reads, the column is now dead weight.
--
-- See docs/plans/2026-04-25-gap-classifier-stub-notes-design.md
-- ("Out of scope for this PR ... Dropping `source_note_fk` column —
--  happens in a follow-up once the stub pattern is stable").

ALTER TABLE knowledge.gaps DROP COLUMN source_note_fk;
