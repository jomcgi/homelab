-- knowledge.notes: add server-computed force-directed layout positions.
--
-- Both columns are nullable. The next reconcile cycle populates them; until
-- then, the frontend's random-center fallback handles missing values.

ALTER TABLE knowledge.notes
    ADD COLUMN layout_x DOUBLE PRECISION,
    ADD COLUMN layout_y DOUBLE PRECISION;
