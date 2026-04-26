from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class ForgotBadgeRequestStatusEnum(str, Enum):
    """Status values for forgot badge requests."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TemporaryNfcAssignmentStatusEnum(str, Enum):
    """Status values for temporary NFC card assignments."""

    ACTIVE = "ACTIVE"
    USED = "USED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class ForgotBadgeRequest(Base):
    """Request created by an employee who forgot their badge."""

    __tablename__ = "forgot_badge_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=ForgotBadgeRequestStatusEnum.PENDING.value,
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    handled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    handled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    nfc_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("nfc_cards.id", ondelete="SET NULL"),
        nullable=True,
    )
    valid_for_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class TemporaryNfcAssignment(Base):
    """Temporary NFC card assignment for forgot badge scenarios."""

    __tablename__ = "temporary_nfc_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nfc_card_id: Mapped[int] = mapped_column(
        ForeignKey("nfc_cards.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    forgot_badge_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("forgot_badge_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    valid_for_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=TemporaryNfcAssignmentStatusEnum.ACTIVE.value,
        nullable=False,
        index=True,
    )
    check_in_attendance_id: Mapped[int | None] = mapped_column(
        ForeignKey("attendance_raw_scan_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    check_out_attendance_id: Mapped[int | None] = mapped_column(
        ForeignKey("attendance_raw_scan_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    released_at: Mapped[datetime | None] = mapped_column(
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


__all__ = [
    "ForgotBadgeRequest",
    "ForgotBadgeRequestStatusEnum",
    "TemporaryNfcAssignment",
    "TemporaryNfcAssignmentStatusEnum",
]