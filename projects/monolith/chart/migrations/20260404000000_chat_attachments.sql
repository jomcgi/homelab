CREATE TABLE chat.attachments (
    id SERIAL PRIMARY KEY,
    message_id INT NOT NULL REFERENCES chat.messages(id) ON DELETE CASCADE,
    data BYTEA NOT NULL,
    content_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE INDEX chat_attachments_message_id ON chat.attachments (message_id);
