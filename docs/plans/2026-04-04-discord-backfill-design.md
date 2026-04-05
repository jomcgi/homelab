# Discord History Backfill — Design

**Date:** 2026-04-04
**Status:** Approved
**ADR:** `docs/decisions/services/001-discord-history-backfill.md`

---

## Summary

Add a `POST /api/chat/backfill` endpoint to the monolith that backfills all Discord channel history into PostgreSQL with embeddings and image attachments. Fire-and-forget — returns 202 immediately, runs as a background task, observable via SigNoz logs.

## Decisions

| Decision           | Choice                                            | Rationale                                                               |
| ------------------ | ------------------------------------------------- | ----------------------------------------------------------------------- |
| Execution model    | Background `asyncio.Task`, no status endpoint     | SigNoz logging is sufficient; YAGNI on progress API                     |
| Channel processing | Sequential (one at a time)                        | Simple, predictable, easy to resume; speed not critical for one-time op |
| Image handling     | Process all images inline                         | Complete data in one pass; no second pass needed                        |
| Embedding strategy | Batch (50 messages per API call)                  | Primary throughput bottleneck; llama.cpp supports array input natively  |
| Duplicate handling | Per-message `IntegrityError` catch via savepoints | Idempotent re-runs; partial failures don't roll back the batch          |
| Bot access         | `app.state.bot` set in lifespan                   | Simplest way to share the Discord client with routes                    |
| Concurrency guard  | `app.state.backfill_task` reference               | 409 if already running; no need for locks or queues                     |

## API Surface

```
POST /api/chat/backfill
→ 202 Accepted {"status": "started", "channels": 5}
→ 409 Conflict  (if backfill already running)
→ 503 Service Unavailable  (if Discord bot not connected)
```

No status endpoint. Progress is logged to SigNoz per channel and per batch.

## Component Changes

### 1. `EmbeddingClient.embed_batch()`

New method on `chat/embedding.py`:

- Sends array `input` to `/v1/embeddings` in a single HTTP call
- Returns vectors sorted by response `index` field (OpenAI-compatible API ordering)
- `embed()` becomes a wrapper: `return (await self.embed_batch([text]))[0]`

### 2. `MessageStore.save_messages()`

Refactor from `save_message()` on `chat/store.py`:

- Accepts a list of message dicts with pre-computed embeddings
- Calls `embed_batch()` once for the whole batch
- Inserts individually using `session.begin_nested()` (savepoints) to isolate `IntegrityError` per message
- Single `commit()` at the end for all successful inserts
- Returns `SaveResult(stored=N, skipped=M)`
- Real-time path calls `save_messages([single_msg])`

### 3. `chat/backfill.py` — Backfill Loop

```
async def run_backfill(bot: ChatBot) -> None:
    for channel in text_channels:
        for message in channel.history(oldest_first=True):
            process image attachments via download_image_attachments()
            accumulate into batch of 50
            when full → save_messages(batch), log progress
        flush remaining partial batch
        log channel summary
    log overall summary
```

- Reuses `download_image_attachments()` from `bot.py` for image processing
- New `Session` per batch to avoid long-lived transactions
- discord.py handles Discord API rate limiting transparently
- Includes bot messages (`is_bot=True`) for full conversation context

### 4. `chat/router.py` — FastAPI Route

```python
POST /api/chat/backfill → launches asyncio.create_task(run_backfill(bot))
```

- Reads bot from `request.app.state.bot`
- Guards against concurrent runs via `app.state.backfill_task`

### 5. `app/main.py` — Wiring

- Set `app.state.bot = bot` in lifespan (or `None` if no token)
- Set `app.state.backfill_task = None`
- Register `chat_router` before static files mount

## Security

- Endpoint on `private.jomcgi.dev`, gated by Cloudflare Access SSO
- No new secrets — reuses existing `DISCORD_BOT_TOKEN`
- Image data limited to bot's existing Discord permissions
