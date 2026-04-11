-- Add dead letter tracking columns to atom_raw_provenance.
ALTER TABLE knowledge.atom_raw_provenance
    ADD COLUMN error TEXT,
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;

-- Unblock YouTube videos wrongly grandfathered on 2026-04-11.
DELETE FROM knowledge.atom_raw_provenance
WHERE raw_fk IN (
    SELECT id FROM knowledge.raw_inputs
    WHERE source = 'youtube'
      AND path LIKE '_raw/2026/04/11/%'
)
AND gardener_version = 'pre-migration';
