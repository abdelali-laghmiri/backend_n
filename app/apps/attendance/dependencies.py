from __future__ import annotations

from app.apps.attendance.service import AttendanceService


def get_attendance_service() -> AttendanceService:
    """Provide the attendance service instance."""

    return AttendanceService()
