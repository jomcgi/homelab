# Streaming Discord Responses

## Problem

The Discord bot waits for the full LLM response before sending a message.
With Qwen3.6 thinking mode enabled, this means users see only a typing
indicator for 30s+ before anything appears. Tool calls (web search, history
search) add further latency with no visibility into what the bot is doing.

## Solution

Replace the batch `agent.run()` → `message.reply()` flow with
`agent.run_stream_events()` → progressive `message.edit()`. The bot sends
a Discord message on the first event and edits it as new content arrives.

## Message Phases

The message content evolves through phases:

| Phase      | Trigger                 | Content                                          |
| ---------- | ----------------------- | ------------------------------------------------ |
| Thinking   | `ThinkingPartDelta`     | `Thinking...` (static indicator, text collected) |
| Tool calls | `FunctionToolCallEvent` | `Searching...\n* {query}` (bullets accumulate)   |
| Response   | `TextPartDelta`         | Streamed response text, edited every ~1s         |
| Final      | Stream ends             | Response text + ThinkingView button              |

- Thinking text is collected but not shown inline. It populates the
  existing "Show thinking" button (ephemeral follow-up on click).
- Tool call indicators are replaced by response text once it starts.
- Multiple tool calls accumulate as bullet points.

## Edit Strategy

- Batch edits at ~1s intervals during text streaming (`debounce_by=1.0`).
- Thinking phase: single static message, no repeated edits.
- Tool calls: one edit per tool call (infrequent).
- 2000 char overflow: truncate streamed preview, full text on final edit.

## Thinking Handling

Remove `_summarize_thinking()` (which made a second LLM call to condense
long thinking text). Replace with simple truncation at 1985 chars. The
summarize step added latency after the response was already generated.

## Error Handling

Keep the 3-retry loop. On stream failure mid-way:

1. Delete the partially-streamed message.
2. Retry with a fresh message.
3. After 3 failures, send the existing error message.

The "nudge" retry (model produces thinking but no response text) stays:
detect by checking whether any `TextPartDelta` events were received.

## Files Changed

- `chat/bot.py` — New `_stream_response()` method replaces
  `_generate_response()`. Removes `_summarize_thinking()`. Updates
  `_process_message()` flow since sending is now interleaved with
  generation.

No changes to `agent.py`, `explorer.py`, or `store.py`.

## Approach

Uses PydanticAI's `run_stream_events()` API which emits typed events:

- `PartStartEvent` / `PartDeltaEvent` / `PartEndEvent` for text and thinking
- `FunctionToolCallEvent` for tool invocations
- `FinalResultEvent` for completion with full message history

This gives full visibility into every phase of the agent's execution,
enabling the phased message UX described above.
