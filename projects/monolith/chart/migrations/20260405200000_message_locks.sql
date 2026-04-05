-- Lightweight lock table for multi-pod message deduplication.
-- Pods race to INSERT before doing expensive work (embedding, LLM).
-- Expired uncompleted locks are reclaimed via SELECT FOR UPDATE SKIP LOCKED.

CREATE TABLE chat.message_locks (
    discord_message_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX message_locks_reclaim ON chat.message_locks (completed, claimed_at)
    WHERE NOT completed;
