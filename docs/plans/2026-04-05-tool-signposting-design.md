# Tool Signposting for Chat Agent

**Status:** Approved
**Date:** 2026-04-05

## Problem

The Gemma 4 26B chat bot doesn't reliably use `web_search` when users make factual claims. It either guesses or hallucinates having searched. The system prompt mentions tools passively — not enough for a smaller model to know _when_ to reach for them.

## Solution

Add a `signposted` decorator that attaches "when to use" guidance to each tool function. This guidance is automatically injected into both the system prompt and the tool schema description at runtime.

### Approach: `signposted` decorator + dynamic system prompt + `prepare_tools`

**Single source of truth:** The signpost lives on the function, right next to its docstring. Adding a tool without a signpost is immediately obvious.

**Dual injection:** The signpost appears in the system prompt (behavioral guidance) and in the tool schema description (tool-call-time reminder). Belt and suspenders for a 26B model.

## Components

### 1. `signposted` decorator

Attaches a `.signpost` string attribute to the tool function. Stacked under `@agent.tool` / `@agent.tool_plain`.

### 2. Dynamic `@agent.system_prompt`

Iterates `agent._function_toolset.tools`, reads `.signpost` from each tool's function, and generates a "Your tools and WHEN to use them" section. Replaces the hand-written tool list in `build_system_prompt()`.

### 3. `prepare_tools` callback

Appends the signpost to each tool's schema description via `dataclasses.replace()`. Passed to the Agent constructor.

### 4. Static prompt changes

- Remove hand-written tool list from `build_system_prompt()`
- Add DON'T rule: "Pretend you looked something up when you didn't"

## Signpost text

- **web_search:** "When someone claims something happened, mentions news, quotes someone, or asks about anything you aren't certain of — search first, respond after. Never guess whether something is real without checking."
- **search_history:** "When someone references a past conversation, asks what was said earlier, or you need context about something discussed before."
- **get_user_summary:** "When someone asks about a person, or you want context on who you're talking to and what they've been up to."

## Testing

- `test_signposted_decorator_attaches_attribute` — decorator works
- `test_tool_guidance_prompt_includes_signposts` — dynamic prompt generates correct output
- `test_all_tools_have_signposts` — no tool registered without a signpost
- Update existing `test_includes_web_search_guidance`
