from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.apps.attendance.dependencies import get_attendance_service
from app.apps.attendance.schemas import AttendanceStatusResponse
from app.apps.attendance.service import AttendanceService

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.get(
    "/status",
    response_model=AttendanceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check attendance module availability",
)
def get_attendance_status(
    _service: AttendanceService = Depends(get_attendance_service),
) -> AttendanceStatusResponse:
    return AttendanceStatusResponse(
        status="ready",
        detail="Attendance module router is registered.",
    )
