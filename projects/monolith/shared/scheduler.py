"""Postgres-backed job scheduler with distributed locking."""

import asyncio
import logging
import platform
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlmodel import Field, Session, SQLModel, select, text

from app.db import get_engine

logger = logging.getLogger(__name__)

_HOSTNAME = platform.node()


class ScheduledJob(SQLModel, table=True):
    __tablename__ = "scheduled_jobs"
    __table_args__ = {"schema": "scheduler", "extend_existing": True}

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
    logger.info(
        "Registered job %s (interval=%ds, ttl=%ds)", name, interval_secs, ttl_secs
    )


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
    session.commit()
    return row[0] if row else None


def _complete_job(
    session: Session, job: ScheduledJob, override: datetime | None
) -> None:
    """Mark a job as succeeded and advance next_run_at."""
    now = datetime.now(timezone.utc)
    job.locked_by = None
    job.locked_at = None
    job.last_run_at = now
    job.last_status = "ok"
    job.next_run_at = override or (now + timedelta(seconds=job.interval_secs))
    session.add(job)
    session.commit()
    logger.info(
        "Job %s completed, next run at %s", job.name, job.next_run_at.isoformat()
    )


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
