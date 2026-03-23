from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class TeamObjectiveTypeEnum(str, Enum):
    """Common optional objective-type hints used by teams."""

    UNITS = "units"
    TASKS = "tasks"
    TICKETS = "tickets"


class TeamObjective(Base):
    """Configurable team objective used as the current performance target."""

    __tablename__ = "team_objectives"
    __table_args__ = (
        CheckConstraint("objective_value > 0", name="team_objectives_objective_value_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    objective_value: Mapped[float] = mapped_column(Float, nullable=False)
    objective_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
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


class TeamDailyPerformance(Base):
    """Stored team-level daily achieved value and calculated performance."""

    __tablename__ = "team_daily_performances"
    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "performance_date",
            name="uq_team_daily_performances_team_date",
        ),
        CheckConstraint("objective_value > 0", name="team_daily_performances_objective_value_positive"),
        CheckConstraint("achieved_value >= 0", name="team_daily_performances_achieved_value_non_negative"),
        CheckConstraint(
            "performance_percentage >= 0",
            name="team_daily_performances_performance_percentage_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    performance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    objective_value: Mapped[float] = mapped_column(Float, nullable=False)
    achieved_value: Mapped[float] = mapped_column(Float, nullable=False)
    performance_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
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


__all__ = [
    "TeamDailyPerformance",
    "TeamObjective",
    "TeamObjectiveTypeEnum",
]
