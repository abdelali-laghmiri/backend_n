from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.auth.dependencies import get_current_super_admin
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.permissions.schemas import (
    JobTitlePermissionAssignmentRequest,
    JobTitlePermissionAssignmentResponse,
    PermissionCreateRequest,
    PermissionResponse,
    PermissionUpdateRequest,
)
from app.apps.permissions.service import (
    PermissionsConflictError,
    PermissionsNotFoundError,
    PermissionsService,
    PermissionsValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/permissions", tags=["Permissions"])


def raise_permissions_http_error(exc: Exception) -> None:
    """Map permission service errors to HTTP exceptions."""

    if isinstance(exc, PermissionsNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, PermissionsValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, PermissionsConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a permission catalog entry",
)
def create_permission(
    payload: PermissionCreateRequest,
    service: PermissionsService = Depends(get_permissions_service),
    _current_user: User = Depends(get_current_super_admin),
) -> PermissionResponse:
    try:
        permission = service.create_permission(payload)
    except (PermissionsConflictError, PermissionsValidationError) as exc:
        raise_permissions_http_error(exc)

    return PermissionResponse.model_validate(permission)


@router.get(
    "",
    response_model=list[PermissionResponse],
    status_code=status.HTTP_200_OK,
    summary="List permission catalog entries",
)
def list_permissions(
    include_inactive: bool = Query(default=False),
    module: str | None = Query(default=None),
    service: PermissionsService = Depends(get_permissions_service),
    _current_user: User = Depends(get_current_super_admin),
) -> list[PermissionResponse]:
    permissions = service.list_permissions(
        include_inactive=include_inactive,
        module=module,
    )
    return [PermissionResponse.model_validate(item) for item in permissions]


@router.get(
    "/{permission_id}",
    response_model=PermissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a permission by id",
)
def get_permission(
    permission_id: int,
    service: PermissionsService = Depends(get_permissions_service),
    _current_user: User = Depends(get_current_super_admin),
) -> PermissionResponse:
    try:
        permission = service.get_permission(permission_id)
    except PermissionsNotFoundError as exc:
        raise_permissions_http_error(exc)

    return PermissionResponse.model_validate(permission)


@router.patch(
    "/{permission_id}",
    response_model=PermissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a permission catalog entry",
)
def update_permission(
    permission_id: int,
    payload: PermissionUpdateRequest,
    service: PermissionsService = Depends(get_permissions_service),
    _current_user: User = Depends(get_current_super_admin),
) -> PermissionResponse:
    try:
        permission = service.update_permission(permission_id, payload)
    except (
        PermissionsConflictError,
        PermissionsNotFoundError,
        PermissionsValidationError,
    ) as exc:
        raise_permissions_http_error(exc)

    return PermissionResponse.model_validate(permission)


@router.put(
    "/job-titles/{job_title_id}",
    response_model=JobTitlePermissionAssignmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Replace the permissions assigned to a job title",
)
def assign_permissions_to_job_title(
    job_title_id: int,
    payload: JobTitlePermissionAssignmentRequest,
    service: PermissionsService = Depends(get_permissions_service),
    _current_user: User = Depends(get_current_super_admin),
) -> JobTitlePermissionAssignmentResponse:
    try:
        return service.assign_permissions_to_job_title(job_title_id, payload)
    except (
        PermissionsConflictError,
        PermissionsNotFoundError,
        PermissionsValidationError,
    ) as exc:
        raise_permissions_http_error(exc)


@router.get(
    "/job-titles/{job_title_id}",
    response_model=JobTitlePermissionAssignmentResponse,
    status_code=status.HTTP_200_OK,
    summary="View the permissions assigned to a job title",
)
def get_job_title_permissions(
    job_title_id: int,
    service: PermissionsService = Depends(get_permissions_service),
    _current_user: User = Depends(get_current_super_admin),
) -> JobTitlePermissionAssignmentResponse:
    try:
        return service.get_job_title_permission_assignment(job_title_id)
    except PermissionsNotFoundError as exc:
        raise_permissions_http_error(exc)
