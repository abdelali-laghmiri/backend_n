from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.attendance.service import AttendanceService
from app.core.dependencies import get_db_session


def get_attendance_service(
    db: Session = Depends(get_db_session),
) -> AttendanceService:
    """Provide the attendance service instance."""

    return AttendanceService(db=db)
