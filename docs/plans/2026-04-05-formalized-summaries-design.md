# Formalized Summaries Design

**Date:** 2026-04-05
**Relates to:** [ADR 002 - Discord Chat Automation](../decisions/services/002-discord-chat-automation.md) Phase 1

## Goal

Improve the Discord bot's contextual awareness by auto-injecting summaries into every agent invocation, adding channel-level summaries, and making summary prompts rolling-window-aware.

## Scope

Three changes from ADR 002 Phase 1:

- **A) Auto-inject summaries into agent context** — prepend channel + user summaries to the prompt in `_generate_response()` so the bot always knows who it's talking to and what the channel is about.
- **B) Channel-level summaries** — new `channel_summaries` table and generation function. Summarizes the entire channel, not just per-user.
- **C) Rolling-window awareness** — update summary prompts to account for the 20-message recent window the bot already sees, focusing on older context.

**Out of scope (YAGNI):** configurable summary schedule (D), configurable prompt templates (E).

## Approach: Inject at prompt-build time

Summaries are fetched and prepended to the user prompt in `_generate_response()`, before the agent sees anything. No changes to agent construction, `ChatDeps`, or system prompt.

### Schema

New table via Atlas migration:

```sql
CREATE TABLE chat.channel_summaries (
    id              SERIAL PRIMARY KEY,
    channel_id      TEXT NOT NULL UNIQUE,
    summary         TEXT NOT NULL,
    message_count   INT NOT NULL DEFAULT 0,
    last_message_id INT NOT NULL REFERENCES chat.messages(id),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

New SQLModel `ChannelSummary` in `models.py`. No changes to existing tables.

### Summarizer

`summarizer.py` gains `generate_channel_summaries()` — same pattern as existing user summaries:

- Query distinct channel_ids from messages
- For each channel, fetch messages since high-water mark
- LLM summarizes into channel-level overview
- Upsert into `channel_summaries`

Both user and channel summary prompts updated with rolling-window guidance:

> "The bot already sees the most recent 20 messages as direct context. Focus your summary on patterns, topics, and context from OLDER messages that would help the bot understand better."

Called from the same 24h lifespan loop, sequentially after `generate_summaries()`.

### Store

New methods on `MessageStore`:

- `get_channel_summary(channel_id) -> ChannelSummary | None`
- `get_user_summaries_for_users(channel_id, user_ids) -> list[UserChannelSummary]`
- `upsert_channel_summary(channel_id, summary, last_message_id, message_count)`

No caching — at <2 responses/minute, sub-millisecond indexed queries are fine.

### Context injection

In `_generate_response()`, after fetching recent messages:

1. `store.get_channel_summary(channel_id)`
2. Collect unique non-bot user_ids from recent 20 messages
3. `store.get_user_summaries_for_users(channel_id, user_ids)` (batched IN clause)
4. Build context header, prepend to existing context
5. Graceful skip if no summaries exist yet

Prompt structure:

```
[Channel context: This channel discusses homelab infrastructure...]

[People in this conversation:
 - jomcgi: Runs the homelab, focuses on GitOps...
 - alex: Interested in container networking...]

Recent conversation:
[2026-04-05 14:30] jomcgi: hey, what were we saying about...
...

Current message from jomcgi: can you check if it's synced now?
```

### Testing

- Summarizer tests: channel summary generation, high-water mark, rolling-window prompt text
- Store tests: new methods (get, upsert, batch user summaries, graceful None)
- Bot tests: context header injection when summaries exist, graceful skip when absent

### Files changed

| Change                     | Files                                          |
| -------------------------- | ---------------------------------------------- |
| New migration + model      | `chart/migrations/`, `chat/models.py`          |
| Channel summary generation | `chat/summarizer.py`                           |
| Store methods              | `chat/store.py`                                |
| Context injection          | `chat/bot.py`                                  |
| Tests                      | `chat/*_test.py`                               |
| Chart version bump         | `chart/Chart.yaml` + `deploy/application.yaml` |

No new dependencies, no new tools, no schema changes to existing tables.
