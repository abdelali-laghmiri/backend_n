from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.permissions.dependencies import require_permission
from app.apps.tasks.dependencies import get_tasks_service
from app.apps.tasks.models import TaskStatusEnum
from app.apps.tasks.schemas import (
    MobileTaskSummaryResponse,
    TaskCreateRequest,
    TaskResponse,
    TasksStatusResponse,
)
from app.apps.tasks.service import (
    TasksConflictError,
    TasksNotFoundError,
    TasksService,
    TasksValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def raise_tasks_http_error(exc: Exception) -> None:
    """Map tasks service errors to HTTP exceptions."""

    if isinstance(exc, TasksNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, TasksValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, TasksConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.get(
    "/status",
    response_model=TasksStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check tasks module availability",
)
def get_tasks_status(
    _service: TasksService = Depends(get_tasks_service),
) -> TasksStatusResponse:
    return TasksStatusResponse(
        status="ready",
        detail="Tasks module router is registered.",
    )


@router.get(
    "/my-summary",
    response_model=MobileTaskSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get mobile home data for the current employee",
)
def get_my_mobile_summary(
    target_date: date | None = Query(default=None, alias="date"),
    task_limit: int = Query(default=8, ge=1, le=20),
    service: TasksService = Depends(get_tasks_service),
    current_user: User = Depends(require_permission("tasks.view")),
) -> MobileTaskSummaryResponse:
    try:
        return service.get_mobile_summary(
            current_user,
            target_date=target_date,
            task_limit=task_limit,
        )
    except (TasksNotFoundError, TasksValidationError) as exc:
        raise_tasks_http_error(exc)


@router.get(
    "/my",
    response_model=list[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="List tasks assigned to the current employee",
)
def list_my_tasks(
    include_done: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    service: TasksService = Depends(get_tasks_service),
    current_user: User = Depends(require_permission("tasks.view")),
) -> list[TaskResponse]:
    try:
        tasks = service.list_my_tasks(
            current_user,
            include_done=include_done,
            limit=limit,
        )
    except (TasksNotFoundError, TasksValidationError) as exc:
        raise_tasks_http_error(exc)

    return service.build_task_responses(tasks)


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark one assigned task as done",
)
def complete_my_task(
    task_id: int,
    service: TasksService = Depends(get_tasks_service),
    current_user: User = Depends(require_permission("tasks.complete")),
) -> TaskResponse:
    try:
        task = service.complete_my_task(task_id, current_user)
    except (TasksConflictError, TasksNotFoundError, TasksValidationError) as exc:
        raise_tasks_http_error(exc)

    return service.build_task_response(task)


@router.get(
    "",
    response_model=list[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="List employee tasks for task managers",
)
def list_tasks(
    employee_id: int | None = Query(default=None, ge=1),
    status_filter: TaskStatusEnum | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TasksService = Depends(get_tasks_service),
    _current_user: User = Depends(require_permission("tasks.manage")),
) -> list[TaskResponse]:
    try:
        tasks = service.list_tasks(
            employee_id=employee_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except (TasksNotFoundError, TasksValidationError) as exc:
        raise_tasks_http_error(exc)

    return service.build_task_responses(tasks)


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign one task to an employee",
)
def create_task(
    payload: TaskCreateRequest,
    service: TasksService = Depends(get_tasks_service),
    current_user: User = Depends(require_permission("tasks.manage")),
) -> TaskResponse:
    try:
        task = service.create_task(payload, current_user)
    except (TasksConflictError, TasksNotFoundError, TasksValidationError) as exc:
        raise_tasks_http_error(exc)

    return service.build_task_response(task)
