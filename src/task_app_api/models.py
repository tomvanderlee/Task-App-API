from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class TaskStatus(StrEnum):
    todo = 'todo'
    in_progress = 'in_progress'
    done = 'done'


class TaskInput(SQLModel):
    title: str
    status: TaskStatus


class Task(TaskInput, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(foreign_key='user.id')
    created_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str


class PaginatedResponse(SQLModel):
    next: int | None = None
    prev: int | None = None
    items: list[dict]


class Error(SQLModel):
    detail: str
