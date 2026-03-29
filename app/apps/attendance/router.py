from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.apps.attendance.dependencies import get_attendance_service
from app.apps.attendance.models import AttendanceStatusEnum
from app.apps.attendance.schemas import (
    AttendanceDailySummaryResponse,
    AttendanceNfcCardAssignRequest,
    AttendanceNfcCardResponse,
    AttendanceNfcScanIngestRequest,
    AttendanceMonthlyReportGenerateRequest,
    AttendanceMonthlyReportGenerateResponse,
    AttendanceMonthlyReportResponse,
    AttendanceScanIngestRequest,
    AttendanceScanIngestResponse,
    AttendanceStatusResponse,
)
from app.apps.attendance.service import (
    AttendanceConflictError,
    AttendanceNotFoundError,
    AttendanceService,
    AttendanceValidationError,
)
from app.apps.permissions.dependencies import require_permission
from app.apps.users.models import User

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def raise_attendance_http_error(exc: Exception) -> None:
    """Map attendance service errors to HTTP exceptions."""

    if isinstance(exc, AttendanceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, AttendanceValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, AttendanceConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


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


@router.post(
    "/scans",
    response_model=AttendanceScanIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an external attendance scan event",
)
def ingest_scan_event(
    payload: AttendanceScanIngestRequest,
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.ingest")),
) -> AttendanceScanIngestResponse:
    try:
        raw_event, daily_summary = service.ingest_scan_event(payload)
    except (
        AttendanceConflictError,
        AttendanceNotFoundError,
        AttendanceValidationError,
    ) as exc:
        raise_attendance_http_error(exc)

    return service.build_scan_ingest_response(raw_event, daily_summary)


@router.post(
    "/nfc-scans",
    response_model=AttendanceScanIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an NFC attendance scan event",
)
def ingest_nfc_scan_event(
    payload: AttendanceNfcScanIngestRequest,
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.ingest")),
) -> AttendanceScanIngestResponse:
    try:
        raw_event, daily_summary = service.ingest_nfc_scan_event(payload)
    except (
        AttendanceConflictError,
        AttendanceNotFoundError,
        AttendanceValidationError,
    ) as exc:
        raise_attendance_http_error(exc)

    return service.build_scan_ingest_response(raw_event, daily_summary)


@router.post(
    "/nfc-cards/assign",
    response_model=AttendanceNfcCardResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign an NFC card to an employee",
)
def assign_nfc_card(
    payload: AttendanceNfcCardAssignRequest,
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.nfc.assign_card")),
) -> AttendanceNfcCardResponse:
    try:
        nfc_card = service.assign_nfc_card(payload)
    except (
        AttendanceConflictError,
        AttendanceNotFoundError,
        AttendanceValidationError,
    ) as exc:
        raise_attendance_http_error(exc)

    return service.build_nfc_card_response(nfc_card)


@router.get(
    "/daily-summaries",
    response_model=list[AttendanceDailySummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List daily attendance summaries",
)
def list_daily_summaries(
    employee_id: int | None = Query(default=None, ge=1),
    matricule: str | None = Query(default=None),
    status_filter: AttendanceStatusEnum | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.read")),
) -> list[AttendanceDailySummaryResponse]:
    try:
        summaries = service.list_daily_summaries(
            employee_id=employee_id,
            matricule=matricule,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
            include_inactive=include_inactive,
        )
    except AttendanceValidationError as exc:
        raise_attendance_http_error(exc)

    return service.build_daily_summary_responses(summaries)


@router.get(
    "/employees/{employee_id}/daily-summaries",
    response_model=list[AttendanceDailySummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="Get daily attendance summaries for one employee",
)
def get_employee_daily_summaries(
    employee_id: int,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.read")),
) -> list[AttendanceDailySummaryResponse]:
    try:
        summaries = service.get_employee_daily_summaries(
            employee_id,
            date_from=date_from,
            date_to=date_to,
        )
    except (AttendanceNotFoundError, AttendanceValidationError) as exc:
        raise_attendance_http_error(exc)

    return service.build_daily_summary_responses(summaries)


@router.post(
    "/monthly-reports/generate",
    response_model=AttendanceMonthlyReportGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate monthly attendance reports",
)
def generate_monthly_reports(
    payload: AttendanceMonthlyReportGenerateRequest,
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.reports.generate")),
) -> AttendanceMonthlyReportGenerateResponse:
    try:
        reports = service.generate_monthly_reports(payload)
    except (
        AttendanceConflictError,
        AttendanceNotFoundError,
        AttendanceValidationError,
    ) as exc:
        raise_attendance_http_error(exc)

    report_responses = service.build_monthly_report_responses(reports)
    return AttendanceMonthlyReportGenerateResponse(
        report_year=payload.report_year,
        report_month=payload.report_month,
        generated_count=len(report_responses),
        reports=report_responses,
    )


@router.get(
    "/monthly-reports",
    response_model=list[AttendanceMonthlyReportResponse],
    status_code=status.HTTP_200_OK,
    summary="List monthly attendance reports",
)
def list_monthly_reports(
    employee_id: int | None = Query(default=None, ge=1),
    year: int | None = Query(default=None, ge=2000, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    include_inactive: bool = Query(default=False),
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.read")),
) -> list[AttendanceMonthlyReportResponse]:
    reports = service.list_monthly_reports(
        employee_id=employee_id,
        year=year,
        month=month,
        include_inactive=include_inactive,
    )
    return service.build_monthly_report_responses(reports)


@router.get(
    "/employees/{employee_id}/monthly-reports/{report_year}/{report_month}",
    response_model=AttendanceMonthlyReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Get one employee monthly attendance report",
)
def get_monthly_report(
    employee_id: int,
    report_year: int = Path(ge=2000, le=9999),
    report_month: int = Path(ge=1, le=12),
    service: AttendanceService = Depends(get_attendance_service),
    _current_user: User = Depends(require_permission("attendance.read")),
) -> AttendanceMonthlyReportResponse:
    try:
        report = service.get_monthly_report(employee_id, report_year, report_month)
    except AttendanceNotFoundError as exc:
        raise_attendance_http_error(exc)

    return service.build_monthly_report_response(report)
