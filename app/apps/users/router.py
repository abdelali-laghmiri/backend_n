from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.auth.dependencies import get_current_super_admin
from app.apps.users.dependencies import get_users_service
from app.apps.users.models import User
from app.apps.users.schemas import (
    UserActivateResponse,
    UserCreateRequest,
    UserEffectivePermissionsResponse,
    UserLinkedEmployeeSummaryResponse,
    UserPasswordResetResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.apps.users.service import (
    UsersConflictError,
    UsersNotFoundError,
    UsersService,
    UsersValidationError,
)

router = APIRouter(prefix="/users", tags=["Users"])


def raise_users_http_error(exc: Exception) -> None:
    """Map users service errors to HTTP exceptions."""

    if isinstance(exc, UsersNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, UsersValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, UsersConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


def _to_user_response(service: UsersService, user: User) -> UserResponse:
    linked_employee = service.get_linked_employee_by_user_id(user.id)
    return UserResponse(
        id=user.id,
        matricule=user.matricule,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_super_admin=user.is_super_admin,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        updated_at=user.updated_at,
        linked_employee=(
            UserLinkedEmployeeSummaryResponse(
                employee_id=linked_employee.id,
                hire_date=linked_employee.hire_date,
                department_id=linked_employee.department_id,
                team_id=linked_employee.team_id,
                job_title_id=linked_employee.job_title_id,
                is_active=linked_employee.is_active,
            )
            if linked_employee is not None
            else None
        ),
    )


@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    summary="Check users module availability",
)
def get_users_status(
    _service: UsersService = Depends(get_users_service),
) -> dict[str, str]:
    return {
        "status": "ready",
        "module": "users",
        "detail": "Users module router is registered.",
    }


@router.get(
    "",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List internal user accounts",
)
def list_users(
    include_inactive: bool = Query(default=False),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: UsersService = Depends(get_users_service),
    _current_user: User = Depends(get_current_super_admin),
) -> list[UserResponse]:
    users = service.list_users(
        q=q,
        include_inactive=include_inactive,
        limit=limit,
    )
    return [_to_user_response(service, user) for user in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get one user account by id",
)
def get_user(
    user_id: int,
    service: UsersService = Depends(get_users_service),
    _current_user: User = Depends(get_current_super_admin),
) -> UserResponse:
    try:
        user = service.get_user(user_id)
    except UsersNotFoundError as exc:
        raise_users_http_error(exc)

    return _to_user_response(service, user)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an internal user account",
)
def create_user(
    payload: UserCreateRequest,
    service: UsersService = Depends(get_users_service),
    _current_user: User = Depends(get_current_super_admin),
) -> UserResponse:
    try:
        user = service.create_user(payload)
    except (UsersConflictError, UsersValidationError) as exc:
        raise_users_http_error(exc)

    return _to_user_response(service, user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an internal user account",
)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    service: UsersService = Depends(get_users_service),
    current_user: User = Depends(get_current_super_admin),
) -> UserResponse:
    try:
        user = service.update_user(user_id, payload, current_admin=current_user)
    except (UsersConflictError, UsersNotFoundError, UsersValidationError) as exc:
        raise_users_http_error(exc)

    return _to_user_response(service, user)


@router.post(
    "/{user_id}/activate",
    response_model=UserActivateResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate a user account",
)
def activate_user(
    user_id: int,
    service: UsersService = Depends(get_users_service),
    current_user: User = Depends(get_current_super_admin),
) -> UserActivateResponse:
    try:
        user = service.set_user_active(user_id, is_active=True, current_admin=current_user)
    except (UsersConflictError, UsersNotFoundError, UsersValidationError) as exc:
        raise_users_http_error(exc)

    return UserActivateResponse(
        detail="User account activated successfully.",
        user=_to_user_response(service, user),
    )


@router.post(
    "/{user_id}/deactivate",
    response_model=UserActivateResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate a user account",
)
def deactivate_user(
    user_id: int,
    service: UsersService = Depends(get_users_service),
    current_user: User = Depends(get_current_super_admin),
) -> UserActivateResponse:
    try:
        user = service.set_user_active(user_id, is_active=False, current_admin=current_user)
    except (UsersConflictError, UsersNotFoundError, UsersValidationError) as exc:
        raise_users_http_error(exc)

    return UserActivateResponse(
        detail="User account deactivated successfully.",
        user=_to_user_response(service, user),
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=UserPasswordResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset one user password and return a temporary credential",
)
def reset_user_password(
    user_id: int,
    service: UsersService = Depends(get_users_service),
    current_user: User = Depends(get_current_super_admin),
) -> UserPasswordResetResponse:
    try:
        user, temporary_password = service.reset_user_password(
            user_id,
            current_admin=current_user,
        )
    except (UsersConflictError, UsersNotFoundError, UsersValidationError) as exc:
        raise_users_http_error(exc)

    return UserPasswordResetResponse(
        detail="Temporary password generated successfully.",
        temporary_password=temporary_password,
        must_change_password=user.must_change_password,
        user=_to_user_response(service, user),
    )


@router.get(
    "/{user_id}/effective-permissions",
    response_model=UserEffectivePermissionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve effective permissions for one user account",
)
def get_user_effective_permissions(
    user_id: int,
    service: UsersService = Depends(get_users_service),
    _current_user: User = Depends(get_current_super_admin),
) -> UserEffectivePermissionsResponse:
    try:
        snapshot = service.get_effective_permissions_snapshot(user_id)
    except UsersNotFoundError as exc:
        raise_users_http_error(exc)

    return UserEffectivePermissionsResponse.model_validate(snapshot)
