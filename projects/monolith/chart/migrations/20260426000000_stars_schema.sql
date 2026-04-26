-- Stars domain: dark-sky locations refresh history.
-- One row per scheduled refresh; reads always target the latest status='ok' row.

CREATE SCHEMA IF NOT EXISTS stars;

CREATE TABLE stars.refresh_runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL,           -- 'ok' | 'error' | 'running'
    locations_count INTEGER,
    payload         JSONB,
    error           TEXT
);

-- Hot path: latest successful refresh.
CREATE INDEX idx_stars_refresh_runs_ok_completed
    ON stars.refresh_runs (completed_at DESC)
    WHERE status = 'ok';
