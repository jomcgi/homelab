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
