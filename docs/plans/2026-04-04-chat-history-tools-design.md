# Chat History Tools + Rolling User Summaries

**Date:** 2026-04-04
**Status:** Approved
**Scope:** `projects/monolith/chat/`

## Problem

The chat bot pre-fetches 5 semantically similar older messages before the agent runs. This is a blind guess — the agent can't request more context when it realizes it needs it, and it can't filter by user or time. Users asking "what did X say about Y?" get unreliable results.

## Solution

Replace the pre-fetched semantic recall with two on-demand agent tools and a background job that maintains rolling per-user summaries.

### Components

1. **`search_history` tool** — semantic search over individual messages, optionally filtered by username
2. **`get_user_summary` tool** — retrieve a rolling LLM-generated summary for a user in the current channel
3. **Summary generation job** — daily scheduled task that incrementally updates per-user-per-channel summaries

The 20-message recent window remains as passive context.

## Data Model

### New table: `chat.user_channel_summaries`

| Column            | Type                 | Notes                                      |
| ----------------- | -------------------- | ------------------------------------------ |
| `id`              | SERIAL PK            |                                            |
| `channel_id`      | TEXT NOT NULL        |                                            |
| `user_id`         | TEXT NOT NULL        |                                            |
| `username`        | TEXT NOT NULL        | Display name for prompt readability        |
| `summary`         | TEXT NOT NULL        | LLM-generated rolling summary              |
| `last_message_id` | INT NOT NULL         | FK to `chat.messages.id` — high-water mark |
| `updated_at`      | TIMESTAMPTZ NOT NULL |                                            |

**Unique constraint:** `(channel_id, user_id)`

## Agent Tools

### `search_history(query: str, username: str | None, limit: int = 5)`

- Embeds the query via Voyage 4 Nano
- Calls `MessageStore.search_similar()` scoped to current channel
- Optional `username` filter (matched on `Message.username`)
- Returns formatted messages with timestamps

### `get_user_summary(username: str)`

- Looks up the rolling summary for the given username in the current channel
- Returns summary text or "No summary available for this user"

Both tools receive `channel_id` via PydanticAI dependency injection — not exposed to the LLM.

## Dependency Injection

```python
@dataclass
class ChatDeps:
    channel_id: str
    store: MessageStore
    embed_client: EmbeddingClient
```

Tools use `ctx.deps` to access the store and channel scope.

## Rolling Summary Job

**Trigger:** Daily scheduled task (FastAPI lifespan background coroutine with `asyncio.sleep` interval).

**Algorithm per (channel_id, user_id) with new messages:**

1. Fetch messages where `id > last_message_id` for this channel+user
2. If no new messages, skip
3. Build prompt:
   - First run: "Summarize this user's messages: {messages}"
   - Update: "Current summary: {summary}\n\nNew messages: {messages}\n\nUpdate the summary. Keep it to 2-4 sentences."
4. Call Gemma 4 via llama.cpp
5. Upsert summary row with new `last_message_id`

## Changes to `_generate_response`

**Before:** recent (20) + semantic pre-fetch (5) → static context → `agent.run()`

**After:** recent (20) → static context → `agent.run()` with `search_history` + `get_user_summary` tools

## System Prompt Update

Add: "You have tools to search conversation history and retrieve user activity summaries. Use `search_history` when you need to find specific messages or context beyond the recent window. Use `get_user_summary` when asked about what a user has been discussing. Always try these tools before saying you don't have context."

## Files Changed

- `chat/models.py` — add `UserChannelSummary` model
- `chat/store.py` — add `get_user_summary()`, `upsert_summary()` methods
- `chat/agent.py` — add `ChatDeps`, register tools, update system prompt
- `chat/bot.py` — pass `ChatDeps` to agent, remove pre-fetch
- `chat/summarizer.py` — new: rolling summary generation logic
- `chart/migrations/` — new migration for `user_channel_summaries` table
- `app/main.py` — register summary job in lifespan
