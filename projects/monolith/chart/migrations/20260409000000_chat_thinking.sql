-- Add thinking column to chat.messages for storing raw model reasoning.
-- Not embedded -- stored as plain text for retrieval via Discord's "Show thinking" button.
ALTER TABLE chat.messages ADD COLUMN IF NOT EXISTS thinking TEXT;
