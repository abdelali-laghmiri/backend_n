from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.organization.dependencies import get_organization_service
from app.apps.organization.schemas import (
    CompanyHierarchyResponse,
    CurrentUserHierarchyResponse,
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
    JobTitleCreateRequest,
    JobTitleResponse,
    JobTitleUpdateRequest,
    TeamCreateRequest,
    TeamResponse,
    TeamUpdateRequest,
)
from app.apps.permissions.dependencies import require_permission
from app.apps.organization.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationService,
    OrganizationValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/organization", tags=["Organization"])


def raise_organization_http_error(exc: Exception) -> None:
    """Map organization service errors to HTTP exceptions."""

    if isinstance(exc, OrganizationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, OrganizationValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, OrganizationConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department",
)
def create_department(
    payload: DepartmentCreateRequest,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.create")),
) -> DepartmentResponse:
    try:
        department = service.create_department(payload)
    except (OrganizationConflictError, OrganizationValidationError) as exc:
        raise_organization_http_error(exc)

    return DepartmentResponse.model_validate(department)


@router.get(
    "/hierarchy/me",
    response_model=CurrentUserHierarchyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the current user's organization hierarchy",
)
def get_current_user_hierarchy(
    service: OrganizationService = Depends(get_organization_service),
    current_user: User = Depends(require_permission("organization.read_hierarchy")),
) -> CurrentUserHierarchyResponse:
    return CurrentUserHierarchyResponse.model_validate(
        service.get_current_user_hierarchy(current_user)
    )


@router.get(
    "/hierarchy/company",
    response_model=CompanyHierarchyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the full company organigram",
)
def get_company_hierarchy(
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.company_hierarchy")),
) -> CompanyHierarchyResponse:
    return CompanyHierarchyResponse.model_validate(service.get_company_hierarchy())


@router.get(
    "/departments",
    response_model=list[DepartmentResponse],
    status_code=status.HTTP_200_OK,
    summary="List departments",
)
def list_departments(
    include_inactive: bool = Query(default=False),
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.read")),
) -> list[DepartmentResponse]:
    departments = service.list_departments(include_inactive=include_inactive)
    return [DepartmentResponse.model_validate(item) for item in departments]


@router.get(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a department by id",
)
def get_department(
    department_id: int,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.read")),
) -> DepartmentResponse:
    try:
        department = service.get_department(department_id)
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)

    return DepartmentResponse.model_validate(department)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a department",
)
def update_department(
    department_id: int,
    payload: DepartmentUpdateRequest,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.update")),
) -> DepartmentResponse:
    try:
        department = service.update_department(department_id, payload)
    except (
        OrganizationConflictError,
        OrganizationNotFoundError,
        OrganizationValidationError,
    ) as exc:
        raise_organization_http_error(exc)

    return DepartmentResponse.model_validate(department)


@router.post(
    "/departments/{department_id}/deactivate",
    response_model=DepartmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate a department",
)
def deactivate_department(
    department_id: int,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.deactivate")),
) -> DepartmentResponse:
    try:
        department = service.deactivate_department(department_id)
    except (OrganizationConflictError, OrganizationNotFoundError) as exc:
        raise_organization_http_error(exc)

    return DepartmentResponse.model_validate(department)


@router.post(
    "/teams",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team",
)
def create_team(
    payload: TeamCreateRequest,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.create")),
) -> TeamResponse:
    try:
        team = service.create_team(payload)
    except (OrganizationConflictError, OrganizationValidationError) as exc:
        raise_organization_http_error(exc)

    return TeamResponse.model_validate(team)


@router.get(
    "/teams",
    response_model=list[TeamResponse],
    status_code=status.HTTP_200_OK,
    summary="List teams",
)
def list_teams(
    include_inactive: bool = Query(default=False),
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.read")),
) -> list[TeamResponse]:
    teams = service.list_teams(include_inactive=include_inactive)
    return [TeamResponse.model_validate(item) for item in teams]


@router.get(
    "/teams/{team_id}",
    response_model=TeamResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a team by id",
)
def get_team(
    team_id: int,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.read")),
) -> TeamResponse:
    try:
        team = service.get_team(team_id)
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)

    return TeamResponse.model_validate(team)


@router.patch(
    "/teams/{team_id}",
    response_model=TeamResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a team",
)
def update_team(
    team_id: int,
    payload: TeamUpdateRequest,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.update")),
) -> TeamResponse:
    try:
        team = service.update_team(team_id, payload)
    except (
        OrganizationConflictError,
        OrganizationNotFoundError,
        OrganizationValidationError,
    ) as exc:
        raise_organization_http_error(exc)

    return TeamResponse.model_validate(team)


@router.post(
    "/teams/{team_id}/deactivate",
    response_model=TeamResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate a team",
)
def deactivate_team(
    team_id: int,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.deactivate")),
) -> TeamResponse:
    try:
        team = service.deactivate_team(team_id)
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)

    return TeamResponse.model_validate(team)


@router.post(
    "/job-titles",
    response_model=JobTitleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job title",
)
def create_job_title(
    payload: JobTitleCreateRequest,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.create")),
) -> JobTitleResponse:
    try:
        job_title = service.create_job_title(payload)
    except OrganizationConflictError as exc:
        raise_organization_http_error(exc)

    return JobTitleResponse.model_validate(job_title)


@router.get(
    "/job-titles",
    response_model=list[JobTitleResponse],
    status_code=status.HTTP_200_OK,
    summary="List job titles",
)
def list_job_titles(
    include_inactive: bool = Query(default=False),
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.read")),
) -> list[JobTitleResponse]:
    job_titles = service.list_job_titles(include_inactive=include_inactive)
    return [JobTitleResponse.model_validate(item) for item in job_titles]


@router.get(
    "/job-titles/{job_title_id}",
    response_model=JobTitleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a job title by id",
)
def get_job_title(
    job_title_id: int,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.read")),
) -> JobTitleResponse:
    try:
        job_title = service.get_job_title(job_title_id)
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)

    return JobTitleResponse.model_validate(job_title)


@router.patch(
    "/job-titles/{job_title_id}",
    response_model=JobTitleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a job title",
)
def update_job_title(
    job_title_id: int,
    payload: JobTitleUpdateRequest,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.update")),
) -> JobTitleResponse:
    try:
        job_title = service.update_job_title(job_title_id, payload)
    except (OrganizationConflictError, OrganizationNotFoundError) as exc:
        raise_organization_http_error(exc)

    return JobTitleResponse.model_validate(job_title)


@router.post(
    "/job-titles/{job_title_id}/deactivate",
    response_model=JobTitleResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate a job title",
)
def deactivate_job_title(
    job_title_id: int,
    service: OrganizationService = Depends(get_organization_service),
    _current_user: User = Depends(require_permission("organization.deactivate")),
) -> JobTitleResponse:
    try:
        job_title = service.deactivate_job_title(job_title_id)
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)

    return JobTitleResponse.model_validate(job_title)
