-- Channel-level rolling summaries for ambient bot context.

CREATE TABLE chat.channel_summaries (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    message_count INT NOT NULL DEFAULT 0,
    last_message_id INT NOT NULL REFERENCES chat.messages(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
