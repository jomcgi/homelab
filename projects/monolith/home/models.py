from datetime import date

from sqlmodel import Field, SQLModel


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    __table_args__ = {"schema": "home", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    task: str = ""
    done: bool = False
    kind: str = "daily"  # "daily" or "weekly"
    position: int = 0  # ordering within kind


class Archive(SQLModel, table=True):
    __tablename__ = "archives"
    __table_args__ = {"schema": "home", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    date: date
    content: str  # rendered markdown
