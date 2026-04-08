-- Vector dim 1024 = voyage-4-nano (matches chat.messages.embedding).
-- pgvector extension is already created cluster-wide via cnpg-cluster.yaml.

CREATE SCHEMA IF NOT EXISTS knowledge;

-- One row per .md file under /vault/_processed.
CREATE TABLE knowledge.notes (
    id            BIGSERIAL PRIMARY KEY,
    note_id       TEXT NOT NULL UNIQUE,        -- stable graph identity from frontmatter `id:` (auto-backfilled if missing)
    path          TEXT NOT NULL UNIQUE,        -- current file location, relative to /vault, e.g. "_processed/papers/attention.md"
    title         TEXT NOT NULL,               -- frontmatter.title or filename stem
    content_hash  TEXT NOT NULL,               -- sha256 of full file bytes (drives reconciliation)

    -- Promoted frontmatter columns.
    type          TEXT,                        -- e.g. note | daily | project | paper | fleeting
    status        TEXT,                        -- e.g. draft | active | archived | published
    source        TEXT,                        -- e.g. web-ui | discord | manual | clipper
    tags          TEXT[]      NOT NULL DEFAULT '{}',
    aliases       TEXT[]      NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ,                 -- frontmatter.created or NULL
    updated_at    TIMESTAMPTZ,                 -- frontmatter.updated or NULL
    extra         JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- everything else from frontmatter

    -- Bookkeeping.
    indexed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX notes_note_id     ON knowledge.notes (note_id);
CREATE INDEX notes_tags_gin    ON knowledge.notes USING gin (tags);
CREATE INDEX notes_aliases_gin ON knowledge.notes USING gin (aliases);
CREATE INDEX notes_extra_gin   ON knowledge.notes USING gin (extra);
CREATE INDEX notes_type        ON knowledge.notes (type);
CREATE INDEX notes_status      ON knowledge.notes (status);
CREATE INDEX notes_source      ON knowledge.notes (source);
CREATE INDEX notes_updated_at  ON knowledge.notes (updated_at DESC);

-- One row per chunk. Re-chunked + re-embedded whenever the parent's content_hash changes.
CREATE TABLE knowledge.chunks (
    id              BIGSERIAL PRIMARY KEY,
    note_id         BIGINT      NOT NULL REFERENCES knowledge.notes(id) ON DELETE CASCADE,
    chunk_index     INTEGER     NOT NULL,
    section_header  TEXT        NOT NULL DEFAULT '',
    chunk_text      TEXT        NOT NULL,
    embedding       vector(1024) NOT NULL,
    UNIQUE (note_id, chunk_index)
);

CREATE INDEX chunks_embedding_hnsw ON knowledge.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_note_id        ON knowledge.chunks (note_id);

-- Edge table for graph queries. Targets are stable note ids (strings), not FKs,
-- because edges may dangle (point at non-existent or not-yet-ingested notes).
--
-- Two-level taxonomy:
--   kind='edge' → declared semantic relationship from frontmatter `edges:` block;
--                 edge_type names the relationship.
--   kind='link' → untyped body wikilink ([[Foo]]); edge_type is NULL.
--
-- Adding a new edge_type is a code change, not a schema migration.
CREATE TABLE knowledge.note_links (
    id            BIGSERIAL PRIMARY KEY,
    src_note_id   BIGINT NOT NULL REFERENCES knowledge.notes(id) ON DELETE CASCADE,
    target_id     TEXT   NOT NULL,             -- target note_id (frontmatter id) or raw wikilink target
    target_title  TEXT,                        -- display text from [[Foo|display]] when present
    kind          TEXT   NOT NULL CHECK (kind IN ('edge', 'link')),
    edge_type     TEXT   CHECK (
                    (kind = 'edge' AND edge_type IN (
                      'refines', 'generalizes', 'related',
                      'contradicts', 'derives_from', 'supersedes'
                    )) OR
                    (kind = 'link' AND edge_type IS NULL)
                  ),
    UNIQUE (src_note_id, target_id, kind, edge_type)
);

CREATE INDEX note_links_target    ON knowledge.note_links (target_id);
CREATE INDEX note_links_kind      ON knowledge.note_links (kind);
CREATE INDEX note_links_edge_type ON knowledge.note_links (edge_type) WHERE edge_type IS NOT NULL;
