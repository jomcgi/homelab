-- Split inline attachment blobs into a content-addressed store so that
-- duplicate images are stored once and vision descriptions are reused.

CREATE TABLE chat.blobs (
    sha256 CHAR(64) PRIMARY KEY,
    data BYTEA NOT NULL,
    content_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

-- Populate blobs from existing attachments (dedup by content hash).
INSERT INTO chat.blobs (sha256, data, content_type, description)
SELECT DISTINCT ON (encode(sha256(data), 'hex'))
       encode(sha256(data), 'hex'),
       data,
       content_type,
       description
FROM chat.attachments
ON CONFLICT DO NOTHING;

-- Add the FK column and backfill from existing data.
ALTER TABLE chat.attachments ADD COLUMN blob_sha256 CHAR(64);

UPDATE chat.attachments
SET blob_sha256 = encode(sha256(data), 'hex');

ALTER TABLE chat.attachments
    ALTER COLUMN blob_sha256 SET NOT NULL,
    ADD CONSTRAINT fk_attachments_blob FOREIGN KEY (blob_sha256) REFERENCES chat.blobs(sha256);

-- Drop the columns that now live in blobs.
ALTER TABLE chat.attachments
    DROP COLUMN data,
    DROP COLUMN content_type,
    DROP COLUMN description;
