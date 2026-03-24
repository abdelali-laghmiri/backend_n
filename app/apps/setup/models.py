from __future__ import annotations

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class InstallationState(Base):
    """Persist the one-time installation lifecycle and wizard draft state."""

    __tablename__ = "installation_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, default=1)
    is_initialized: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    initialized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    initialized_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    wizard_state: Mapped[dict[str, object]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
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


__all__ = ["InstallationState"]
