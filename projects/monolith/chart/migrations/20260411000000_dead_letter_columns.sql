-- Add dead letter tracking columns to atom_raw_provenance.
ALTER TABLE knowledge.atom_raw_provenance
    ADD COLUMN error TEXT,
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
