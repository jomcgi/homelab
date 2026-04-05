# Thinking Mode Handling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix Gemma 4's thinking mode leak in the Discord bot — set proper max_tokens, parse and strip `<think>` blocks, retry on thinking-only responses, summarize long thinking, and add a "Show thinking" button.

**Architecture:** Post-processing approach in `bot.py`. Parse `<think>` tags from raw model output, strip them from the user-visible reply, and attach a discord.py `View` with an ephemeral button. Summarize long thinking via a direct llama.cpp HTTP call (same pattern as `vision.py`).

**Tech Stack:** PydanticAI (ModelSettings), discord.py (View, Button, Interaction), httpx (summarization call), regex (thinking parser)

---

### Task 1: Add max_tokens to agent

**Files:**

- Modify: `projects/monolith/chat/agent.py:85-100`

**Step 1: Write the failing test**

Create `projects/monolith/chat/agent_max_tokens_test.py`:

```python
"""Test that the chat agent is created with max_tokens=16384."""

from unittest.mock import patch

from chat.agent import create_agent


class TestAgentMaxTokens:
    def test_agent_has_max_tokens_setting(self):
        """create_agent() configures ModelSettings with max_tokens=16384."""
        with patch("chat.agent.LLAMA_CPP_URL", "http://fake:8080"):
            agent = create_agent(base_url="http://fake:8080")
        settings = agent.model_settings
        assert settings is not None
        assert settings.get("max_tokens") == 16384
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/agent_max_tokens_test.py -v`
Expected: FAIL — `model_settings` is None or missing `max_tokens`

**Step 3: Write minimal implementation**

In `projects/monolith/chat/agent.py`, add the import and model_settings to the Agent constructor:

```python
# Add to imports (line 8):
from pydantic_ai import Agent, ModelSettings, RunContext

# Update Agent constructor (line 96-100):
    agent: Agent[ChatDeps] = Agent(
        model,
        system_prompt=build_system_prompt(),
        model_settings=ModelSettings(max_tokens=16384),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/agent_max_tokens_test.py -v`
Expected: PASS

**Step 5: Run existing agent tests to check for regressions**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/agent_test.py projects/monolith/chat/agent_coverage_test.py projects/monolith/chat/agent_deps_test.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_max_tokens_test.py
git commit -m "feat(chat): set max_tokens=16384 on PydanticAI agent

Gemma 4 was exhausting the default output budget during <think> blocks,
never producing an actual response."
```

---

### Task 2: Implement thinking parser

**Files:**

- Modify: `projects/monolith/chat/bot.py` (add `_parse_thinking` function)
- Create: `projects/monolith/chat/bot_thinking_test.py`

**Step 1: Write the failing tests**

Create `projects/monolith/chat/bot_thinking_test.py`:

```python
"""Tests for thinking mode handling in the Discord bot."""

import pytest

from chat.bot import _parse_thinking


class TestParseThinking:
    def test_no_thinking_tags(self):
        """Plain text without <think> tags passes through unchanged."""
        response, thinking = _parse_thinking("Hello world!")
        assert response == "Hello world!"
        assert thinking is None

    def test_thinking_and_response(self):
        """Extracts thinking and returns clean response."""
        text = "<think>I should greet them.</think>Hello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking == "I should greet them."

    def test_thinking_with_whitespace(self):
        """Strips whitespace between thinking block and response."""
        text = "<think>reasoning</think>\n\nHello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking == "reasoning"

    def test_thinking_only_empty_response(self):
        """Returns empty response when model only produces thinking."""
        text = "<think>I'm just thinking here.</think>"
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "I'm just thinking here."

    def test_thinking_only_whitespace_response(self):
        """Whitespace-only response after thinking is treated as empty."""
        text = "<think>reasoning</think>   \n  "
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "reasoning"

    def test_multiple_think_blocks(self):
        """Multiple <think> blocks are concatenated."""
        text = "<think>first</think>middle<think>second</think>end"
        response, thinking = _parse_thinking(text)
        assert response == "middleend"
        assert thinking == "first\n\nsecond"

    def test_unclosed_think_tag(self):
        """Unclosed <think> tag — treat entire remainder as thinking."""
        text = "<think>no closing tag here"
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "no closing tag here"

    def test_empty_think_block(self):
        """Empty <think></think> produces no thinking text."""
        text = "<think></think>Hello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py -v`
Expected: FAIL — `_parse_thinking` does not exist

**Step 3: Write minimal implementation**

Add to `projects/monolith/chat/bot.py`, after the imports and before `should_respond`:

```python
import re

def _parse_thinking(text: str) -> tuple[str, str | None]:
    """Extract <think>...</think> blocks from model output.

    Returns (response_text, thinking_text). thinking_text is None if no
    thinking was found or if all think blocks were empty.
    """
    thinking_parts: list[str] = []

    def _collect(match: re.Match) -> str:
        content = match.group(1).strip()
        if content:
            thinking_parts.append(content)
        return ""

    # Handle closed <think>...</think> blocks
    cleaned = re.sub(r"<think>(.*?)</think>", _collect, text, flags=re.DOTALL)

    # Handle unclosed <think> tag (model cut off mid-thought)
    unclosed = re.search(r"<think>(.*)", cleaned, flags=re.DOTALL)
    if unclosed:
        content = unclosed.group(1).strip()
        if content:
            thinking_parts.append(content)
        cleaned = cleaned[: unclosed.start()]

    response = cleaned.strip()
    thinking = "\n\n".join(thinking_parts) if thinking_parts else None
    return response, thinking
```

**Step 4: Run tests to verify they pass**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_thinking_test.py
git commit -m "feat(chat): add _parse_thinking to extract <think> blocks from model output"
```

---

### Task 3: Implement thinking summarization

**Files:**

- Modify: `projects/monolith/chat/bot.py` (add `_summarize_thinking` function)
- Modify: `projects/monolith/chat/bot_thinking_test.py` (add summarization tests)

**Step 1: Write the failing tests**

Append to `projects/monolith/chat/bot_thinking_test.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from chat.bot import _summarize_thinking, LLAMA_CPP_URL


class TestSummarizeThinking:
    @pytest.mark.asyncio
    async def test_short_thinking_returned_as_is(self):
        """Thinking under 2000 chars is not summarized."""
        result = await _summarize_thinking("short reasoning", base_url="http://fake:8080")
        assert result == "short reasoning"

    @pytest.mark.asyncio
    async def test_long_thinking_calls_llm(self):
        """Thinking over 2000 chars triggers an LLM summarization call."""
        long_text = "x" * 2001
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "summarized"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_text, base_url="http://fake:8080")

        assert result == "summarized"
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_llm_failure_truncates(self):
        """If summarization LLM call fails, truncate to 1990 chars."""
        long_text = "x" * 2500

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_text, base_url="http://fake:8080")

        assert len(result) <= 2000
        assert result.endswith("... (truncated)")
```

**Step 2: Run tests to verify they fail**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py::TestSummarizeThinking -v`
Expected: FAIL — `_summarize_thinking` does not exist

**Step 3: Write minimal implementation**

Add to `projects/monolith/chat/bot.py`, after `_parse_thinking`:

```python
import httpx as httpx_lib

DISCORD_MESSAGE_LIMIT = 2000
THINKING_TRUNCATE_AT = 1990

async def _summarize_thinking(
    thinking: str,
    base_url: str | None = None,
) -> str:
    """Summarize thinking text if it exceeds Discord's message limit.

    Short thinking (<2000 chars) is returned as-is. Long thinking is
    summarized via a direct llama.cpp call. On failure, truncates.
    """
    if len(thinking) <= DISCORD_MESSAGE_LIMIT:
        return thinking

    url = base_url or LLAMA_CPP_URL
    try:
        async with httpx_lib.AsyncClient(timeout=httpx_lib.Timeout(30.0)) as client:
            resp = await client.post(
                f"{url}/v1/chat/completions",
                json={
                    "model": "gemma-4-26b-a4b",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Summarize this reasoning concisely. "
                                "Keep the key points but make it much shorter:\n\n"
                                f"{thinking}"
                            ),
                        }
                    ],
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            summary = resp.json()["choices"][0]["message"]["content"]
            # Safety check: if summary is still too long, truncate
            if len(summary) > DISCORD_MESSAGE_LIMIT:
                return summary[:THINKING_TRUNCATE_AT] + "... (truncated)"
            return summary
    except Exception:
        logger.warning("Failed to summarize thinking, truncating")
        return thinking[:THINKING_TRUNCATE_AT] + "... (truncated)"
```

Note: import `httpx` as `httpx_lib` to avoid shadowing the existing `httpx` usage if any, or just use `httpx` directly since it's not imported at module level in `bot.py` currently. Check the existing imports — `bot.py` does not currently import `httpx`, so `import httpx` is fine. Use `import httpx` directly.

**Step 4: Run tests to verify they pass**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py::TestSummarizeThinking -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_thinking_test.py
git commit -m "feat(chat): add _summarize_thinking for long thinking blocks

Calls llama.cpp directly to summarize thinking >2000 chars (Discord limit).
Falls back to truncation on failure."
```

---

### Task 4: Implement ThinkingView (Discord button)

**Files:**

- Modify: `projects/monolith/chat/bot.py` (add `ThinkingView` class)
- Modify: `projects/monolith/chat/bot_thinking_test.py` (add view tests)

**Step 1: Write the failing tests**

Append to `projects/monolith/chat/bot_thinking_test.py`:

```python
import discord

from chat.bot import ThinkingView


class TestThinkingView:
    def test_view_has_button(self):
        """ThinkingView contains a 'Show thinking' button."""
        view = ThinkingView("some thinking")
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == "Show thinking"
        assert buttons[0].style == discord.ButtonStyle.secondary

    def test_view_no_timeout(self):
        """ThinkingView has no timeout."""
        view = ThinkingView("some thinking")
        assert view.timeout is None

    @pytest.mark.asyncio
    async def test_button_sends_ephemeral(self):
        """Clicking the button sends thinking as an ephemeral message."""
        view = ThinkingView("my reasoning")
        button = [c for c in view.children if isinstance(c, discord.ui.Button)][0]

        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_called_once_with(
            "my reasoning", ephemeral=True
        )
```

**Step 2: Run tests to verify they fail**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py::TestThinkingView -v`
Expected: FAIL — `ThinkingView` does not exist

**Step 3: Write minimal implementation**

Add to `projects/monolith/chat/bot.py`, after `_summarize_thinking`:

```python
class ThinkingView(discord.ui.View):
    """Discord View with a 'Show thinking' button that reveals model reasoning."""

    def __init__(self, thinking_text: str):
        super().__init__(timeout=None)
        self.thinking_text = thinking_text

    @discord.ui.button(label="Show thinking", style=discord.ButtonStyle.secondary)
    async def show_thinking(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(self.thinking_text, ephemeral=True)
```

**Step 4: Run tests to verify they pass**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py::TestThinkingView -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_thinking_test.py
git commit -m "feat(chat): add ThinkingView with ephemeral 'Show thinking' button"
```

---

### Task 5: Wire thinking handling into on_message and \_generate_response

**Files:**

- Modify: `projects/monolith/chat/bot.py` (update `_generate_response` and `on_message`)
- Modify: `projects/monolith/chat/bot_thinking_test.py` (add integration tests)

**Step 1: Write the failing tests**

Append to `projects/monolith/chat/bot_thinking_test.py`:

```python
from chat.bot import ChatBot


# Helpers (same pattern as bot_coverage_test.py)

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
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


class TestThinkingIntegration:
    @pytest.mark.asyncio
    async def test_response_with_thinking_adds_view(self):
        """When model returns <think>...</think>, reply includes ThinkingView."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.output = "<think>reasoning here</think>Hello!"
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot._summarize_thinking", new_callable=AsyncMock, return_value="reasoning here"),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # reply should have been called with response text and a ThinkingView
        call_kwargs = message.reply.call_args
        assert call_kwargs[0][0] == "Hello!"
        assert isinstance(call_kwargs[1].get("view"), ThinkingView)

    @pytest.mark.asyncio
    async def test_response_without_thinking_no_view(self):
        """When model returns plain text, reply has no view."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.output = "Hello!"
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        message.reply.assert_called_once_with("Hello!")

    @pytest.mark.asyncio
    async def test_thinking_only_triggers_retry(self):
        """When model produces only thinking, bot retries with a nudge."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        # First call: thinking only. Second call: proper response.
        thinking_only = MagicMock()
        thinking_only.output = "<think>just reasoning</think>"
        proper_response = MagicMock()
        proper_response.output = "Here's my answer!"
        bot.agent.run = AsyncMock(side_effect=[thinking_only, proper_response])

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Should have called agent.run twice
        assert bot.agent.run.call_count == 2
        # Second call should include the nudge
        second_prompt = bot.agent.run.call_args_list[1][0][0]
        assert "no visible response" in second_prompt.lower() or "respond to the user" in second_prompt.lower()
        # Reply should be the proper response
        message.reply.assert_called_once_with("Here's my answer!")
```

**Step 2: Run tests to verify they fail**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py::TestThinkingIntegration -v`
Expected: FAIL — `on_message` doesn't parse thinking yet

**Step 3: Update `_generate_response` to return thinking separately**

Change `_generate_response` signature and `on_message` in `projects/monolith/chat/bot.py`:

Update `_generate_response` to return `tuple[str, str | None]` (response, thinking):

```python
    async def _generate_response(
        self,
        message: discord.Message,
        current_attachments: list[dict] | None = None,
    ) -> tuple[str, str | None]:
        """Build context and run the PydanticAI agent.

        Returns (response_text, thinking_text). thinking_text is None when
        the model produced no <think> blocks.
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

            context = "Recent conversation:\n" + format_context_messages(
                recent, attachments_by_msg
            )

            user_prompt = (
                f"{context}\n\nCurrent message from "
                f"{message.author.display_name}: {message.content}"
            )

            if current_attachments:
                image_context = "\n".join(
                    f"[Attached image '{a['filename']}': {a['description']}]"
                    for a in current_attachments
                )
                user_prompt += f"\n{image_context}"

            last_exc: Exception | None = None
            for attempt in range(LLM_MAX_RETRIES):
                try:
                    result = await self.agent.run(user_prompt, deps=deps)
                    response, thinking = _parse_thinking(result.output)

                    # Retry once if model produced thinking but no response
                    if not response:
                        nudge = (
                            f"{user_prompt}\n\n"
                            "You produced reasoning but no visible response. "
                            "Please respond to the user directly."
                        )
                        result = await self.agent.run(nudge, deps=deps)
                        response, thinking = _parse_thinking(result.output)
                        if not response:
                            response = (
                                "Sorry, I'm having trouble formulating a response. "
                                "Please try again."
                            )

                    # Summarize long thinking
                    if thinking:
                        thinking = await _summarize_thinking(thinking)

                    return response, thinking
                except Exception as exc:
                    last_exc = exc
                    if attempt < LLM_MAX_RETRIES - 1:
                        delay = LLM_RETRY_BASE_DELAY * (2**attempt)
                        logger.warning(
                            "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1,
                            LLM_MAX_RETRIES,
                            delay,
                            exc,
                        )
                        await asyncio.sleep(delay)
            raise last_exc
```

Update `on_message` to handle the new return type:

```python
        try:
            async with message.channel.typing():
                response_text, thinking = await self._generate_response(
                    message, attachments
                )
            if thinking:
                sent = await message.reply(
                    response_text, view=ThinkingView(thinking)
                )
            else:
                sent = await message.reply(response_text)
        except Exception:
            # ... existing error handling unchanged ...
```

Also update the bot response storage to only store `response_text` (not thinking):

```python
        # Store bot response — the stored content is the user-visible text only
        try:
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                await store.save_message(
                    discord_message_id=str(sent.id),
                    channel_id=str(message.channel.id),
                    user_id=str(self.user.id),
                    username=self.user.display_name,
                    content=response_text,
                    is_bot=True,
                )
        except Exception:
            logger.exception("Failed to store bot response for message %s", message.id)
```

**Step 4: Run all thinking tests**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py -v`
Expected: All PASS

**Step 5: Run existing bot tests to check for regressions**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_test.py projects/monolith/chat/bot_coverage_test.py projects/monolith/chat/bot_extra_test.py projects/monolith/chat/bot_exception_test.py projects/monolith/chat/bot_error_handling_test.py projects/monolith/chat/bot_backoff_test.py projects/monolith/chat/bot_attachments_test.py projects/monolith/chat/bot_self_message_test.py projects/monolith/chat/bot_session_failure_test.py -v`

Expected: Some tests will need updating because `_generate_response` now returns a tuple instead of a string. Fix any that fail — the main change is that tests which mock `_generate_response` or check `message.reply` calls need to account for the new signature.

Key tests likely needing updates:

- `bot_coverage_test.py::TestOnMessageGenerateReply::test_replies_when_mentioned` — `mock_agent_result.output` now goes through `_parse_thinking`, and `message.reply` is called with just the text (no view) for plain responses. This should still pass as-is.
- Tests that directly call `_generate_response` and check its return value — now returns a tuple.

**Step 6: Commit**

```bash
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_thinking_test.py
git commit -m "feat(chat): wire thinking parsing into on_message and _generate_response

- Parse <think> blocks from model output
- Retry with nudge on thinking-only responses
- Summarize long thinking before attaching to button
- Attach ThinkingView when thinking is present"
```

---

### Task 6: Add BUILD target for new test file and run format

**Files:**

- Modify: `projects/monolith/BUILD` (add `py_test` for `bot_thinking_test`)

**Step 1: Add BUILD target**

Add to `projects/monolith/BUILD` (after the existing `chat_bot_session_failure_test` target):

```starlark
py_test(
    name = "chat_bot_thinking_test",
    srcs = ["chat/bot_thinking_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

Also add a target for `agent_max_tokens_test.py`:

```starlark
py_test(
    name = "chat_agent_max_tokens_test",
    srcs = ["chat/agent_max_tokens_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
    ],
)
```

**Step 2: Run format**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && format`

This will auto-format code and regenerate BUILD files via gazelle.

**Step 3: Run all tests locally**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_thinking_test.py projects/monolith/chat/agent_max_tokens_test.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add projects/monolith/BUILD projects/monolith/chat/agent_max_tokens_test.py projects/monolith/chat/bot_thinking_test.py
git commit -m "build: add BUILD targets for thinking mode tests"
```

---

### Task 7: Fix regressions in existing bot tests

**Files:**

- Modify: Various `projects/monolith/chat/bot_*_test.py` files as needed

**Step 1: Run all existing bot tests**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/chat/bot_test.py projects/monolith/chat/bot_coverage_test.py projects/monolith/chat/bot_extra_test.py projects/monolith/chat/bot_exception_test.py projects/monolith/chat/bot_error_handling_test.py projects/monolith/chat/bot_backoff_test.py projects/monolith/chat/bot_attachments_test.py projects/monolith/chat/bot_self_message_test.py projects/monolith/chat/bot_session_failure_test.py -v`

**Step 2: Fix any failures**

The main regression will be tests that check `message.reply` was called with a plain string — since `_generate_response` now returns `(response, thinking)` and `on_message` unpacks it. Tests where `mock_agent_result.output` is a plain string (no `<think>` tags) should still work since `_parse_thinking` passes plain text through. Tests that directly call `_generate_response` and assert `result == "Sunny!"` need updating to `result == ("Sunny!", None)`.

**Step 3: Run all bot tests again**

Run: same command as Step 1
Expected: All PASS

**Step 4: Commit**

```bash
git add -u projects/monolith/chat/
git commit -m "fix(chat): update existing bot tests for thinking mode return type"
```

---

### Task 8: Final validation and push

**Step 1: Run ALL monolith tests**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && python -m pytest projects/monolith/ -v`
Expected: All PASS

**Step 2: Run format one more time**

Run: `cd /tmp/claude-worktrees/thinking-mode-handling && format`

**Step 3: Push and create PR**

```bash
cd /tmp/claude-worktrees/thinking-mode-handling
git push -u origin feat/thinking-mode-handling
gh pr create --title "feat(chat): handle Gemma 4 thinking mode in Discord bot" --body "$(cat <<'EOF'
## Summary
- Set `max_tokens=16384` on PydanticAI agent — root cause fix for thinking-only responses
- Parse and strip `<think>` blocks from model output
- Retry with nudge when model produces thinking but no response
- Summarize long thinking (>2000 chars) via llama.cpp
- Add "Show thinking" button (ephemeral message) for transparency

## Test plan
- [ ] Unit tests for `_parse_thinking` (various edge cases)
- [ ] Unit tests for `_summarize_thinking` (short pass-through, long summarize, failure truncate)
- [ ] Unit tests for `ThinkingView` (button exists, ephemeral callback)
- [ ] Integration tests (thinking+response, no thinking, thinking-only retry)
- [ ] Existing bot tests pass (regression check)
- [ ] CI passes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
