from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.auth.dependencies import get_current_active_user
from app.apps.dashboard.dependencies import get_dashboard_service
from app.apps.dashboard.schemas import (
    DashboardAttendanceSummaryResponse,
    DashboardEmployeesSummaryResponse,
    DashboardOverviewResponse,
    DashboardPerformanceSummaryResponse,
    DashboardRequestsSummaryResponse,
    DashboardStatusResponse,
)
from app.apps.dashboard.service import (
    DashboardAuthorizationError,
    DashboardService,
    DashboardValidationError,
)
from app.apps.permissions.dependencies import require_permission
from app.apps.users.models import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def raise_dashboard_http_error(exc: Exception) -> None:
    """Map dashboard service errors to HTTP exceptions."""

    if isinstance(exc, DashboardValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if isinstance(exc, DashboardAuthorizationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    raise exc


@router.get(
    "/status",
    response_model=DashboardStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check dashboard module availability",
)
def get_dashboard_status(
    _service: DashboardService = Depends(get_dashboard_service),
    _current_user: User = Depends(get_current_active_user),
) -> DashboardStatusResponse:
    return DashboardStatusResponse(
        status="ready",
        detail="Dashboard module router is registered.",
    )


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the global dashboard overview",
)
def get_overview(
    target_date: date | None = Query(default=None, alias="date"),
    team_id: int | None = Query(default=None, ge=1),
    department_id: int | None = Query(default=None, ge=1),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: User = Depends(require_permission("dashboard.read")),
) -> DashboardOverviewResponse:
    try:
        return service.get_overview(
            current_user,
            target_date=target_date,
            team_id=team_id,
            department_id=department_id,
        )
    except (DashboardAuthorizationError, DashboardValidationError) as exc:
        raise_dashboard_http_error(exc)


@router.get(
    "/requests-summary",
    response_model=DashboardRequestsSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard request aggregates",
)
def get_requests_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    team_id: int | None = Query(default=None, ge=1),
    department_id: int | None = Query(default=None, ge=1),
    recent_limit: int = Query(default=5, ge=1, le=20),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: User = Depends(require_permission("dashboard.read")),
) -> DashboardRequestsSummaryResponse:
    try:
        return service.get_requests_summary(
            current_user,
            date_from=date_from,
            date_to=date_to,
            team_id=team_id,
            department_id=department_id,
            recent_limit=recent_limit,
        )
    except (DashboardAuthorizationError, DashboardValidationError) as exc:
        raise_dashboard_http_error(exc)


@router.get(
    "/attendance-summary",
    response_model=DashboardAttendanceSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard attendance aggregates",
)
def get_attendance_summary(
    target_date: date | None = Query(default=None, alias="date"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    team_id: int | None = Query(default=None, ge=1),
    department_id: int | None = Query(default=None, ge=1),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: User = Depends(require_permission("dashboard.read")),
) -> DashboardAttendanceSummaryResponse:
    try:
        return service.get_attendance_summary(
            current_user,
            target_date=target_date,
            date_from=date_from,
            date_to=date_to,
            team_id=team_id,
            department_id=department_id,
        )
    except (DashboardAuthorizationError, DashboardValidationError) as exc:
        raise_dashboard_http_error(exc)


@router.get(
    "/performance-summary",
    response_model=DashboardPerformanceSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard performance aggregates",
)
def get_performance_summary(
    target_date: date | None = Query(default=None, alias="date"),
    team_id: int | None = Query(default=None, ge=1),
    department_id: int | None = Query(default=None, ge=1),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: User = Depends(require_permission("dashboard.read")),
) -> DashboardPerformanceSummaryResponse:
    try:
        return service.get_performance_summary(
            current_user,
            target_date=target_date,
            team_id=team_id,
            department_id=department_id,
        )
    except (DashboardAuthorizationError, DashboardValidationError) as exc:
        raise_dashboard_http_error(exc)


@router.get(
    "/employees-summary",
    response_model=DashboardEmployeesSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard employee aggregates",
)
def get_employees_summary(
    team_id: int | None = Query(default=None, ge=1),
    department_id: int | None = Query(default=None, ge=1),
    service: DashboardService = Depends(get_dashboard_service),
    current_user: User = Depends(require_permission("dashboard.read")),
) -> DashboardEmployeesSummaryResponse:
    try:
        return service.get_employees_summary(
            current_user,
            team_id=team_id,
            department_id=department_id,
        )
    except (DashboardAuthorizationError, DashboardValidationError) as exc:
        raise_dashboard_http_error(exc)
