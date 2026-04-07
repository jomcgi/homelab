# Postgres-Backed Scheduler for Monolith

## Problem

The monolith runs 4 background loops as standalone `asyncio.create_task()` calls:
midnight reset (daily/weekly), calendar poll (5min), summary generation (24h),
and changelog posting (hourly). These are all in-memory with no coordination,
meaning:

- Two replicas would both fire every job (no leader election)
- If a pod crashes mid-job, the work is lost until the next cycle
- No visibility into when jobs last ran or whether they succeeded
- Each loop is wired up independently in `main.py` lifespan with bespoke logic

## Decision

Replace the in-memory loops with a shared Postgres-backed scheduler library
(`shared/scheduler.py`) that services register into via startup hooks. The
message lock sweep stays in-memory (30s, bot-coupled, already multi-pod safe
via `SKIP LOCKED`).

## Design

### Table: `shared.scheduled_jobs`

```sql
CREATE SCHEMA IF NOT EXISTS shared;

CREATE TABLE shared.scheduled_jobs (
    name           TEXT PRIMARY KEY,
    interval_secs  INTEGER NOT NULL,
    next_run_at    TIMESTAMPTZ NOT NULL,
    last_run_at    TIMESTAMPTZ,
    last_status    TEXT,
    locked_by      TEXT,
    locked_at      TIMESTAMPTZ,
    ttl_secs       INTEGER NOT NULL DEFAULT 300
);
```

- `name` as PK — jobs are singletons identified by a stable string
- `interval_secs` — default interval; handlers can override `next_run_at`
- `ttl_secs` — max lock hold time before another pod can reclaim
- No cron syntax — handlers compute timezone-aware schedules themselves

### Library API: `shared/scheduler.py`

**Handler contract:**

```python
async def handler(session: Session) -> datetime | None:
    """Receives an open Session. Return datetime to override next_run_at, or None."""
```

Handlers that need extra dependencies (bot, LLM caller) close over them —
the scheduler only sees the uniform `(Session) -> datetime | None` signature.

**Registration:**

```python
from shared.scheduler import register_job

register_job(
    name="home.daily_reset",
    interval_secs=86400,
    handler=daily_reset_handler,
    ttl_secs=600,
)
```

`register_job()` stores the handler in an in-memory registry and upserts the
job row (`INSERT ... ON CONFLICT (name) DO UPDATE SET interval_secs, ttl_secs`).
Code is the source of truth for schedule config; `next_run_at` and `last_run_at`
are preserved across deploys.

**Scheduler loop:**

```python
async def run_scheduler_loop(poll_interval: int = 30) -> None:
```

Polls every 30 seconds. Each tick:

1. `SELECT ... WHERE next_run_at <= NOW() AND (unlocked OR stale lock) ORDER BY next_run_at LIMIT 1 FOR UPDATE SKIP LOCKED`
2. Set `locked_by` to pod hostname, `locked_at` to now
3. Call the registered handler
4. On success: clear lock, set `last_status = 'ok'`, advance `next_run_at`
5. On failure: clear lock, set `last_status` to error message, still advance `next_run_at` to avoid blocking

### Service startup hooks

Each service exports an `on_startup()` function called from `main.py` lifespan.
Registration happens only at startup, never at import time.

```python
# home/service.py
async def on_startup():
    register_job(name="home.daily_reset", ...)

# shared/service.py
async def on_startup():
    register_job(name="shared.calendar_poll", ...)

# chat/summarizer.py
def on_startup(bot, llm_call):
    async def _summary_handler(session):
        await generate_all_summaries(session, llm_call)

    async def _changelog_handler(session):
        await run_changelog(session, bot, llm_call)

    register_job(name="chat.summary_generation", ...)
    register_job(name="chat.changelog", ...)
```

### Integration in `main.py`

```python
# Before: 5 separate asyncio loops
scheduler_task = asyncio.create_task(run_scheduler())
calendar_task = asyncio.create_task(calendar_loop())
summary_task = asyncio.create_task(_summary_loop())
changelog_task = asyncio.create_task(changelog_loop(...))
sweep_task = asyncio.create_task(_lock_sweep_loop())

# After: startup hooks + 2 tasks
await home_startup()
await shared_startup()
await chat_startup(bot=bot, llm_call=build_llm_caller())
scheduler_task = asyncio.create_task(run_scheduler_loop())
sweep_task = asyncio.create_task(_lock_sweep_loop())  # stays in-memory
```

### Jobs

| Job | Interval | TTL | Notes |
|-----|----------|-----|-------|
| `home.daily_reset` | 86400s | 600s | Returns next midnight Vancouver |
| `shared.calendar_poll` | 900s (15min) | 120s | Idempotent fetch |
| `chat.summary_generation` | 86400s | 1800s | LLM calls, slow |
| `chat.changelog` | 3600s | 300s | Hourly, needs bot via closure |

### Migration

Single file: `chart/migrations/20260407000000_scheduled_jobs.sql`

### Future extensions

- `job_runs` audit table for execution history
- Retry with backoff (currently jobs just advance to next interval on failure)
- Web UI to view job status (query `scheduled_jobs` table directly for now)
