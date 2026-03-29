from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class AttendanceReaderTypeEnum(str, Enum):
    """Supported attendance reader types sent by the external pointage app."""

    IN = "IN"
    OUT = "OUT"


class AttendanceStatusEnum(str, Enum):
    """Supported day-level attendance statuses."""

    PRESENT = "present"
    INCOMPLETE = "incomplete"
    ABSENT = "absent"
    LEAVE = "leave"


class NfcCard(Base):
    """Simple NFC card to employee mapping used for attendance resolution."""

    __tablename__ = "nfc_cards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nfc_uid: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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


class AttendanceRawScanEvent(Base):
    """Short-term raw traceability record for a scan event ingestion."""

    __tablename__ = "attendance_raw_scan_events"

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
    reader_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )


class AttendanceDailySummary(Base):
    """Main day-level attendance record used for ongoing attendance tracking."""

    __tablename__ = "attendance_daily_summaries"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "attendance_date",
            name="uq_attendance_daily_summaries_employee_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    first_check_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_check_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    worked_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=AttendanceStatusEnum.ABSENT.value,
        nullable=False,
        index=True,
    )
    linked_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("requests.id", ondelete="SET NULL"),
        nullable=True,
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


class AttendanceMonthlyReport(Base):
    """Stored monthly aggregate generated from daily attendance summaries."""

    __tablename__ = "attendance_monthly_reports"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "report_year",
            "report_month",
            name="uq_attendance_monthly_reports_employee_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    report_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    report_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_worked_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_worked_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_present_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_absence_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_leave_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    "AttendanceDailySummary",
    "AttendanceMonthlyReport",
    "AttendanceRawScanEvent",
    "AttendanceReaderTypeEnum",
    "AttendanceStatusEnum",
    "NfcCard",
]
