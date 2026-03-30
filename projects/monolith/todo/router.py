import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session

from .models import Archive, Task
from .service import archive_and_reset

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/todo", tags=["todo"])

ROLLING_WINDOW_DAYS = 14


class TaskResponse(BaseModel):
    task: str
    done: bool


class TodoData(BaseModel):
    weekly: TaskResponse
    daily: list[TaskResponse]


@router.get("/weekly")
def get_weekly(session: Session = Depends(get_session)) -> TaskResponse:
    task = session.exec(select(Task).where(Task.kind == "weekly")).first()
    if not task:
        return TaskResponse(task="", done=False)
    return TaskResponse(task=task.task, done=task.done)


@router.get("/daily")
def get_daily(session: Session = Depends(get_session)) -> list[TaskResponse]:
    tasks = session.exec(
        select(Task).where(Task.kind == "daily").order_by(Task.position)
    ).all()
    if not tasks:
        return [TaskResponse(task="", done=False) for _ in range(3)]
    return [TaskResponse(task=t.task, done=t.done) for t in tasks]


@router.get("")
def get_todo(session: Session = Depends(get_session)) -> TodoData:
    weekly = session.exec(select(Task).where(Task.kind == "weekly")).first()
    daily = session.exec(
        select(Task).where(Task.kind == "daily").order_by(Task.position)
    ).all()
    return TodoData(
        weekly=TaskResponse(
            task=weekly.task if weekly else "",
            done=weekly.done if weekly else False,
        ),
        daily=[TaskResponse(task=t.task, done=t.done) for t in daily]
        or [TaskResponse(task="", done=False) for _ in range(3)],
    )


@router.put("")
def update_todo(data: TodoData, session: Session = Depends(get_session)) -> None:
    # Clear existing tasks
    existing = session.exec(select(Task)).all()
    for t in existing:
        session.delete(t)

    # Write weekly
    session.add(
        Task(task=data.weekly.task, done=data.weekly.done, kind="weekly", position=0)
    )

    # Write daily
    for i, d in enumerate(data.daily):
        session.add(Task(task=d.task, done=d.done, kind="daily", position=i))

    session.commit()


@router.get("/dates")
def get_dates(session: Session = Depends(get_session)) -> list[str]:
    cutoff = date.today() - timedelta(days=ROLLING_WINDOW_DAYS)
    archives = session.exec(
        select(Archive.date).where(Archive.date >= cutoff).order_by(Archive.date)
    ).all()
    dates = [d.isoformat() for d in archives]
    today = date.today().isoformat()
    if not dates or dates[-1] != today:
        dates.append(today)
    return dates


@router.get("/archive/{archive_date}")
def get_archive(archive_date: str, session: Session = Depends(get_session)) -> dict:
    try:
        d = date.fromisoformat(archive_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format") from exc
    archive = session.exec(select(Archive).where(Archive.date == d)).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    return {"date": archive.date.isoformat(), "content": archive.content}


@router.post("/reset/daily")
def reset_daily(session: Session = Depends(get_session)) -> None:
    archive_and_reset(session, weekly_reset=False)


@router.post("/reset/weekly")
def reset_weekly(session: Session = Depends(get_session)) -> None:
    archive_and_reset(session, weekly_reset=True)
