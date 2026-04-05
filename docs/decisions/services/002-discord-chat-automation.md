# ADR 002: Discord Chat Automation & Reactivity

**Author:** jomcgi
**Status:** Draft
**Created:** 2026-04-05
**Relates to:** [001 - Discord History Backfill](001-discord-history-backfill.md)

---

## Problem

The Discord bot (`projects/monolith/chat/`) is purely reactive today — it only responds when @-mentioned or replied to. It stores messages with vector embeddings and can recall context, but it has no ability to:

- **Schedule actions** — "remind me to check the deploy at 3pm", "post a daily standup summary every morning"
- **React to events** — auto-respond to certain keywords, greet new members, trigger workflows when a message matches a pattern
- **Run proactive tasks** — periodic channel digests, sentiment monitoring, automated follow-ups
- **Chain multi-step workflows** — "when someone posts in #incidents, summarize it and cross-post to #status"

NanoClaw and OpenClaw — two open-source AI agent frameworks with Discord integrations — solve these problems with scheduling, trigger systems, and per-group memory. Rather than adopting either framework wholesale (they bring their own runtimes, LLM routing, and container orchestration that would conflict with our stack), we can steal the best patterns and build them on top of what we already have: PydanticAI + pgvector + PostgreSQL.

---

## What NanoClaw / OpenClaw Offer

### NanoClaw (lightweight, ~3,900 LOC)

| Feature | How It Works |
|---|---|
| **Task Scheduler** | SQLite table of scheduled jobs (cron, interval, one-shot). Polling loop picks up due tasks and executes them in ephemeral Docker containers. |
| **Per-Group Memory** | Each Discord channel gets its own `CLAUDE.md` file on disk — persistent context the agent can read/write between invocations. |
| **Trigger System** | Message prefix matching (`@Andy`) + channel allowlists. Non-admin channels require explicit mention; admin channels respond to everything. |
| **Agent Swarms** | Multiple specialized agents collaborate via filesystem IPC with authorization validation. |
| **Concurrency Control** | Per-group semaphore (default 3 concurrent containers) prevents resource exhaustion. |

### OpenClaw (full-featured, larger ecosystem)

| Feature | How It Works |
|---|---|
| **Skill Injection** | 5,400+ skills discovered at runtime based on context. Only relevant skills loaded to save tokens. |
| **Cron Scheduling** | Built-in cron + push notifications. Tasks run without user prompts. |
| **Reactive + Proactive** | Default reactive mode; becomes proactive with scheduled tasks that post to channels unprompted. |
| **Multi-Platform** | Single bot process handles Discord, Slack, Telegram, etc. via platform adapters. |
| **Capability Tokens** | Skills receive scoped access tokens rather than full system access. |

### What We Should Steal

| Pattern | Source | Why |
|---|---|---|
| **Scheduled tasks in a DB table** | NanoClaw | We already have PostgreSQL — no need for SQLite. A `chat.scheduled_tasks` table with a polling loop is simple and observable. |
| **Event triggers / pattern matching** | Both | NanoClaw's prefix matching is too basic; OpenClaw's skill injection is too heavy. A lightweight trigger table with regex patterns and action types hits the sweet spot. |
| **Per-channel persistent memory** | NanoClaw | We already have `user_channel_summaries`. Extending this to channel-level "memory notes" the bot can read/write gives it persistent context without filesystem state. |
| **Proactive channel posting** | OpenClaw | The bot should be able to post without being mentioned — daily digests, scheduled reminders, event-driven alerts. |
| **Concurrency control** | NanoClaw | Per-channel semaphore to prevent the bot from flooding a channel or exhausting LLM capacity. |

### What We Should NOT Steal

| Pattern | Why Not |
|---|---|
| **Container-per-invocation** | We run in Kubernetes with a single monolith pod. Ephemeral containers per message would be over-engineered and conflict with our deployment model. |
| **Custom LLM routing** | We already have PydanticAI + llama.cpp with tool calling. No need for another LLM abstraction layer. |
| **Filesystem IPC** | We have PostgreSQL. Agent communication via DB tables is more observable and survives pod restarts. |
| **Skill marketplace / plugin system** | Over-engineering for a homelab. We add capabilities as PydanticAI tools in Python — no plugin discovery needed. |
| **Multi-platform adapters** | We only need Discord. Adding Slack/Telegram adapters would be YAGNI. |

---

## Proposal

Add three new tables to the `chat` schema and a lightweight scheduler loop to the monolith's lifespan. The bot gains scheduling, triggers, and proactive posting while keeping the existing vector-backed conversational memory intact.

### New Schema: `chat.scheduled_tasks`

Tasks saved by users (via Discord commands or the bot itself) and polled by a background loop.

```sql
CREATE TABLE chat.scheduled_tasks (
    id              SERIAL PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    created_by      TEXT NOT NULL,          -- discord user ID
    task_type       TEXT NOT NULL,          -- 'reminder' | 'digest' | 'custom'
    description     TEXT NOT NULL,          -- human-readable description
    action_prompt   TEXT NOT NULL,          -- prompt to run through the agent
    schedule_cron   TEXT,                   -- cron expression (NULL for one-shot)
    next_run_at     TIMESTAMPTZ NOT NULL,
    last_run_at     TIMESTAMPTZ,
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- prevent duplicate firings across pod restarts
    run_lock        TIMESTAMPTZ             -- NULL = unlocked, set = claimed
);

CREATE INDEX idx_scheduled_tasks_next_run
    ON chat.scheduled_tasks (next_run_at)
    WHERE enabled = TRUE AND run_lock IS NULL;
```

### New Schema: `chat.triggers`

Pattern-matched reactions to messages (regex on content, user filters, channel filters).

```sql
CREATE TABLE chat.triggers (
    id              SERIAL PRIMARY KEY,
    channel_id      TEXT,                   -- NULL = all channels
    name            TEXT NOT NULL UNIQUE,
    pattern         TEXT NOT NULL,          -- regex matched against message content
    user_filter     TEXT,                   -- optional: only trigger for this user ID
    action_type     TEXT NOT NULL,          -- 'respond' | 'crosspost' | 'agent_run'
    action_config   JSONB NOT NULL,         -- action-specific config
    cooldown_secs   INT DEFAULT 0,          -- minimum seconds between firings
    last_fired_at   TIMESTAMPTZ,
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### New Schema: `chat.channel_memory`

Persistent per-channel notes the bot can read and write (inspired by NanoClaw's per-group `CLAUDE.md`).

```sql
CREATE TABLE chat.channel_memory (
    id              SERIAL PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    key             TEXT NOT NULL,           -- e.g. 'channel_rules', 'ongoing_topics'
    value           TEXT NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE (channel_id, key)
);
```

### Scheduler Loop

A new background task in the monolith lifespan, similar to the existing summary loop:

```python
async def scheduler_loop(interval: int = 30):
    """Poll chat.scheduled_tasks every `interval` seconds and execute due tasks."""
    while True:
        try:
            with Session(get_engine()) as session:
                now = datetime.now(timezone.utc)
                # Atomically claim due tasks (prevents double-fire on pod restart)
                due = session.exec(
                    select(ScheduledTask)
                    .where(
                        ScheduledTask.enabled == True,
                        ScheduledTask.next_run_at <= now,
                        ScheduledTask.run_lock == None,
                    )
                    .with_for_update(skip_locked=True)
                ).all()
                
                for task in due:
                    task.run_lock = now
                    session.add(task)
                session.commit()
                
                for task in due:
                    await execute_task(task)
                    
        except Exception:
            logger.exception("Scheduler loop error")
        await asyncio.sleep(interval)
```

### Trigger Evaluation

Added to the existing `on_message` handler in `bot.py`:

```python
async def evaluate_triggers(self, message: discord.Message):
    """Check message against active triggers and fire matching ones."""
    with Session(get_engine()) as session:
        triggers = get_active_triggers(session, str(message.channel.id))
        for trigger in triggers:
            if re.search(trigger.pattern, message.content, re.IGNORECASE):
                if trigger.cooldown_secs and trigger.last_fired_at:
                    elapsed = (datetime.now(timezone.utc) - trigger.last_fired_at).total_seconds()
                    if elapsed < trigger.cooldown_secs:
                        continue
                await fire_trigger(trigger, message)
                trigger.last_fired_at = datetime.now(timezone.utc)
                session.add(trigger)
        session.commit()
```

### New Agent Tools

The bot gains three new PydanticAI tools so users can create automations conversationally:

| Tool | Description |
|---|---|
| `schedule_task` | "Remind me to check deploys every morning at 9am" → creates a row in `scheduled_tasks` with a cron expression |
| `manage_triggers` | "When someone posts in #incidents, summarize and crosspost to #status" → creates a trigger row |
| `channel_notes` | Read/write persistent channel memory — "remember that we decided to use gRPC for this service" |

### Architecture Diagram

```
Discord Gateway
     │
     ▼
  on_message()
     │
     ├──► store message + embedding  (existing)
     ├──► evaluate_triggers()        (new - pattern matching)
     └──► should_respond()?
              │
              ▼
         PydanticAI Agent
         ├── web_search          (existing)
         ├── search_history      (existing)
         ├── get_user_summary    (existing)
         ├── schedule_task       (new)
         ├── manage_triggers     (new)
         └── channel_notes       (new)

  ┌──────────────────────┐
  │  scheduler_loop()    │  (new - 30s poll interval)
  │  polls scheduled_    │
  │  tasks table         │──► execute_task() ──► post to Discord channel
  └──────────────────────┘
```

---

## Implementation Phases

### Phase 1: Scheduled Tasks (reminders & digests)

- Add `chat.scheduled_tasks` table via Atlas migration
- Add `ScheduledTask` SQLModel
- Add `scheduler_loop()` to monolith lifespan
- Add `schedule_task` PydanticAI tool
- Support one-shot reminders and cron-based recurring tasks
- Add `croniter` dependency for cron expression parsing

### Phase 2: Event Triggers

- Add `chat.triggers` table via Atlas migration
- Add `evaluate_triggers()` to `on_message` handler
- Add `manage_triggers` PydanticAI tool
- Support: respond, crosspost, agent_run action types
- Cooldown enforcement to prevent spam

### Phase 3: Channel Memory & Proactive Posting

- Add `chat.channel_memory` table
- Add `channel_notes` PydanticAI tool
- Add daily digest task type (LLM summarizes last 24h of messages)
- Enable bot to post to channels proactively (not just in reply)

---

## Consequences

**Positive:**
- Users can set up automations conversationally — no config files or deployments needed
- All state lives in PostgreSQL — observable, survives restarts, backed up with CNPG
- The existing vector memory + semantic search is preserved and enhanced
- Trigger evaluation is lightweight (regex match on a small table, not a full LLM call)
- Scheduled tasks use `SELECT ... FOR UPDATE SKIP LOCKED` for safe concurrency

**Negative:**
- 30-second polling means tasks fire up to 30s late (acceptable for a homelab)
- Regex triggers can be footguns (overly broad patterns → spam). Cooldowns and per-channel scoping mitigate this
- More LLM load from proactive tasks. Bounded by: one concurrent task per channel, configurable rate limits
- Schema migrations required for each phase

**Tradeoffs vs. adopting NanoClaw/OpenClaw directly:**

| | Adopt Framework | Build on Existing |
|---|---|---|
| **Time to first feature** | Faster (pre-built) | Slower (custom code) |
| **Operational complexity** | Higher (new runtime, SQLite, Docker-in-Docker) | Lower (same monolith, same Postgres) |
| **LLM integration** | Must replace or bridge PydanticAI | Native PydanticAI tools |
| **Observability** | Separate system to monitor | Same SigNoz traces, same CNPG metrics |
| **Maintenance** | Upstream dependency risk | Full control |
| **Vector memory** | Would need to replicate or bridge | Already there |

---

## Open Questions

1. **Cron parsing library** — `croniter` is the de facto Python choice. Any concerns with adding it as a dependency?
2. **Task execution timeout** — should scheduled tasks have a hard timeout? NanoClaw uses container lifetime; we'd need an `asyncio.wait_for` wrapper.
3. **Trigger creation permissions** — should any Discord user be able to create triggers, or should it be restricted to specific roles?
4. **Digest format** — should daily digests be a simple summary or include links to specific messages?
5. **Channel memory size limits** — should we cap the size of channel memory notes to prevent unbounded growth?

---

## References

- [NanoClaw](https://github.com/qwibitai/nanoclaw) — lightweight personal AI agent with Discord integration and task scheduling
- [OpenClaw](https://openclaw.ai/) — full-featured AI assistant with 5,400+ skills and multi-platform support
- [NanoClaw vs OpenClaw architecture comparison](https://ibl.ai/blog/openclaw-ironclaw-nanoclaw-securing-autonomous-ai-agents)
- Existing chat implementation: `projects/monolith/chat/`
- Existing summary scheduler: `projects/monolith/chat/summarizer.py`
