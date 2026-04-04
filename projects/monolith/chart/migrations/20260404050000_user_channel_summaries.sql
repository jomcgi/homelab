-- Rolling per-user-per-channel summaries for chat agent context.

CREATE TABLE chat.user_channel_summaries (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    summary TEXT NOT NULL,
    last_message_id INT NOT NULL REFERENCES chat.messages(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, user_id)
);

CREATE INDEX chat_summaries_channel ON chat.user_channel_summaries (channel_id);
