from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class TaskStatusEnum(str, Enum):
    """Supported employee task lifecycle states."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriorityEnum(str, Enum):
    """Supported employee task priority labels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EmployeeTask(Base):
    """Small task assigned to one employee and shown in the mobile app."""

    __tablename__ = "employee_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=TaskStatusEnum.TODO.value,
        nullable=False,
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default=TaskPriorityEnum.MEDIUM.value,
        nullable=False,
        index=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


__all__ = ["EmployeeTask", "TaskPriorityEnum", "TaskStatusEnum"]
