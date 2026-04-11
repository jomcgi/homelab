-- knowledge.ingest_queue: URL-based content ingestion queue.
--
-- Rows are never deleted — the queue doubles as an audit log.
-- A row stuck in 'processing' for >5 minutes is re-claimable (TTL).

CREATE TABLE knowledge.ingest_queue (
    id           BIGSERIAL    PRIMARY KEY,
    url          TEXT         NOT NULL,
    source_type  TEXT         NOT NULL CHECK (source_type IN ('youtube', 'webpage')),
    status       TEXT         NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    error        TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    started_at   TIMESTAMPTZ,
    processed_at TIMESTAMPTZ
);

CREATE INDEX ingest_queue_status ON knowledge.ingest_queue (status)
    WHERE status = 'pending';
CREATE INDEX ingest_queue_created_at ON knowledge.ingest_queue (created_at DESC);
