-- knowledge gaps: unresolved wikilinks promoted to trackable work items
-- for the gap-driven knowledge graph (see docs/plans/2026-04-24-gap-driven-knowledge-graph-design.md).
--
-- A gap is an unresolved [[wikilink]] that becomes a research agenda item.
-- Each gap tracks its class (external/internal/hybrid/parked) and state through
-- the pipeline. Internal gaps drain through the review queue; external gaps
-- route to automated research (not yet implemented in this slice).

CREATE TABLE knowledge.gaps (
    id               BIGSERIAL    PRIMARY KEY,
    term             TEXT         NOT NULL,
    context          TEXT         NOT NULL DEFAULT '',
    source_note_fk   BIGINT       REFERENCES knowledge.notes(id) ON DELETE CASCADE,
    gap_class        TEXT         CHECK (gap_class IN ('external','internal','hybrid','parked')),
    state            TEXT         NOT NULL DEFAULT 'discovered'
                                  CHECK (state IN ('discovered','classified','in_review',
                                                   'researched','verified','consolidated',
                                                   'committed','rejected')),
    answer           TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    classified_at   TIMESTAMPTZ,
    resolved_at      TIMESTAMPTZ,
    pipeline_version TEXT         NOT NULL,
    UNIQUE (term, source_note_fk)
);

CREATE INDEX gaps_state ON knowledge.gaps (state);
CREATE INDEX gaps_class ON knowledge.gaps (gap_class);
CREATE INDEX gaps_term  ON knowledge.gaps (term);
