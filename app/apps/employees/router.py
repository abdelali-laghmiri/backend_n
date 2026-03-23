from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.employees.dependencies import get_employees_service
from app.apps.employees.schemas import (
    EmployeeAccountBootstrapResponse,
    EmployeeCreateRequest,
    EmployeeCreateResponse,
    EmployeeResponse,
    EmployeeUpdateRequest,
)
from app.apps.permissions.dependencies import require_permission
from app.apps.employees.service import (
    EmployeesConflictError,
    EmployeesNotFoundError,
    EmployeesService,
    EmployeesValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/employees", tags=["Employees"])


def raise_employees_http_error(exc: Exception) -> None:
    """Map employee service errors to HTTP exceptions."""

    if isinstance(exc, EmployeesNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, EmployeesValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, EmployeesConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "",
    response_model=EmployeeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee and linked user account",
)
def create_employee(
    payload: EmployeeCreateRequest,
    service: EmployeesService = Depends(get_employees_service),
    _current_user: User = Depends(require_permission("employees.create")),
) -> EmployeeCreateResponse:
    try:
        employee, temporary_password = service.create_employee(payload)
    except (EmployeesConflictError, EmployeesValidationError) as exc:
        raise_employees_http_error(exc)

    return EmployeeCreateResponse(
        employee=EmployeeResponse.model_validate(employee),
        account=EmployeeAccountBootstrapResponse(
            user_id=employee.user_id,
            matricule=employee.matricule,
            email=employee.email,
            temporary_password=temporary_password,
            must_change_password=True,
            is_active=employee.is_active,
        ),
    )


@router.get(
    "",
    response_model=list[EmployeeResponse],
    status_code=status.HTTP_200_OK,
    summary="List employees",
)
def list_employees(
    include_inactive: bool = Query(default=False),
    q: str | None = Query(default=None),
    department_id: int | None = Query(default=None, ge=1),
    team_id: int | None = Query(default=None, ge=1),
    job_title_id: int | None = Query(default=None, ge=1),
    service: EmployeesService = Depends(get_employees_service),
    _current_user: User = Depends(require_permission("employees.read")),
) -> list[EmployeeResponse]:
    employees = service.list_employees(
        include_inactive=include_inactive,
        q=q,
        department_id=department_id,
        team_id=team_id,
        job_title_id=job_title_id,
    )
    return [EmployeeResponse.model_validate(item) for item in employees]


@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get an employee by id",
)
def get_employee(
    employee_id: int,
    service: EmployeesService = Depends(get_employees_service),
    _current_user: User = Depends(require_permission("employees.read")),
) -> EmployeeResponse:
    try:
        employee = service.get_employee(employee_id)
    except EmployeesNotFoundError as exc:
        raise_employees_http_error(exc)

    return EmployeeResponse.model_validate(employee)


@router.patch(
    "/{employee_id}",
    response_model=EmployeeResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an employee and linked account data",
)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdateRequest,
    service: EmployeesService = Depends(get_employees_service),
    _current_user: User = Depends(require_permission("employees.update")),
) -> EmployeeResponse:
    try:
        employee = service.update_employee(employee_id, payload)
    except (
        EmployeesConflictError,
        EmployeesNotFoundError,
        EmployeesValidationError,
    ) as exc:
        raise_employees_http_error(exc)

    return EmployeeResponse.model_validate(employee)
