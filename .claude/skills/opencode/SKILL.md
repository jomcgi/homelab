---
name: opencode
description: Use to offload token-heavy tasks to cheaper models. Qwen (free local) for directed tasks, Gemini for 1M+ context. Minimizes Claude token usage.
---

# OpenCode - Token-Efficient Task Offloading

## Overview

OpenCode runs AI tasks non-interactively via `opencode run`. Use it to minimize Claude token usage by offloading work to cheaper models.

## Model Priority

**Always prefer this order:**

1. **Qwen via `--agent cheap-local-tokens`** - FREE local model, use liberally
2. **Claude (current session)** - When context/quality matters
3. **Gemini via `--agent long-context-window-tasks`** - Only for 1M+ token context

## Available Agents

| Agent                       | Model           | Context | Cost | Use For                            |
| --------------------------- | --------------- | ------- | ---- | ---------------------------------- |
| `cheap-local-tokens`        | Qwen3 Coder 30B | 24k     | FREE | Directed tasks, code gen, research |
| `long-context-window-tasks` | Gemini 3 Flash  | 1M+     | Paid | Massive context analysis           |

## Qwen3 Coder 30B (Local)

**Cost:** FREE - abuse this liberally
**Context:** 24k tokens
**Agent:** `--agent cheap-local-tokens`

**Use for:**

- Directed, well-scoped tasks
- Research summaries
- Code generation with clear specs
- File transformations
- Documentation generation
- Repetitive refactoring
- Any token-heavy but low-complexity work

```bash
# Basic usage with local Qwen (FREE)
opencode run --agent cheap-local-tokens "summarize the authentication flow in this codebase"

# With file context
opencode run --agent cheap-local-tokens "refactor this function to use async/await" -f src/api.ts

# Multi-file tasks
opencode run --agent cheap-local-tokens "add JSDoc comments to all exported functions" -f "src/**/*.ts"
```

## Gemini 3 Flash (Long Context)

**Cost:** Paid API - use sparingly
**Context:** 1M+ tokens
**Agent:** `--agent long-context-window-tasks`

**Use ONLY for:**

- Tasks requiring 1M+ token context window
- Analyzing entire large codebases at once
- Very long document analysis
- When Qwen's 24k context is insufficient

```bash
# Only when truly needed for massive context
opencode run --agent long-context-window-tasks "analyze the entire codebase architecture and identify coupling issues"
```

## When to Use OpenCode vs Claude

| Task Type                            | Use                                 |
| ------------------------------------ | ----------------------------------- |
| Quick question about current context | Claude (you)                        |
| Research across many files           | `--agent cheap-local-tokens` (FREE) |
| Generate boilerplate code            | `--agent cheap-local-tokens` (FREE) |
| Summarize documents                  | `--agent cheap-local-tokens` (FREE) |
| Complex multi-step reasoning         | Claude (you)                        |
| Tasks needing conversation context   | Claude (you)                        |
| Analyzing 100+ files at once         | `--agent long-context-window-tasks` |

## Command Reference

```bash
# Run with Qwen (FREE, recommended for most tasks)
opencode run --agent cheap-local-tokens "<prompt>"

# Run with Gemini (only for 1M+ context)
opencode run --agent long-context-window-tasks "<prompt>"

# Include files
opencode run --agent cheap-local-tokens "<prompt>" -f <file-or-glob>

# Multiple file patterns
opencode run --agent cheap-local-tokens "<prompt>" -f "src/**/*.ts" -f "tests/**/*.ts"

# Continue previous session
opencode run -c "<follow-up prompt>"
```

## Cost-Saving Patterns

### Research Tasks

Instead of reading many files yourself:

```bash
# Let Qwen do the heavy lifting (FREE)
opencode run --agent cheap-local-tokens "find all usages of the AuthService class and explain how authentication flows through the system" -f "src/**/*.ts"
```

### Code Generation

Instead of generating repetitive code:

```bash
# Generate boilerplate with Qwen (FREE)
opencode run --agent cheap-local-tokens "create unit tests for all exported functions" -f src/utils.ts
```

### Documentation

Instead of writing docs manually:

```bash
# Let Qwen document the codebase (FREE)
opencode run --agent cheap-local-tokens "generate API documentation for all HTTP endpoints" -f "src/routes/**/*.ts"
```

## Anti-Patterns

**DON'T use Gemini for:**

- Tasks Qwen can handle (wastes money)
- Small file sets under 24k tokens
- Quick lookups (use Qwen)

**DON'T use OpenCode for:**

- Tasks requiring current conversation context
- Interactive debugging sessions
- Tasks where you need to iterate quickly with Claude

## Integration with Claude Workflow

1. **Identify token-heavy task** (research, generation, summarization)
2. **Offload to Qwen** via `opencode run --agent cheap-local-tokens`
3. **Review output** and incorporate into your response
4. **Use Claude** for synthesis, judgment, and complex reasoning

This maximizes value: Qwen handles volume (FREE), Claude handles quality.
