from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.apps.auth.dependencies import get_current_active_user
from app.apps.performance.dependencies import get_performance_service
from app.apps.performance.schemas import (
    PerformanceStatusResponse,
    TeamDailyPerformanceCreateRequest,
    TeamDailyPerformanceResponse,
    TeamObjectiveCreateRequest,
    TeamObjectiveResponse,
    TeamObjectiveUpdateRequest,
)
from app.apps.performance.service import (
    PerformanceAuthorizationError,
    PerformanceConflictError,
    PerformanceNotFoundError,
    PerformanceService,
    PerformanceValidationError,
)
from app.apps.permissions.dependencies import require_permission
from app.apps.users.models import User

router = APIRouter(prefix="/performance", tags=["Performance"])


def raise_performance_http_error(exc: Exception) -> None:
    """Map performance service errors to HTTP exceptions."""

    if isinstance(exc, PerformanceNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if isinstance(exc, PerformanceValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if isinstance(exc, PerformanceConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if isinstance(exc, PerformanceAuthorizationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    raise exc


@router.get(
    "/status",
    response_model=PerformanceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check performance module availability",
)
def get_performance_status(
    _service: PerformanceService = Depends(get_performance_service),
    _current_user: User = Depends(get_current_active_user),
) -> PerformanceStatusResponse:
    return PerformanceStatusResponse(
        status="ready",
        detail="Performance module router is registered.",
    )


@router.post(
    "/objectives",
    response_model=TeamObjectiveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team objective",
)
def create_team_objective(
    payload: TeamObjectiveCreateRequest,
    service: PerformanceService = Depends(get_performance_service),
    _current_user: User = Depends(require_permission("performance.manage")),
) -> TeamObjectiveResponse:
    try:
        objective = service.create_team_objective(payload)
    except (
        PerformanceConflictError,
        PerformanceNotFoundError,
        PerformanceValidationError,
    ) as exc:
        raise_performance_http_error(exc)

    return service.build_team_objective_response(objective)


@router.patch(
    "/objectives/{objective_id}",
    response_model=TeamObjectiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a team objective",
)
def update_team_objective(
    objective_id: int,
    payload: TeamObjectiveUpdateRequest,
    service: PerformanceService = Depends(get_performance_service),
    _current_user: User = Depends(require_permission("performance.manage")),
) -> TeamObjectiveResponse:
    try:
        objective = service.update_team_objective(objective_id, payload)
    except (
        PerformanceConflictError,
        PerformanceNotFoundError,
        PerformanceValidationError,
    ) as exc:
        raise_performance_http_error(exc)

    return service.build_team_objective_response(objective)


@router.get(
    "/objectives",
    response_model=list[TeamObjectiveResponse],
    status_code=status.HTTP_200_OK,
    summary="List team objectives",
)
def list_team_objectives(
    team_id: int | None = Query(default=None, ge=1),
    include_inactive: bool = Query(default=False),
    service: PerformanceService = Depends(get_performance_service),
    _current_user: User = Depends(require_permission("performance.manage")),
) -> list[TeamObjectiveResponse]:
    try:
        objectives = service.list_team_objectives(
            team_id=team_id,
            include_inactive=include_inactive,
        )
    except (PerformanceNotFoundError, PerformanceValidationError) as exc:
        raise_performance_http_error(exc)

    return service.build_team_objective_responses(objectives)


@router.get(
    "/objectives/team/{team_id}",
    response_model=TeamObjectiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the active objective for a team",
)
def get_active_objective_for_team(
    team_id: int,
    service: PerformanceService = Depends(get_performance_service),
    _current_user: User = Depends(require_permission("performance.manage")),
) -> TeamObjectiveResponse:
    try:
        objective = service.get_active_objective_for_team(team_id)
    except (PerformanceNotFoundError, PerformanceValidationError) as exc:
        raise_performance_http_error(exc)

    return service.build_team_objective_response(objective)


@router.post(
    "/daily-performances",
    response_model=TeamDailyPerformanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit daily achieved value for a team",
)
def submit_daily_performance(
    payload: TeamDailyPerformanceCreateRequest,
    service: PerformanceService = Depends(get_performance_service),
    current_user: User = Depends(require_permission("performance.create")),
) -> TeamDailyPerformanceResponse:
    try:
        performance = service.submit_daily_performance(current_user, payload)
    except (
        PerformanceAuthorizationError,
        PerformanceConflictError,
        PerformanceNotFoundError,
        PerformanceValidationError,
    ) as exc:
        raise_performance_http_error(exc)

    return service.build_daily_performance_response(performance)


@router.get(
    "/daily-performances",
    response_model=list[TeamDailyPerformanceResponse],
    status_code=status.HTTP_200_OK,
    summary="List team daily performance records",
)
def list_daily_performances(
    team_id: int | None = Query(default=None, ge=1),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: PerformanceService = Depends(get_performance_service),
    current_user: User = Depends(require_permission("performance.read")),
) -> list[TeamDailyPerformanceResponse]:
    try:
        performances = service.list_daily_performances(
            current_user,
            team_id=team_id,
            date_from=date_from,
            date_to=date_to,
        )
    except (
        PerformanceAuthorizationError,
        PerformanceNotFoundError,
        PerformanceValidationError,
    ) as exc:
        raise_performance_http_error(exc)

    return service.build_daily_performance_responses(performances)


@router.get(
    "/teams/{team_id}/daily-performances/{performance_date}",
    response_model=TeamDailyPerformanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get daily performance for one team and one day",
)
def get_daily_performance(
    team_id: int,
    performance_date: date = Path(...),
    service: PerformanceService = Depends(get_performance_service),
    current_user: User = Depends(require_permission("performance.read")),
) -> TeamDailyPerformanceResponse:
    try:
        performance = service.get_daily_performance(
            current_user,
            team_id=team_id,
            performance_date=performance_date,
        )
    except (
        PerformanceAuthorizationError,
        PerformanceNotFoundError,
        PerformanceValidationError,
    ) as exc:
        raise_performance_http_error(exc)

    return service.build_daily_performance_response(performance)
