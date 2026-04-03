-- Enable pgvector extension and create chat schema for Discord chatbot.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS chat;

CREATE TABLE chat.messages (
    id SERIAL PRIMARY KEY,
    discord_message_id TEXT UNIQUE NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    is_bot BOOLEAN NOT NULL DEFAULT FALSE,
    embedding vector(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX chat_messages_channel_time ON chat.messages (channel_id, created_at DESC);
CREATE INDEX chat_messages_channel_user_time ON chat.messages (channel_id, user_id, created_at DESC);
CREATE INDEX chat_messages_embedding_hnsw ON chat.messages USING hnsw (embedding vector_cosine_ops);
