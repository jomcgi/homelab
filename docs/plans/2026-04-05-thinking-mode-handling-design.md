# Gemma 4 Thinking Mode Handling

**Date:** 2026-04-05
**Status:** Approved
**Scope:** `projects/monolith/chat/`

## Problem

Gemma 4 produces `<think>...</think>` reasoning blocks before its actual response.
Two issues:

1. **No `max_tokens` configured** — the default output limit is too small, so the model
   exhausts its budget during the thinking phase and the actual response is never generated.
   Users see only the raw thinking text as the bot's reply.
2. **Thinking text leaks into chat** — even with sufficient tokens, the `<think>` block
   appears as part of the visible response.

## Design

### 1. Max tokens (`agent.py`)

Set `max_tokens=16384` via PydanticAI `ModelSettings` on the chat agent. The llama.cpp
context window is 32k; input context (system prompt, 20 recent messages, tool results)
uses ~4-8k, leaving plenty of room for output including thinking.

### 2. Thinking parser (`bot.py`)

`_parse_thinking(text: str) -> tuple[str, str | None]`

- Extracts content between `<think>` and `</think>` tags using regex.
- Returns `(response_text, thinking_text)`.
- Handles: no thinking, thinking + response, thinking-only, multiple think blocks
  (concatenated).

### 3. Thinking-only retry (`bot.py`)

When the parsed response is empty/whitespace after stripping thinking:

- Retry the agent with the original prompt plus a nudge:
  `"You produced reasoning but no visible response. Please respond to the user directly."`
- Parse the retry output the same way.
- If still thinking-only, fall back to a generic error message.

This is a content retry, separate from the existing exponential-backoff error retries.

### 4. Eager thinking summarization (`bot.py`)

When thinking text exceeds 2000 characters (Discord message limit):

- Call llama.cpp directly (raw HTTP, same pattern as `vision.py` / `summarizer.py`)
  with a summarization prompt and `max_tokens=1024`.
- On summarization failure, truncate to 1990 chars + `"... (truncated)"`.

When thinking is under 2000 chars, use as-is.

### 5. "Show thinking" button (`bot.py`)

`ThinkingView(discord.ui.View)`:

- Takes `thinking_text: str` in constructor, stores as instance attribute.
- One `discord.ui.Button` labeled "Show thinking", `ButtonStyle.secondary`.
- Button callback sends `thinking_text` as an **ephemeral** message (only visible to
  the person who clicks).
- `timeout=None` — button stays active for the bot process lifetime.

In `on_message`:

- Thinking present: `await message.reply(response_text, view=ThinkingView(thinking))`
- No thinking: `await message.reply(response_text)`

### 6. Testing

- `_parse_thinking` unit tests: no thinking, thinking + response, thinking-only,
  multiple blocks, malformed tags.
- Thinking-only retry: mock agent returning thinking-only, verify nudge retry,
  verify fallback after second failure.
- `_summarize_thinking`: mock HTTP call, verify prompt and `max_tokens=1024`,
  verify truncation fallback on failure.
- `ThinkingView`: verify button exists, verify ephemeral callback.
- `max_tokens`: verify agent created with `ModelSettings(max_tokens=16384)`.

## Files Changed

| File                                          | Change                                                                                                    |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `projects/monolith/chat/agent.py`             | Add `ModelSettings(max_tokens=16384)`                                                                     |
| `projects/monolith/chat/bot.py`               | `_parse_thinking()`, `_summarize_thinking()`, `ThinkingView`, thinking-only retry, wire into `on_message` |
| `projects/monolith/chat/bot_thinking_test.py` | New test file for all thinking-related tests                                                              |
