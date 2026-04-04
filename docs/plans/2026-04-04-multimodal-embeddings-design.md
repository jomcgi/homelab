# Multi-Modal Discord Message Embeddings

**Date:** 2026-04-04
**Status:** Approved

## Goal

Enable the Discord bot to process, store, and semantically search image attachments alongside text messages. Images are described by Gemma 4 (vision), embedded by voyage-4-nano, and stored as raw bytes in PostgreSQL for later retrieval.

## Data Flow

### Ingestion (on message received)

```
Discord message with image attachment(s)
  -> filter attachments where content_type starts with "image/"
  -> for each image:
      -> download bytes from Discord CDN
      -> store raw bytes + metadata in chat.attachments
      -> base64 encode -> Gemma 4 /v1/chat/completions (vision) -> text description
      -> store description on attachment row
  -> embed combined text: "{message.content}\n\n[Image: {desc1}]\n[Image: {desc2}]"
  -> store Message with embedding (unchanged schema)
```

### Response generation (image-aware recall)

```
User references a past image
  -> semantic search finds relevant Message via embedded description
  -> load associated Attachment rows (raw bytes)
  -> base64 encode images -> include in Gemma 4 chat completion as vision content
  -> Gemma generates response with actual visual context
```

## Schema

### New table: `chat.attachments`

| Column       | Type   | Notes                                     |
| ------------ | ------ | ----------------------------------------- |
| id           | SERIAL | PK                                        |
| message_id   | INT    | FK -> chat.messages.id, ON DELETE CASCADE |
| data         | BYTEA  | Raw image bytes                           |
| content_type | TEXT   | e.g. image/png                            |
| filename     | TEXT   | Original Discord filename                 |
| description  | TEXT   | Gemma 4 vision description                |

Separate table keeps `chat.messages` lean for text-only queries. Binary data is only loaded when explicitly needed (e.g., re-sending to Gemma for response generation).

### Existing table changes

None. The `chat.messages.embedding` column (vector(1024)) is unchanged. The embedding now encodes text + image descriptions combined, but the column type and index are the same.

## Components

### New: `vision.py` — VisionClient

Single method: `describe(image_bytes: bytes, content_type: str) -> str`

- Base64 encodes the image
- Sends to Gemma 4 via `/v1/chat/completions` with image_url content type
- System prompt: "Describe this image concisely for semantic search."
- Uses the existing `LLAMA_CPP_URL` endpoint

### Modified: `models.py`

Add `Attachment` SQLModel with FK to Message.

### Modified: `bot.py`

- In `on_message`: iterate `message.attachments`, filter for `image/*` content types
- Download each image via `httpx`
- Call `VisionClient.describe()` for each
- Pass attachment data to `store.save_message()`

### Modified: `store.py`

- `save_message()` accepts optional list of attachment tuples (bytes, content_type, filename, description)
- Embeds combined `content + image descriptions`
- Saves Attachment rows linked to the Message

### Modified: `agent.py`

- `_generate_response()` loads attachments for semantically similar messages
- Builds multi-modal content array (text + base64 images) for Gemma 4 chat completion
- `format_context_messages()` includes image descriptions in text context

## Design Decisions

- **Raw bytes in BYTEA**: Simple, transactional, no external dependencies. Acceptable for Discord-scale traffic.
- **No size cap**: Store whatever Discord sends. Revisit if DB growth becomes an issue.
- **All images processed**: Up to 10 per Discord message. Each gets its own Attachment row and Gemma description.
- **Re-send images at response time**: When the bot recalls a message with images, it re-sends the actual images to Gemma (not just the text description) for higher fidelity responses.
- **Separate attachments table**: Avoids bloating every Message SELECT with binary data.
