from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.apps.permissions.dependencies import get_permissions_service, require_permission
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
from app.core.config import get_settings
from app.core.dependencies import get_db_session

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
    _current_user: User = Depends(require_permission("permissions.create")),
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
    _current_user: User = Depends(require_permission("permissions.read")),
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
    _current_user: User = Depends(require_permission("permissions.read")),
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
    _current_user: User = Depends(require_permission("permissions.update")),
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
    _current_user: User = Depends(require_permission("permissions.assign")),
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
    _current_user: User = Depends(require_permission("permissions.read")),
) -> JobTitlePermissionAssignmentResponse:
    try:
        return service.get_job_title_permission_assignment(job_title_id)
    except PermissionsNotFoundError as exc:
        raise_permissions_http_error(exc)


@router.post(
    "/admin/ensure-canonical",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Ensure canonical permissions exist (admin, works anytime)",
)
def ensure_canonical_permissions(
    db: DBSession = Depends(get_db_session),
    _current_user: User = Depends(require_permission("permissions.create")),
) -> dict:
    """Create any missing canonical permissions from the source of truth."""
    from app.apps.setup.service import SetupService

    service = SetupService(db=db, settings=get_settings())
    job_titles_summary = service.ensure_canonical_job_titles()
    permissions_summary = service.ensure_permission_catalog(
        enforce_wizard_writable=False,
        update_wizard_state=False,
    )
    return {
        "message": "Ensured canonical job titles and permissions",
        "job_titles": len(job_titles_summary.get("job_titles", [])),
        "permissions": len(permissions_summary.get("permissions", [])),
        "expected_permissions": permissions_summary.get("expected_count", 0),
    }


@router.post(
    "/admin/ensure-job-title-permissions",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Ensure canonical job-title assignments (admin, works anytime)",
)
def ensure_canonical_job_title_permissions(
    db: DBSession = Depends(get_db_session),
    _current_user: User = Depends(require_permission("permissions.assign")),
) -> dict:
    """Apply canonical job-title permission assignments (overwrites existing)."""
    from app.apps.setup.service import SetupService

    service = SetupService(db=db, settings=get_settings())
    service.ensure_canonical_job_titles()
    service.ensure_permission_catalog(
        enforce_wizard_writable=False,
        update_wizard_state=False,
    )
    assignment_summary = service.ensure_job_title_permission_assignments(
        enforce_wizard_writable=False,
        update_wizard_state=False,
    )
    assignment_counts = {
        code: len(items)
        for code, items in assignment_summary.get("assignments", {}).items()
    }
    return {
        "message": "Applied canonical assignments for all required setup job titles",
        "assignment_counts": assignment_counts,
    }
