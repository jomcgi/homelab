# Streaming Discord Responses Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stream LLM responses to Discord by progressively editing a message as thinking, tool calls, and response text arrive.

**Architecture:** Replace batch `agent.run()` with `agent.run_stream_events()`. A new `_stream_response()` method in `bot.py` sends a Discord message on the first event and edits it through phases (thinking → tool calls → response text). The `_summarize_thinking()` function is removed in favor of simple truncation.

**Tech Stack:** PydanticAI streaming events API, discord.py message editing, asyncio

---

### Task 1: Replace `_summarize_thinking` with truncation

**Files:**

- Modify: `projects/monolith/chat/bot.py:51-86`
- Modify: `projects/monolith/chat/bot_thinking_test.py:96-142`

**Step 1: Update tests — replace `TestSummarizeThinking` with `TestTruncateThinking`**

In `projects/monolith/chat/bot_thinking_test.py`, replace the `TestSummarizeThinking` class (lines 96-142) with:

```python
class TestTruncateThinking:
    def test_short_thinking_returned_as_is(self):
        """Thinking under 2000 chars is not truncated."""
        assert _truncate_thinking("short reasoning") == "short reasoning"

    def test_long_thinking_truncated(self):
        """Thinking over 2000 chars is truncated with suffix."""
        long_text = "x" * 2500
        result = _truncate_thinking(long_text)
        assert len(result) <= 2000
        assert result.endswith("... (truncated)")

    def test_exactly_2000_chars_not_truncated(self):
        """Thinking at exactly 2000 chars passes through."""
        text = "x" * 2000
        assert _truncate_thinking(text) == text
```

Update imports at line 10 to import `_truncate_thinking` instead of `_summarize_thinking`:

```python
from chat.bot import _extract_thinking, _truncate_thinking, ThinkingView, ChatBot
```

**Step 2: Run tests to verify they fail**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/chat:bot_thinking_test --config=ci`
Expected: FAIL — `_truncate_thinking` does not exist yet

**Step 3: Implement `_truncate_thinking` and remove `_summarize_thinking`**

In `projects/monolith/chat/bot.py`, replace the `_summarize_thinking` function (lines 51-86) with:

```python
def _truncate_thinking(thinking: str) -> str:
    """Truncate thinking text if it exceeds Discord's message limit."""
    if len(thinking) <= DISCORD_MESSAGE_LIMIT:
        return thinking
    return thinking[:THINKING_TRUNCATE_AT] + "... (truncated)"
```

Remove the `import httpx` line (line 9) since it was only used by `_summarize_thinking`.

Remove the `LLAMA_CPP_URL` line (line 27) — it was only used by `_summarize_thinking`. The agent gets its URL from `create_agent()`.

**Step 4: Update call site in `_generate_response`**

In `bot.py` line 458-459, change:

```python
                    if thinking:
                        thinking = await _summarize_thinking(thinking)
```

to:

```python
                    if thinking:
                        thinking = _truncate_thinking(thinking)
```

**Step 5: Run tests to verify they pass**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/chat:bot_thinking_test --config=ci`
Expected: PASS

**Step 6: Commit**

```bash
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_thinking_test.py
git commit -m "refactor(chat): replace thinking summarization with truncation"
```

---

### Task 2: Add `_stream_response` method with streaming event loop

This is the core change. The new method handles the full lifecycle: send initial message, edit through phases, return final state.

**Files:**

- Modify: `projects/monolith/chat/bot.py`
- Create: `projects/monolith/chat/bot_streaming_test.py`

**Step 1: Write tests for `_stream_response` phases**

Create `projects/monolith/chat/bot_streaming_test.py`:

```python
"""Tests for streaming Discord response behavior."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from chat.bot import ChatBot, ThinkingView

# -- Helpers (same pattern as bot_thinking_test.py) --


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_bot() -> ChatBot:
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
        patch("chat.bot.create_agent") as mock_ca,
    ):
        mock_ec.return_value = AsyncMock()
        mock_ca.return_value = MagicMock()
        bot = ChatBot()
    bot._connection = MagicMock()
    bot._connection.user = MagicMock()
    bot._connection.user.id = 999
    bot._connection.user.display_name = "BotUser"
    return bot


def _make_message(content="hello", mentions=None, msg_id=1):
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = 99
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = None
    msg.attachments = []
    msg.embeds = []
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


def _make_mock_store():
    mock_store = AsyncMock()
    mock_store.save_message = AsyncMock()
    mock_store.acquire_lock = MagicMock(return_value=True)
    mock_store.mark_completed = MagicMock()
    mock_store.get_recent = MagicMock(return_value=[])
    mock_store.get_attachments = MagicMock(return_value={})
    mock_store.get_channel_summary = MagicMock(return_value=None)
    mock_store.get_user_summaries_for_users = MagicMock(return_value=[])
    return mock_store


# -- Fake streaming events --
# These simulate what PydanticAI's run_stream_events() yields.


def _fake_thinking_event(content: str):
    """Simulate a PartDeltaEvent with ThinkingPartDelta."""
    event = MagicMock()
    event.__class__.__name__ = "PartDeltaEvent"
    type(event).delta = property(lambda self: MagicMock(
        __class__=type("ThinkingPartDelta", (), {}),
        content_delta=content,
    ))
    return event


def _fake_text_event(content: str):
    """Simulate a PartDeltaEvent with TextPartDelta."""
    event = MagicMock()
    event.__class__.__name__ = "PartDeltaEvent"
    type(event).delta = property(lambda self: MagicMock(
        __class__=type("TextPartDelta", (), {}),
        content_delta=content,
    ))
    return event


def _fake_tool_call_event(tool_name: str, args: dict):
    """Simulate a FunctionToolCallEvent."""
    event = MagicMock()
    event.__class__.__name__ = "FunctionToolCallEvent"
    event.part = MagicMock()
    event.part.tool_name = tool_name
    event.part.args = args
    return event


def _fake_final_event(output: str):
    """Simulate a FinalResultEvent."""
    event = MagicMock()
    event.__class__.__name__ = "FinalResultEvent"
    event.result = MagicMock()
    event.result.output = output
    return event


class TestStreamResponsePhases:
    @pytest.mark.asyncio
    async def test_text_only_response_sends_and_edits(self):
        """A simple text response sends initial message then edits with final content."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_mock_store()

        # Simulate: text chunks arrive
        async def fake_events(*args, **kwargs):
            yield _fake_text_event("Hello ")
            yield _fake_text_event("world!")

        bot.agent.run_stream_events = fake_events

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Should have sent a reply
        message.reply.assert_called_once()
        # Final edit should contain full text
        sent_msg = message.reply.return_value
        last_edit = sent_msg.edit.call_args_list[-1]
        assert "Hello world!" in last_edit.kwargs.get("content", last_edit.args[0] if last_edit.args else "")

    @pytest.mark.asyncio
    async def test_tool_call_shows_searching_indicator(self):
        """When a tool call event arrives, the message shows a searching indicator."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="what is the weather", mentions=[bot_user])
        mock_store = _make_mock_store()

        async def fake_events(*args, **kwargs):
            yield _fake_tool_call_event("web_search", {"query": "weather today"})
            yield _fake_text_event("It's sunny!")

        bot.agent.run_stream_events = fake_events

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        sent_msg = message.reply.return_value
        # At least one edit should have contained "Searching"
        all_edit_contents = [
            c.kwargs.get("content", c.args[0] if c.args else "")
            for c in sent_msg.edit.call_args_list
        ]
        assert any("Searching" in c for c in all_edit_contents)

    @pytest.mark.asyncio
    async def test_thinking_collected_for_button(self):
        """Thinking events are collected and attached as ThinkingView on final edit."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_mock_store()

        async def fake_events(*args, **kwargs):
            yield _fake_thinking_event("Let me think...")
            yield _fake_thinking_event(" about this.")
            yield _fake_text_event("Here's my answer.")

        bot.agent.run_stream_events = fake_events

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        sent_msg = message.reply.return_value
        # Final edit should include a ThinkingView
        last_edit = sent_msg.edit.call_args_list[-1]
        view = last_edit.kwargs.get("view")
        assert isinstance(view, ThinkingView)
```

**Step 2: Run tests to verify they fail**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/chat:bot_streaming_test --config=ci`
Expected: FAIL — `run_stream_events` not wired up yet

**Step 3: Implement `_stream_response` method**

In `projects/monolith/chat/bot.py`, add new imports at the top:

```python
from pydantic_ai import (
    FunctionToolCallEvent,
    PartDeltaEvent,
    TextPartDelta,
    ThinkingPartDelta,
)
```

Add `STREAM_EDIT_INTERVAL = 1.0` constant near the other constants (line ~30).

Add the `_stream_response` method to `ChatBot` class. This replaces `_generate_response` and the send logic in `_process_message`. The method:

1. Builds the prompt (same context-building logic from `_generate_response`)
2. Sends an initial reply message on first event
3. Edits through phases: thinking indicator → tool call bullets → response text
4. Returns `(sent_message, response_text, thinking_text)`

```python
    async def _stream_response(
        self,
        message: discord.Message,
        current_attachments: list[dict] | None = None,
    ) -> tuple[discord.Message, str, str | None]:
        """Stream a response to Discord, editing the message as events arrive.

        Returns (sent_message, response_text, thinking_text).
        """
        from chat.agent import ChatDeps

        with Session(get_engine()) as session:
            store = MessageStore(session=session, embed_client=self.embed_client)
            recent = store.get_recent(str(message.channel.id), limit=20)
            deps = ChatDeps(
                channel_id=str(message.channel.id),
                store=store,
                embed_client=self.embed_client,
            )
            all_msg_ids = [m.id for m in recent if m.id is not None]
            attachments_by_msg = store.get_attachments(all_msg_ids)
            channel_summary = store.get_channel_summary(str(message.channel.id))
            recent_user_ids = list({m.user_id for m in recent if not m.is_bot})
            user_summaries = store.get_user_summaries_for_users(
                str(message.channel.id), recent_user_ids
            )

            summary_header = ""
            if channel_summary:
                summary_header += f"[Channel context: {channel_summary.summary}]\n\n"
            if user_summaries:
                summary_header += "[People in this conversation:\n"
                for s in user_summaries:
                    summary_header += f" - {s.username}: {s.summary}\n"
                summary_header += "]\n\n"

            context = (
                summary_header
                + "Recent conversation:\n"
                + format_context_messages(recent, attachments_by_msg)
            )
            user_prompt = (
                f"{context}\n\nCurrent message from "
                f"{message.author.display_name}: {message.content}"
            )

            image_parts: list[BinaryContent] = []
            if current_attachments:
                image_context = "\n".join(
                    f"[Attached image '{a['filename']}': {a['description']}]"
                    for a in current_attachments
                )
                user_prompt += f"\n{image_context}"
                for a in current_attachments:
                    if a["data"] is not None:
                        image_parts.append(
                            BinaryContent(data=a["data"], media_type=a["content_type"])
                        )

            if current_attachments:
                descriptions = " ".join(
                    a["description"]
                    for a in current_attachments
                    if a["description"] != "(image could not be processed)"
                )
                if descriptions:
                    try:
                        search_results = await search_web(descriptions)
                        user_prompt += (
                            f"\n\n[Auto-search results for attached image]\n"
                            f"{search_results}"
                        )
                    except Exception:
                        logger.warning(
                            "Auto-search for image failed, continuing without"
                        )

            agent_prompt: str | list = user_prompt
            if image_parts:
                agent_prompt = [user_prompt, *image_parts]

            # Stream state
            sent: discord.Message | None = None
            thinking_parts: list[str] = []
            tool_queries: list[str] = []
            response_text = ""
            last_edit_time = 0.0

            async def _ensure_sent(content: str) -> discord.Message:
                nonlocal sent
                if sent is None:
                    sent = await message.reply(content)
                return sent

            async def _edit_if_due(content: str, force: bool = False) -> None:
                nonlocal last_edit_time
                now = asyncio.get_event_loop().time()
                if force or (now - last_edit_time) >= STREAM_EDIT_INTERVAL:
                    if sent is not None:
                        await sent.edit(content=content)
                        last_edit_time = now

            async for event in self.agent.run_stream_events(
                agent_prompt, deps=deps
            ):
                if isinstance(event, PartDeltaEvent):
                    if isinstance(event.delta, ThinkingPartDelta):
                        thinking_parts.append(event.delta.content_delta)
                        await _ensure_sent("\U0001f4ad Thinking...")
                    elif isinstance(event.delta, TextPartDelta):
                        response_text += event.delta.content_delta
                        await _ensure_sent(response_text)
                        await _edit_if_due(response_text)
                elif isinstance(event, FunctionToolCallEvent):
                    tool_name = event.part.tool_name
                    args = event.part.args
                    query = args.get("query", str(args))
                    tool_queries.append(query)
                    indicator = "\U0001f50d Searching...\n" + "\n".join(
                        f"\u2022 {q}" for q in tool_queries
                    )
                    await _ensure_sent(indicator)
                    if sent is not None:
                        await sent.edit(content=indicator)

            # Ensure we have a sent message even if no events arrived
            if sent is None:
                sent = await message.reply(
                    "Sorry, I'm having trouble formulating a response. "
                    "Please try again."
                )
                return sent, sent.content, None

            # Final edit with complete response + optional ThinkingView
            thinking = (
                "".join(thinking_parts).strip() if thinking_parts else None
            )
            if thinking:
                thinking = _truncate_thinking(thinking)

            if not response_text:
                response_text = (
                    "Sorry, I'm having trouble formulating a response. "
                    "Please try again."
                )

            if thinking:
                await sent.edit(
                    content=response_text, view=ThinkingView(thinking)
                )
            else:
                await sent.edit(content=response_text)

            return sent, response_text, thinking
```

**Step 4: Update `_process_message` to use `_stream_response`**

Replace the try/except block in `_process_message` (lines 289-312) that calls `_generate_response`, sends the reply, and handles errors:

```python
        try:
            async with message.channel.typing():
                sent, response_text, thinking = await self._stream_response(
                    message, attachments
                )
        except Exception:
            logger.exception("Failed to respond to message %s", msg_id)
            try:
                await message.reply(
                    "Sorry, I'm having trouble reaching the language model right now. "
                    "Please try again in a moment."
                )
            except Exception:
                logger.exception("Failed to send error reply for message %s", msg_id)
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                store.mark_completed(msg_id)
            return
```

Update the store bot response block (lines 314-328) to use `sent` and `response_text` from the returned tuple instead of the old `sent` variable:

```python
        try:
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                await store.save_message(
                    discord_message_id=str(sent.id),
                    channel_id=channel_id,
                    user_id=str(self.user.id),
                    username=self.user.display_name,
                    content=response_text,
                    is_bot=True,
                    thinking=thinking,
                )
        except Exception:
            logger.exception("Failed to store bot response for message %s", msg_id)
```

**Step 5: Remove `_generate_response` and `_extract_thinking`**

Delete the `_generate_response` method (lines 334-474) and the `_extract_thinking` function (lines 33-48). These are fully replaced by `_stream_response`.

Remove unused imports: `ModelResponse`, `ThinkingPart` from `pydantic_ai.messages` (line 11) — unless still used elsewhere. Check first.

**Step 6: Run all bot tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/chat:bot_streaming_test //projects/monolith/chat:bot_thinking_test --config=ci`
Expected: PASS

**Step 7: Commit**

```bash
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_streaming_test.py
git commit -m "feat(chat): stream LLM responses to Discord with progressive edits"
```

---

### Task 3: Update existing tests that reference removed functions

**Files:**

- Modify: `projects/monolith/chat/bot_thinking_test.py`
- Modify: `projects/monolith/chat/bot_generate_response_gaps_test.py`
- Modify: `projects/monolith/chat/bot_coverage_test.py`

Tests that mock `agent.run`, `_generate_response`, or `_summarize_thinking` need updating to work with the new streaming flow. The key changes:

- Replace `bot.agent.run = AsyncMock(...)` with `bot.agent.run_stream_events = <async generator>`
- Remove patches for `_summarize_thinking`
- Update `ThinkingIntegration` tests to check `sent.edit()` calls instead of `message.reply()` kwargs

**Step 1: Read each test file and identify what needs changing**

Check these files for references to `_generate_response`, `_summarize_thinking`, or `agent.run`:

- `projects/monolith/chat/bot_thinking_test.py` — `TestThinkingIntegration` class
- `projects/monolith/chat/bot_generate_response_gaps_test.py` — entire file
- `projects/monolith/chat/bot_coverage_test.py` — may reference `_generate_response`

**Step 2: Update each test file**

For each test that previously mocked `agent.run`, create an async generator that yields the appropriate fake events to simulate the same behavior.

**Step 3: Run all chat tests**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/chat/... --config=ci`
Expected: PASS

**Step 4: Commit**

```bash
git add projects/monolith/chat/
git commit -m "test(chat): update bot tests for streaming response flow"
```

---

### Task 4: Add BUILD target for new test file

**Files:**

- Modify: `projects/monolith/chat/BUILD`

**Step 1: Run `format` to auto-generate BUILD targets**

The `format` command includes gazelle which auto-generates Python test targets.

Run: `format`

**Step 2: Verify the new test target exists**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/chat:bot_streaming_test --config=ci`
Expected: PASS

**Step 3: Commit if BUILD changed**

```bash
git add projects/monolith/chat/BUILD
git commit -m "build(chat): add bot_streaming_test target"
```

---

### Task 5: Create PR and deploy

**Step 1: Push and create PR**

```bash
git push -u origin feat/streaming-discord-responses
gh pr create --title "feat(chat): stream LLM responses to Discord" --body "..."
gh pr merge --auto --rebase
```

**Step 2: Monitor rollout**

Poll PR merge, then check monolith pod restarts and test Discord interaction.
