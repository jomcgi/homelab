# Tool Signposting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-generate tool usage guidance in the chat agent's system prompt from signpost metadata on each tool function, replacing the hand-written tool list.

**Architecture:** A `signposted` decorator attaches `.signpost` to tool functions. A dynamic `@agent.system_prompt` reads these at runtime to generate the "when to use" section. A `prepare_tools` callback injects signposts into tool schema descriptions too.

**Tech Stack:** PydanticAI (`Agent`, `RunContext`, `ToolDefinition`), `dataclasses.replace`

---

### Task 1: Add `signposted` decorator and apply to tools

**Files:**

- Modify: `projects/monolith/chat/agent.py:1-16` (imports)
- Modify: `projects/monolith/chat/agent.py:48-78` (build_system_prompt)
- Modify: `projects/monolith/chat/agent.py:100-174` (create_agent)

**Step 1: Write the failing test for signpost decorator**

Add to `projects/monolith/chat/agent_tools_test.py`:

```python
class TestSignpostedDecorator:
    def test_attaches_signpost_attribute(self):
        """signposted decorator attaches .signpost to the function."""
        from chat.agent import signposted

        @signposted("test guidance")
        def dummy():
            pass

        assert dummy.signpost == "test guidance"

    def test_preserves_function_name(self):
        """signposted decorator preserves the original function name."""
        from chat.agent import signposted

        @signposted("test")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_agent_tools_test`
Expected: FAIL — `signposted` not importable

**Step 3: Add the `signposted` decorator to `agent.py`**

Add after line 19 (`logger = ...`), before `_coerce_username`:

```python
def signposted(text: str):
    """Attach a usage signpost to a tool function."""

    def decorator(fn):
        fn.signpost = text
        return fn

    return decorator
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/monolith:chat_agent_tools_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_tools_test.py
git commit -m "feat(chat): add signposted decorator for tool usage guidance"
```

---

### Task 2: Apply signposts to all three tools

**Files:**

- Modify: `projects/monolith/chat/agent.py:118-152` (tool definitions)
- Modify: `projects/monolith/chat/agent_tools_test.py`

**Step 1: Write the failing test**

Add to `projects/monolith/chat/agent_tools_test.py`:

```python
class TestAllToolsSignposted:
    def test_all_tools_have_signposts(self):
        """Every registered tool must have a signpost."""
        agent = create_agent(base_url="http://fake:8080")
        for name, tool in agent._function_toolset.tools.items():
            signpost = getattr(tool.function, "signpost", None)
            assert signpost is not None, f"Tool '{name}' is missing a signpost"
            assert len(signpost) > 10, f"Tool '{name}' signpost is too short"
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_agent_tools_test`
Expected: FAIL — tools don't have `.signpost` attribute yet

**Step 3: Apply `@signposted` to each tool in `create_agent()`**

Stack `@signposted(...)` under each `@agent.tool` / `@agent.tool_plain`:

```python
@agent.tool_plain
@signposted(
    "When someone claims something happened, mentions news, quotes someone, "
    "or asks about anything you aren't certain of — search first, respond "
    "after. Never guess whether something is real without checking."
)
async def web_search(query: str) -> str:
    """Search the web for current information."""
    return await search_web(query)

@agent.tool
@signposted(
    "When someone references a past conversation, asks what was said "
    "earlier, or you need context about something discussed before."
)
async def search_history(
    ctx: RunContext[ChatDeps],
    query: str,
    username: Any = None,
    limit: int = 5,
) -> str:
    """Search older messages in this channel by topic. Optionally filter by username."""
    # ... body unchanged

@agent.tool
@signposted(
    "When someone asks about a person, or you want context on who "
    "you're talking to and what they've been up to."
)
async def get_user_summary(
    ctx: RunContext[ChatDeps],
    username: Any = None,
) -> str:
    """Get user activity summaries. Call with no username to list all available users. Call with a username to get their full summary."""
    # ... body unchanged
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/monolith:chat_agent_tools_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_tools_test.py
git commit -m "feat(chat): add signposts to all three chat tools"
```

---

### Task 3: Add dynamic system prompt and remove hand-written tool list

**Files:**

- Modify: `projects/monolith/chat/agent.py:48-78` (build_system_prompt — remove tool list)
- Modify: `projects/monolith/chat/agent.py:100-116` (create_agent — add dynamic prompt)
- Modify: `projects/monolith/chat/agent_test.py`

**Step 1: Write the failing test**

Add to `projects/monolith/chat/agent_test.py`:

```python
from chat.agent import create_agent

class TestToolGuidancePrompt:
    def test_dynamic_prompt_includes_signposted_tools(self):
        """Dynamic system prompt includes USE WHEN guidance for each tool."""
        agent = create_agent(base_url="http://fake:8080")
        # Find the tool_guidance system prompt function
        prompt_fns = agent._system_prompt_functions
        tool_prompt = None
        for fn in prompt_fns:
            result = fn()
            if result and "USE WHEN:" in result:
                tool_prompt = result
                break
        assert tool_prompt is not None, "No dynamic prompt with USE WHEN found"
        assert "web_search" in tool_prompt
        assert "search_history" in tool_prompt
        assert "get_user_summary" in tool_prompt

    def test_static_prompt_no_longer_lists_tools(self):
        """build_system_prompt() no longer contains the hand-written tool list."""
        from chat.agent import build_system_prompt
        prompt = build_system_prompt()
        assert "You have these tools:" not in prompt
```

Note: The `_system_prompt_functions` access may need adjustment — check PydanticAI internals. If dynamic prompts are stored differently, the test should iterate `agent._system_prompts` or similar. The key assertion is that the generated text contains "USE WHEN:" for each tool.

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_agent_test`
Expected: FAIL — static prompt still has tool list, no dynamic prompt exists

**Step 3: Remove hand-written tool list from `build_system_prompt()`**

Change `build_system_prompt()` to end after the DON'T section. Remove lines 72-77:

```python
def build_system_prompt() -> str:
    """Build the system prompt for the chat agent."""
    return (
        "You are a friend hanging out in a Discord server. "
        "You talk like a real person — casual, direct, and natural.\n\n"
        "DO:\n"
        "- Answer directly. If someone asks a question, just answer it.\n"
        "- Match the vibe of the conversation. Be chill, funny, or serious "
        "depending on what people are talking about.\n"
        "- Use your tools proactively when they're relevant.\n"
        "- Keep it concise. One or two sentences is usually enough.\n\n"
        "DON'T:\n"
        "- Narrate or explain what people meant. Never say things like "
        '"contextually, they are referring to..." or '
        '"the user is asking about...".\n'
        "- Write like an essay or a report. No bullet points, no headers, "
        "no structured breakdowns unless someone specifically asks.\n"
        '- Start messages with "Sure!", "Of course!", "Great question!", '
        "or any other filler.\n"
        "- Announce that you're using a tool. Just use it and share "
        "what you found.\n"
        '- Apologize for being an AI or say "as an AI".\n'
        "- Pretend you looked something up when you didn't. If you haven't "
        "used web_search, don't claim to have checked."
    )
```

Note: Also simplified the DO bullet about tools (no longer lists them by name — that's in the dynamic prompt now) and added the "don't pretend" DON'T rule.

**Step 4: Add dynamic `@agent.system_prompt` in `create_agent()`**

After the agent is created (after line 116) and before the tool definitions:

```python
@agent.system_prompt
def tool_guidance() -> str:
    lines = ["Your tools and WHEN to use them:"]
    for name, tool in agent._function_toolset.tools.items():
        fn = tool.function
        sp = getattr(fn, "signpost", None)
        desc = tool.description or ""
        if sp:
            lines.append(f"- {name}: {desc}\n  USE WHEN: {sp}")
        else:
            lines.append(f"- {name}: {desc}")
    return "\n".join(lines)
```

**Step 5: Run test to verify it passes**

Run: `bazel test //projects/monolith:chat_agent_test`
Expected: PASS

**Step 6: Commit**

```bash
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_test.py
git commit -m "feat(chat): auto-generate tool guidance in system prompt from signposts"
```

---

### Task 4: Add `prepare_tools` to inject signposts into tool schema

**Files:**

- Modify: `projects/monolith/chat/agent.py:1-10` (add imports)
- Modify: `projects/monolith/chat/agent.py` (create_agent — add prepare_tools)
- Modify: `projects/monolith/chat/agent_tools_test.py`

**Step 1: Write the failing test**

Add to `projects/monolith/chat/agent_tools_test.py`:

```python
import asyncio
from unittest.mock import MagicMock

class TestToolSchemaSignposts:
    def test_prepare_tools_appends_signpost_to_description(self):
        """prepare_tools callback appends USE WHEN to tool schema descriptions."""
        agent = create_agent(base_url="http://fake:8080")
        # Access the prepare_tools function
        assert agent._prepare_tools is not None

        # Create mock ToolDefinitions matching registered tools
        from pydantic_ai import ToolDefinition

        tool_defs = []
        for name, tool in agent._function_toolset.tools.items():
            tool_defs.append(
                ToolDefinition(name=name, description=tool.description or "")
            )

        # Run the prepare_tools callback
        ctx = MagicMock()
        result = asyncio.get_event_loop().run_until_complete(
            agent._prepare_tools(ctx, tool_defs)
        )

        for td in result:
            assert "USE WHEN:" in td.description, (
                f"Tool '{td.name}' schema missing signpost"
            )
```

Note: The exact way to access `_prepare_tools` and `ToolDefinition` constructor may need adjustment based on PydanticAI internals. The key assertion is that after `prepare_tools` runs, each tool definition's description contains "USE WHEN:".

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_agent_tools_test`
Expected: FAIL — no prepare_tools callback set

**Step 3: Add imports and `prepare_tools` callback**

Add to imports in `agent.py`:

```python
from dataclasses import dataclass, replace
from pydantic_ai import Agent, ModelSettings, RunContext, ToolDefinition
```

Add the callback function inside `create_agent()`, before the Agent constructor:

```python
async def inject_signposts(
    ctx: RunContext[ChatDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    updated = []
    for td in tool_defs:
        tool = agent._function_toolset.tools.get(td.name)
        if tool:
            sp = getattr(tool.function, "signpost", None)
            if sp:
                updated.append(
                    replace(td, description=f"{td.description} USE WHEN: {sp}")
                )
                continue
        updated.append(td)
    return updated
```

Pass to Agent constructor:

```python
agent: Agent[ChatDeps] = Agent(
    model,
    system_prompt=build_system_prompt(),
    model_settings=ModelSettings(max_tokens=16384),
    prepare_tools=inject_signposts,
)
```

Note: There's a chicken-and-egg issue — `inject_signposts` references `agent` which isn't created yet. The callback is defined first and only references `agent` when called (at runtime, not at definition time), so this works because Python closures capture the variable name, not the value. But if PydanticAI evaluates `prepare_tools` eagerly, we may need to define `inject_signposts` after agent creation and set `agent._prepare_tools = inject_signposts` manually. Test will reveal which approach works.

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/monolith:chat_agent_tools_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_tools_test.py
git commit -m "feat(chat): inject signposts into tool schema via prepare_tools"
```

---

### Task 5: Update existing tests and run full suite

**Files:**

- Modify: `projects/monolith/chat/agent_test.py:15-18` (update web search guidance test)

**Step 1: Update existing test**

The `test_includes_web_search_guidance` test currently checks `build_system_prompt()` for "search". Since the tool list is removed from the static prompt, update it:

```python
def test_includes_web_search_guidance(self):
    """System prompt includes proactive tool usage guidance."""
    prompt = build_system_prompt()
    assert "tools" in prompt.lower()
```

**Step 2: Run full test suite**

Run: `bazel test //projects/monolith:chat_agent_test //projects/monolith:chat_agent_tools_test`
Expected: All PASS

**Step 3: Commit**

```bash
git add projects/monolith/chat/agent_test.py
git commit -m "test(chat): update prompt tests for signposted tool guidance"
```

---

### Task 6: Run format and push

**Step 1: Run format**

```bash
cd /tmp/claude-worktrees/tool-signposting && format
```

**Step 2: Commit any format changes**

```bash
git add -A && git commit -m "style: format"
```

**Step 3: Push and create PR**

```bash
git push -u origin feat/tool-signposting
gh pr create --title "feat(chat): auto-generate tool signposting in system prompt" --body "..."
```
