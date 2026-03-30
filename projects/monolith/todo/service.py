"""Todo business logic — the module's internal interface.

Other modules should import from here, never from router.py.
"""

import logging
from datetime import date

from sqlmodel import Session, select

from .models import Archive, Task

logger = logging.getLogger(__name__)


def archive_and_reset(session: Session, weekly_reset: bool) -> None:
    """Archive current state to markdown, then reset tasks."""
    weekly = session.exec(select(Task).where(Task.kind == "weekly")).first()
    daily = session.exec(
        select(Task).where(Task.kind == "daily").order_by(Task.position)
    ).all()

    # Build markdown archive
    today = date.today()
    lines = [f"# {today.strftime('%A, %B %-d')}\n"]
    lines.append("## Weekly")
    lines.append(weekly.task if weekly and weekly.task else "(none)")
    lines.append("")
    lines.append("## Daily")
    for t in daily:
        if t.task:
            check = "x" if t.done else " "
            lines.append(f"- [{check}] {t.task}")

    existing_archive = session.exec(
        select(Archive).where(Archive.date == today)
    ).first()
    if existing_archive:
        existing_archive.content = "\n".join(lines)
    else:
        session.add(Archive(date=today, content="\n".join(lines)))

    # Clear tasks
    existing = session.exec(select(Task)).all()
    for t in existing:
        session.delete(t)

    if not weekly_reset and weekly:
        # Keep weekly task on daily reset
        session.add(Task(task=weekly.task, done=weekly.done, kind="weekly", position=0))

    # Add empty daily slots
    for i in range(3):
        session.add(Task(task="", done=False, kind="daily", position=i))

    session.commit()
    logger.info("Reset completed (weekly=%s)", weekly_reset)
