# Postgres-Backed Scheduler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 4 in-memory asyncio background loops with a shared Postgres-backed scheduler that supports multi-pod locking, TTLs, and centralized job visibility.

**Architecture:** A `shared/scheduler.py` library provides `register_job()` and `run_scheduler_loop()`. Each service registers jobs via startup hooks. A single scheduler loop polls the `scheduler.scheduled_jobs` table every 30s, claiming due jobs with `FOR UPDATE SKIP LOCKED`. The message lock sweep stays in-memory.

**Tech Stack:** Python, SQLModel, psycopg3, asyncio, Atlas migrations

**Design doc:** `docs/plans/2026-04-07-pg-backed-scheduler-design.md`

---

### Task 1: Migration — Create `scheduler.scheduled_jobs` Table

**Files:**

- Create: `projects/monolith/chart/migrations/20260407000000_scheduled_jobs.sql`

**Step 1: Write the migration**

```sql
-- Postgres-backed scheduler: job registry with distributed locking.
-- Pods claim due jobs via SELECT FOR UPDATE SKIP LOCKED.

CREATE SCHEMA IF NOT EXISTS scheduler;

CREATE TABLE scheduler.scheduled_jobs (
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

**Step 2: Verify Atlas checksum**

The `atlas.sum` file in `chart/migrations/` needs updating. This happens automatically when the e2e test runs against the migration directory — Atlas recalculates it. For now, just verify the file parses:

Run: `head -5 /tmp/claude-worktrees/pg-scheduler/projects/monolith/chart/migrations/atlas.sum`

**Step 3: Commit**

```bash
git add projects/monolith/chart/migrations/20260407000000_scheduled_jobs.sql
git commit -m "feat(monolith): add scheduler.scheduled_jobs migration"
```

---

### Task 2: Scheduler Library — `ScheduledJob` Model + `register_job()`

**Files:**

- Create: `projects/monolith/shared/scheduler.py`
- Test: `projects/monolith/shared/scheduler_test.py`

**Step 1: Write the failing test for ScheduledJob model**

```python
import pytest
from shared.scheduler import ScheduledJob


def test_scheduled_job_table_name():
    assert ScheduledJob.__tablename__ == "scheduled_jobs"


def test_scheduled_job_schema():
    schema = ScheduledJob.model_config.get("table", None)
    # SQLModel uses __table_args__ for schema
    assert ScheduledJob.__table_args__ == {"schema": "scheduler"}
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:shared_scheduler_test --config=ci`
Expected: FAIL — module not found

**Step 3: Write the ScheduledJob model and register_job()**

```python
"""Postgres-backed job scheduler with distributed locking."""

import logging
import platform
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlmodel import Field, Session, SQLModel, select, text

logger = logging.getLogger(__name__)

_HOSTNAME = platform.node()


class ScheduledJob(SQLModel, table=True):
    __tablename__ = "scheduled_jobs"
    __table_args__ = {"schema": "scheduler"}

    name: str = Field(primary_key=True)
    interval_secs: int
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_status: str | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    ttl_secs: int = Field(default=300)


# Handler signature: receives a Session, returns optional next_run_at override
Handler = Callable[[Session], Awaitable[datetime | None]]

# In-memory handler registry (populated at startup)
_registry: dict[str, Handler] = {}


def register_job(
    session: Session,
    *,
    name: str,
    interval_secs: int,
    handler: Handler,
    ttl_secs: int = 300,
) -> None:
    """Register a job handler and upsert its row in the database."""
    _registry[name] = handler

    now = datetime.now(timezone.utc)
    # Upsert: insert if new, update interval/ttl if changed, preserve timing
    existing = session.get(ScheduledJob, name)
    if existing:
        existing.interval_secs = interval_secs
        existing.ttl_secs = ttl_secs
        session.add(existing)
    else:
        session.add(
            ScheduledJob(
                name=name,
                interval_secs=interval_secs,
                next_run_at=now,
                ttl_secs=ttl_secs,
            )
        )
    session.commit()
    logger.info("Registered job %s (interval=%ds, ttl=%ds)", name, interval_secs, ttl_secs)
```

**Step 4: Write the failing test for register_job()**

Add to `shared/scheduler_test.py`:

```python
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from shared.scheduler import register_job, _registry, ScheduledJob


def test_register_job_adds_to_registry():
    _registry.clear()
    mock_session = MagicMock()
    mock_session.get.return_value = None  # no existing job

    async def my_handler(session):
        return None

    register_job(
        mock_session,
        name="test.job",
        interval_secs=3600,
        handler=my_handler,
        ttl_secs=120,
    )

    assert "test.job" in _registry
    assert _registry["test.job"] is my_handler
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

    added_job = mock_session.add.call_args[0][0]
    assert added_job.name == "test.job"
    assert added_job.interval_secs == 3600
    assert added_job.ttl_secs == 120


def test_register_job_updates_existing():
    _registry.clear()
    mock_session = MagicMock()
    existing = ScheduledJob(
        name="test.job",
        interval_secs=1800,
        next_run_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ttl_secs=60,
    )
    mock_session.get.return_value = existing

    async def my_handler(session):
        return None

    register_job(
        mock_session,
        name="test.job",
        interval_secs=3600,
        handler=my_handler,
        ttl_secs=120,
    )

    assert existing.interval_secs == 3600
    assert existing.ttl_secs == 120
    mock_session.add.assert_called_once_with(existing)
```

**Step 5: Run tests**

Run: `bb remote test //projects/monolith:shared_scheduler_test --config=ci`
Expected: PASS

**Step 6: Add BUILD target**

Add to `projects/monolith/BUILD`:

```starlark
py_test(
    name = "shared_scheduler_test",
    srcs = ["shared/scheduler_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)
```

**Step 7: Commit**

```bash
git add projects/monolith/shared/scheduler.py projects/monolith/shared/scheduler_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add scheduler library with ScheduledJob model and register_job"
```

---

### Task 3: Scheduler Loop — `run_scheduler_loop()`

**Files:**

- Modify: `projects/monolith/shared/scheduler.py`
- Test: `projects/monolith/shared/scheduler_loop_test.py`

**Step 1: Write the failing test for claim-and-run**

```python
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from shared import scheduler
from shared.scheduler import ScheduledJob, _registry


@pytest.mark.asyncio
async def test_scheduler_loop_claims_and_runs_due_job():
    """Scheduler picks up a due job, calls its handler, and advances next_run_at."""
    _registry.clear()

    handler = AsyncMock(return_value=None)
    _registry["test.job"] = handler

    due_job = ScheduledJob(
        name="test.job",
        interval_secs=3600,
        next_run_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        ttl_secs=300,
    )

    mock_session = MagicMock()
    mock_connection = MagicMock()
    # Simulate: first call returns due_job, second returns None (loop exits)
    mock_connection.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=(due_job.name,))),
    ]

    with (
        patch.object(scheduler, "get_engine") as mock_engine,
        patch.object(scheduler, "Session") as MockSession,
        patch.object(scheduler, "asyncio") as mock_asyncio,
    ):
        mock_asyncio.sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])

        mock_sess_instance = MagicMock()
        mock_sess_instance.get.return_value = due_job
        MockSession.return_value.__enter__ = MagicMock(return_value=mock_sess_instance)
        MockSession.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_scheduler_loop(poll_interval=1)

        handler.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:shared_scheduler_loop_test --config=ci`
Expected: FAIL — `run_scheduler_loop` not found

**Step 3: Implement `run_scheduler_loop()`**

Add to `shared/scheduler.py`:

```python
from app.db import get_engine


async def run_scheduler_loop(poll_interval: int = 30) -> None:
    """Poll for due jobs and run them. Runs forever."""
    logger.info("Scheduler loop started (poll every %ds)", poll_interval)
    while True:
        try:
            _tick()
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(poll_interval)


def _tick() -> None:
    """Single scheduler tick: claim one due job and run it."""
    with Session(get_engine()) as session:
        job_name = _claim_next_job(session)
        if job_name is None:
            return

        job = session.get(ScheduledJob, job_name)
        if job is None:
            return

        handler = _registry.get(job_name)
        if handler is None:
            logger.warning("No handler registered for job %s", job_name)
            _release_lock(session, job)
            return

        try:
            import asyncio
            override = asyncio.get_event_loop().run_until_complete(handler(session))
            _complete_job(session, job, override)
        except Exception as exc:
            logger.exception("Job %s failed", job_name)
            _fail_job(session, job, str(exc))
```

Wait — handlers are async but `_tick` is sync. We need an async approach. Let me revise:

```python
import asyncio


async def run_scheduler_loop(poll_interval: int = 30) -> None:
    """Poll for due jobs and run them. Runs forever."""
    logger.info("Scheduler loop started (poll every %ds)", poll_interval)
    while True:
        try:
            await _tick()
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(poll_interval)


async def _tick() -> None:
    """Single scheduler tick: claim one due job and run it."""
    with Session(get_engine()) as session:
        job_name = _claim_next_job(session)
        if job_name is None:
            return

        job = session.get(ScheduledJob, job_name)
        if job is None:
            return

        handler = _registry.get(job_name)
        if handler is None:
            logger.warning("No handler registered for job %s", job_name)
            _release_lock(session, job)
            return

        try:
            override = await handler(session)
            _complete_job(session, job, override)
        except Exception as exc:
            logger.exception("Job %s failed", job_name)
            _fail_job(session, job, str(exc))


def _claim_next_job(session: Session) -> str | None:
    """Claim the next due job using SELECT FOR UPDATE SKIP LOCKED."""
    now = datetime.now(timezone.utc)
    result = session.execute(
        text("""
            UPDATE scheduler.scheduled_jobs
            SET locked_by = :hostname, locked_at = :now
            WHERE name = (
                SELECT name FROM scheduler.scheduled_jobs
                WHERE next_run_at <= :now
                  AND (locked_by IS NULL
                       OR locked_at < :now - make_interval(secs => ttl_secs))
                ORDER BY next_run_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING name
        """),
        {"hostname": _HOSTNAME, "now": now},
    )
    row = result.fetchone()
    session.commit()  # release the advisory lock from FOR UPDATE
    return row[0] if row else None


def _complete_job(session: Session, job: ScheduledJob, override: datetime | None) -> None:
    """Mark a job as succeeded and advance next_run_at."""
    now = datetime.now(timezone.utc)
    job.locked_by = None
    job.locked_at = None
    job.last_run_at = now
    job.last_status = "ok"
    job.next_run_at = override or (now + timedelta(seconds=job.interval_secs))
    session.add(job)
    session.commit()
    logger.info("Job %s completed, next run at %s", job.name, job.next_run_at.isoformat())


def _fail_job(session: Session, job: ScheduledJob, error: str) -> None:
    """Mark a job as failed, still advance next_run_at to avoid blocking."""
    now = datetime.now(timezone.utc)
    job.locked_by = None
    job.locked_at = None
    job.last_run_at = now
    job.last_status = f"error: {error[:200]}"
    job.next_run_at = now + timedelta(seconds=job.interval_secs)
    session.add(job)
    session.commit()


def _release_lock(session: Session, job: ScheduledJob) -> None:
    """Release a lock without advancing the schedule (for missing handler)."""
    job.locked_by = None
    job.locked_at = None
    session.add(job)
    session.commit()
```

**Step 4: Run tests**

Run: `bb remote test //projects/monolith:shared_scheduler_loop_test --config=ci`
Expected: PASS

**Step 5: Add BUILD target**

```starlark
py_test(
    name = "shared_scheduler_loop_test",
    srcs = ["shared/scheduler_loop_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)
```

**Step 6: Commit**

```bash
git add projects/monolith/shared/scheduler.py projects/monolith/shared/scheduler_loop_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add scheduler loop with claim/complete/fail mechanics"
```

---

### Task 4: Home Startup Hook — `home.daily_reset`

**Files:**

- Modify: `projects/monolith/home/service.py` — add `on_startup()` + handler
- Create: `projects/monolith/home/startup_test.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from home.service import daily_reset_handler

TZ = ZoneInfo("America/Vancouver")


@pytest.mark.asyncio
async def test_daily_reset_handler_calls_archive_and_reset():
    mock_session = MagicMock()

    with patch("home.service.archive_and_reset") as mock_reset:
        with patch("home.service.datetime") as mock_dt:
            # Tuesday at midnight
            mock_now = datetime(2026, 4, 7, 0, 0, 1, tzinfo=TZ)
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine

            result = await daily_reset_handler(mock_session)

            mock_reset.assert_called_once_with(mock_session, weekly_reset=False)
            # Should return next midnight Vancouver
            assert result is not None
            assert result.hour == 0
            assert result.minute == 0


@pytest.mark.asyncio
async def test_daily_reset_handler_weekly_on_monday():
    mock_session = MagicMock()

    with patch("home.service.archive_and_reset") as mock_reset:
        with patch("home.service.datetime") as mock_dt:
            # Monday at midnight (weekday 0)
            mock_now = datetime(2026, 4, 6, 0, 0, 1, tzinfo=TZ)
            mock_dt.now.return_value = mock_now
            mock_dt.combine = datetime.combine

            await daily_reset_handler(mock_session)

            mock_reset.assert_called_once_with(mock_session, weekly_reset=True)
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:home_startup_test --config=ci`
Expected: FAIL — `daily_reset_handler` not found

**Step 3: Implement the handler and on_startup()**

Add to `home/service.py`:

```python
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Vancouver")


async def daily_reset_handler(session: Session) -> datetime:
    """Run the daily/weekly reset and return next midnight Vancouver."""
    now = datetime.now(TZ)
    weekly = now.weekday() == 0  # Monday
    archive_and_reset(session, weekly_reset=weekly)

    next_midnight = datetime.combine(
        now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
    )
    return next_midnight


def on_startup(session: Session) -> None:
    """Register home jobs with the scheduler."""
    from shared.scheduler import register_job

    register_job(
        session,
        name="home.daily_reset",
        interval_secs=86400,
        handler=daily_reset_handler,
        ttl_secs=600,
    )
```

**Step 4: Run tests**

Run: `bb remote test //projects/monolith:home_startup_test --config=ci`
Expected: PASS

**Step 5: Add BUILD target**

```starlark
py_test(
    name = "home_startup_test",
    srcs = ["home/startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)
```

**Step 6: Commit**

```bash
git add projects/monolith/home/service.py projects/monolith/home/startup_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add home.daily_reset scheduler handler"
```

---

### Task 5: Shared Startup Hook — `shared.calendar_poll`

**Files:**

- Modify: `projects/monolith/shared/service.py` — add `on_startup()` + handler
- Create: `projects/monolith/shared/startup_test.py`

**Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.service import calendar_poll_handler


@pytest.mark.asyncio
async def test_calendar_poll_handler_calls_poll_calendar():
    mock_session = MagicMock()

    with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
        result = await calendar_poll_handler(mock_session)

        mock_poll.assert_called_once()
        assert result is None  # uses default interval
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:shared_startup_test --config=ci`
Expected: FAIL — `calendar_poll_handler` not found

**Step 3: Implement handler and on_startup()**

Add to `shared/service.py`:

```python
async def calendar_poll_handler(session: Session) -> None:
    """Scheduler handler for calendar polling. Session unused (stateless HTTP fetch)."""
    await poll_calendar()
    return None


def on_startup(session: Session) -> None:
    """Register shared jobs with the scheduler."""
    from shared.scheduler import register_job

    register_job(
        session,
        name="shared.calendar_poll",
        interval_secs=900,  # 15 minutes
        handler=calendar_poll_handler,
        ttl_secs=120,
    )
```

Note: `Session` import is already available via the existing imports — we just need to add it. The `session` parameter is required by the handler contract but unused here since calendar polling is a stateless HTTP fetch.

**Step 4: Run tests**

Run: `bb remote test //projects/monolith:shared_startup_test --config=ci`
Expected: PASS

**Step 5: Add BUILD target**

```starlark
py_test(
    name = "shared_startup_test",
    srcs = ["shared/startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)
```

**Step 6: Commit**

```bash
git add projects/monolith/shared/service.py projects/monolith/shared/startup_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add shared.calendar_poll scheduler handler"
```

---

### Task 6: Chat Startup Hook — `chat.summary_generation` + `chat.changelog`

**Files:**

- Modify: `projects/monolith/chat/summarizer.py` — add `on_startup()`
- Modify: `projects/monolith/chat/changelog.py` — extract `run_changelog_iteration()`
- Create: `projects/monolith/chat/startup_test.py`

**Step 1: Write the failing test for summary handler**

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_summary_handler_calls_generate_functions():
    mock_session = MagicMock()
    mock_llm = AsyncMock(return_value="summary text")

    from chat.summarizer import on_startup

    with (
        patch("chat.summarizer.generate_summaries", new_callable=AsyncMock) as mock_gen,
        patch("chat.summarizer.generate_channel_summaries", new_callable=AsyncMock) as mock_chan,
    ):
        # Call on_startup to register, then get the handler from the registry
        from shared.scheduler import _registry
        _registry.clear()

        on_startup(mock_session, llm_call=mock_llm)

        handler = _registry["chat.summary_generation"]
        await handler(mock_session)

        mock_gen.assert_called_once_with(mock_session, mock_llm)
        mock_chan.assert_called_once_with(mock_session, mock_llm)
```

**Step 2: Write the failing test for changelog handler**

```python
@pytest.mark.asyncio
async def test_changelog_handler_calls_run_changelog_iteration():
    mock_session = MagicMock()
    mock_bot = MagicMock()
    mock_llm = AsyncMock(return_value="changelog text")

    from chat.summarizer import on_startup
    from shared.scheduler import _registry
    _registry.clear()

    on_startup(mock_session, bot=mock_bot, llm_call=mock_llm)

    handler = _registry["chat.changelog"]

    with patch("chat.changelog.run_changelog_iteration", new_callable=AsyncMock) as mock_iter:
        await handler(mock_session)
        mock_iter.assert_called_once_with(mock_bot, mock_llm)
```

**Step 3: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:chat_startup_test --config=ci`
Expected: FAIL

**Step 4: Extract `run_changelog_iteration()` from `changelog.py`**

Refactor `changelog_loop()` in `chat/changelog.py` — extract the inner try block into `run_changelog_iteration()`:

```python
async def run_changelog_iteration(
    bot: discord.Client,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Single iteration: fetch recent commits, summarize, post to Discord."""
    channel_id = os.environ.get("CHANGELOG_CHANNEL_ID", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_repo = os.environ.get("CHANGELOG_GITHUB_REPO", "")

    if not all([channel_id, github_token, github_repo]):
        logger.warning("Changelog disabled: missing env vars")
        return

    since = datetime.now(timezone.utc) - timedelta(hours=1)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        commits = await _fetch_commits_since(client, github_repo, github_token, since)

        if not commits:
            logger.info("Changelog: no new commits in the last hour")
            return

        changelog_commits = _filter_changelog_commits(commits)
        ci_status = await _fetch_ci_status(client, github_repo, github_token)

    if not changelog_commits:
        logger.info("Changelog: %d new commits but none are feat/fix", len(commits))
        return

    summary = await _summarize_with_gemma(changelog_commits, llm_call)
    embed = _build_embed(summary, ci_status, len(changelog_commits))

    channel = bot.get_channel(int(channel_id))
    if channel:
        await channel.send(embed=embed)
        logger.info("Changelog: posted %d changes to channel %s", len(changelog_commits), channel_id)
    else:
        logger.warning("Changelog: channel %s not found", channel_id)
```

Keep the old `changelog_loop()` calling `run_changelog_iteration()` for backwards compat during the transition (removed in Task 8).

**Step 5: Add `on_startup()` to `chat/summarizer.py`**

```python
def on_startup(
    session: Session,
    *,
    bot: "discord.Client | None" = None,
    llm_call: Callable[[str], Awaitable[str]] | None = None,
) -> None:
    """Register chat jobs with the scheduler."""
    from shared.scheduler import register_job

    if llm_call is None:
        llm_call = build_llm_caller()

    async def _summary_handler(session: Session) -> None:
        await generate_summaries(session, llm_call)
        await generate_channel_summaries(session, llm_call)
        return None

    register_job(
        session,
        name="chat.summary_generation",
        interval_secs=86400,
        handler=_summary_handler,
        ttl_secs=1800,
    )

    if bot is not None:
        from chat.changelog import run_changelog_iteration

        async def _changelog_handler(session: Session) -> None:
            await run_changelog_iteration(bot, llm_call)
            return None

        register_job(
            session,
            name="chat.changelog",
            interval_secs=3600,
            handler=_changelog_handler,
            ttl_secs=300,
        )
```

**Step 6: Run tests**

Run: `bb remote test //projects/monolith:chat_startup_test --config=ci`
Expected: PASS

**Step 7: Add BUILD target**

```starlark
py_test(
    name = "chat_startup_test",
    srcs = ["chat/startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)
```

**Step 8: Commit**

```bash
git add projects/monolith/chat/summarizer.py projects/monolith/chat/changelog.py projects/monolith/chat/startup_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add chat scheduler handlers for summary and changelog"
```

---

### Task 7: Rewire `main.py` — Replace Loops with Startup Hooks

**Files:**

- Modify: `projects/monolith/app/main.py`
- Modify: `projects/monolith/app/main_test.py` (and other main\_\*\_test.py as needed)

**Step 1: Rewrite the lifespan**

Replace the 4 separate asyncio loops with startup hooks + single scheduler loop. The lock sweep stays in-memory.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db import get_engine
    from shared.scheduler import run_scheduler_loop
    from sqlmodel import Session

    # Register all scheduled jobs
    with Session(get_engine()) as session:
        from home.service import on_startup as home_startup
        from shared.service import on_startup as shared_startup

        home_startup(session)
        shared_startup(session)

        bot = None
        discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
        if discord_token:
            from chat.bot import create_bot
            from chat.summarizer import build_llm_caller
            from chat.summarizer import on_startup as chat_startup

            bot = create_bot()
            app.state.bot = bot
            chat_startup(session, bot=bot, llm_call=build_llm_caller())

    # Start scheduler loop (replaces 4 separate asyncio tasks)
    scheduler_task = asyncio.create_task(run_scheduler_loop())
    scheduler_task.add_done_callback(_log_task_exception)

    # Start Discord bot if configured
    bot_task = None
    if discord_token and bot:
        async def _start_bot_when_ready():
            await _wait_for_sidecar()
            await bot.start(discord_token)

        bot_task = asyncio.create_task(_start_bot_when_ready())
        bot_task.add_done_callback(_log_task_exception)
        logger.info("Discord bot starting")

    # Lock sweep stays in-memory (30s, bot-coupled, already multi-pod safe via SKIP LOCKED)
    sweep_task = None
    if discord_token and bot:
        # ... (keep existing _lock_sweep_loop unchanged)
        sweep_task = asyncio.create_task(_lock_sweep_loop())
        sweep_task.add_done_callback(_log_task_exception)

    app.state.backfill_task = None
    logger.info("Monolith started")
    yield

    # Cleanup
    backfill_task = getattr(app.state, "backfill_task", None)
    if backfill_task and not backfill_task.done():
        backfill_task.cancel()
    if sweep_task:
        sweep_task.cancel()
    if bot:
        await bot.close()
    if bot_task:
        bot_task.cancel()
    scheduler_task.cancel()
    logger.info("Monolith shutting down")
```

Key changes:

- Remove `calendar_loop` inline function
- Remove `_summary_loop` inline function
- Remove `changelog_loop` import and task
- Remove `run_scheduler` import (old home scheduler)
- Add single `run_scheduler_loop()` task
- Register jobs via startup hooks before starting the loop

**Step 2: Update existing main tests**

Many `main_*_test.py` files mock the old loops. Update patches to mock the new startup hooks and `run_scheduler_loop`. The key mock changes:

- `patch("home.scheduler.run_scheduler")` → `patch("shared.scheduler.run_scheduler_loop")`
- Remove mocks for `calendar_loop`, `_summary_loop`, `changelog_loop`
- Add mocks for `home.service.on_startup`, `shared.service.on_startup`, `chat.summarizer.on_startup`

**Step 3: Run all tests**

Run: `bb remote test //projects/monolith:main_test //projects/monolith:main_coverage_test //projects/monolith:main_extra_test //projects/monolith:main_lock_sweep_test //projects/monolith:main_app_state_test //projects/monolith:main_sidecar_test //projects/monolith:app_main_summary_test //projects/monolith:app_main_summary_edge_test --config=ci`
Expected: PASS

**Step 4: Commit**

```bash
git add projects/monolith/app/main.py projects/monolith/app/main_test.py projects/monolith/app/main_coverage_test.py projects/monolith/app/main_extra_test.py
git commit -m "feat(monolith): rewire main.py to use pg-backed scheduler"
```

---

### Task 8: Cleanup — Remove Old Scheduler + Update Existing Tests

**Files:**

- Delete: `projects/monolith/home/scheduler.py`
- Delete: `projects/monolith/home/scheduler_test.py`
- Modify: `projects/monolith/chat/changelog.py` — remove `changelog_loop()` (kept `run_changelog_iteration()`)
- Modify: `projects/monolith/BUILD` — remove `home_scheduler_test` target

**Step 1: Delete old files**

```bash
rm projects/monolith/home/scheduler.py
rm projects/monolith/home/scheduler_test.py
```

**Step 2: Remove `changelog_loop()` from `chat/changelog.py`**

Delete the `changelog_loop()` function and `_seconds_until_next_hour()` helper — they're replaced by the scheduler handler. Keep `run_changelog_iteration()` and all the helper functions it uses.

**Step 3: Remove BUILD target**

Remove the `home_scheduler_test` py_test block from `BUILD`.

**Step 4: Run full test suite**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: PASS (all tests green)

**Step 5: Commit**

```bash
git add -A projects/monolith/home/scheduler.py projects/monolith/home/scheduler_test.py projects/monolith/chat/changelog.py projects/monolith/BUILD
git commit -m "refactor(monolith): remove old in-memory scheduler and changelog loop"
```

---

### Task 9: Deploy — Bump Chart Version + Verify

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` — bump version
- Modify: `projects/monolith/deploy/application.yaml` — update `targetRevision`

**Step 1: Bump chart version**

Increment the patch version in `Chart.yaml`. Also update `targetRevision` in `deploy/application.yaml` to match (per CLAUDE.md: both must stay in sync).

**Step 2: Run e2e tests**

Run: `bb remote test //projects/monolith:e2e_test --config=ci`
Expected: PASS (validates the new migration runs against a real Postgres)

**Step 3: Commit**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version for pg-backed scheduler"
```

**Step 4: Push and create PR**

```bash
git push -u origin feat/pg-scheduler
gh pr create --title "feat(monolith): pg-backed scheduler" --body "$(cat <<'EOF'
## Summary
- Replace 4 in-memory asyncio background loops with a Postgres-backed scheduler
- New `scheduler.scheduled_jobs` table with distributed locking via `FOR UPDATE SKIP LOCKED`
- Each service registers jobs via startup hooks (`home.on_startup`, `shared.on_startup`, `chat.on_startup`)
- Single `run_scheduler_loop()` polls every 30s, claims due jobs, handles TTL-based lock expiry
- Message lock sweep stays in-memory (bot-coupled, already multi-pod safe)

## Jobs
| Job | Interval | TTL |
|-----|----------|-----|
| home.daily_reset | 24h | 10m |
| shared.calendar_poll | 15m | 2m |
| chat.summary_generation | 24h | 30m |
| chat.changelog | 1h | 5m |

## Test plan
- [ ] Unit tests for ScheduledJob model, register_job, scheduler loop
- [ ] Unit tests for each handler (daily_reset, calendar_poll, summary, changelog)
- [ ] Updated main.py tests with new startup hook mocks
- [ ] e2e test validates migration runs against real Postgres
- [ ] Verify ArgoCD deploys new chart version
- [ ] Check `scheduler.scheduled_jobs` table has correct rows after startup

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 5: Monitor deployment**

After PR merges, verify via MCP tools:

- ArgoCD app is synced and healthy
- Pod logs show "Scheduler loop started" and "Registered job" messages
- Query `scheduler.scheduled_jobs` table to verify jobs are registered
