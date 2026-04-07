-- Postgres-backed scheduler: job registry with distributed locking.
-- Pods claim due jobs via SELECT FOR UPDATE SKIP LOCKED.

CREATE SCHEMA IF NOT EXISTS scheduler;

CREATE TABLE scheduler.scheduled_jobs (
    name           TEXT PRIMARY KEY,
    interval_secs  INTEGER NOT NULL,
    next_run_at    TIMESTAMPTZ NOT NULL,
    last_run_at    TIMESTAMPTZ,
    last_status    TEXT,
    locked_by      TEXT,
    locked_at      TIMESTAMPTZ,
    ttl_secs       INTEGER NOT NULL DEFAULT 300
);
