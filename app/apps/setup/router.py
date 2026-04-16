from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.apps.auth.dependencies import get_current_super_admin
from app.apps.employees.schemas import EmployeeResponse
from app.apps.organization.schemas import DepartmentResponse, JobTitleResponse, TeamResponse
from app.apps.permissions.schemas import PermissionResponse
from app.apps.setup.dependencies import get_setup_service
from app.apps.setup.schemas import (
    BootstrapSuperAdminResponse,
    SetupInitializeResponse,
    SetupStatusResponse,
    SetupWizardFinalizeResponse,
    SetupWizardJobTitlePermissionAssignmentResponse,
    SetupWizardJobTitlePermissionsSummaryResponse,
    SetupWizardJobTitlesStepRequest,
    SetupWizardJobTitlesSummaryResponse,
    SetupWizardLinkedUserResponse,
    SetupWizardOperationalUserSummaryResponse,
    SetupWizardOperationalUsersStepRequest,
    SetupWizardOperationalUsersSummaryResponse,
    SetupWizardOrganizationStepRequest,
    SetupWizardOrganizationSummaryResponse,
    SetupWizardPermissionsSummaryResponse,
    SetupWizardReadinessSummaryResponse,
    SetupWizardReviewSummaryResponse,
    SetupWizardStateResponse,
)
from app.apps.setup.service import (
    SetupAlreadyInitializedError,
    SetupConfigurationError,
    SetupInitializationError,
    SetupService,
    SetupValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/setup", tags=["Setup"])


def raise_setup_http_error(exc: Exception) -> None:
    """Map setup service errors to HTTP exceptions."""

    if isinstance(exc, SetupValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, SetupAlreadyInitializedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if isinstance(exc, SetupConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if isinstance(exc, SetupInitializationError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    raise exc


def _build_readiness_summary(service: SetupService) -> SetupWizardReadinessSummaryResponse:
    readiness = service.get_readiness_summary()
    super_admin = readiness.get("super_admin")
    return SetupWizardReadinessSummaryResponse(
        initialized=bool(readiness["initialized"]),
        bootstrap_super_admin_exists=bool(readiness["bootstrap_super_admin_exists"]),
        setup_wizard_required=bool(readiness["setup_wizard_required"]),
        detail=str(readiness["detail"]),
        initialized_at=readiness.get("initialized_at"),
        database_ready=bool(readiness["database_ready"]),
        migrations_ready=bool(readiness["migrations_ready"]),
        super_admin=(
            BootstrapSuperAdminResponse.model_validate(super_admin)
            if super_admin is not None
            else None
        ),
    )


def _build_organization_summary(service: SetupService) -> SetupWizardOrganizationSummaryResponse:
    organization_summary = service.get_organization_summary()
    department = organization_summary.get("department")
    teams = organization_summary.get("teams", [])
    return SetupWizardOrganizationSummaryResponse(
        department=(
            DepartmentResponse.model_validate(department)
            if department is not None
            else None
        ),
        teams=[TeamResponse.model_validate(team) for team in teams],
    )


def _build_job_titles_summary(service: SetupService) -> SetupWizardJobTitlesSummaryResponse:
    job_titles_summary = service.get_job_titles_summary()
    return SetupWizardJobTitlesSummaryResponse(
        job_titles=[
            JobTitleResponse.model_validate(job_title)
            for job_title in job_titles_summary.get("job_titles", [])
        ]
    )


def _build_permissions_summary(service: SetupService) -> SetupWizardPermissionsSummaryResponse:
    permissions_summary = service.get_permissions_summary()
    return SetupWizardPermissionsSummaryResponse(
        expected_count=int(permissions_summary.get("expected_count", 0) or 0),
        permissions=[
            PermissionResponse.model_validate(permission)
            for permission in permissions_summary.get("permissions", [])
        ],
    )


def _build_job_title_permissions_summary(
    service: SetupService,
) -> SetupWizardJobTitlePermissionsSummaryResponse:
    assignment_summary = service.get_job_title_permission_summary()
    assignments = assignment_summary.get("assignments", {})
    return SetupWizardJobTitlePermissionsSummaryResponse(
        assignments=[
            SetupWizardJobTitlePermissionAssignmentResponse(
                job_title_code=job_title_code,
                permissions=[
                    PermissionResponse.model_validate(permission)
                    for permission in permissions
                ],
            )
            for job_title_code, permissions in sorted(assignments.items())
        ]
    )


def _build_operational_users_summary(
    service: SetupService,
) -> SetupWizardOperationalUsersSummaryResponse:
    operational_users_summary = service.get_operational_users_summary()
    employees = operational_users_summary.get("employees", [])

    return SetupWizardOperationalUsersSummaryResponse(
        employees=[
            SetupWizardOperationalUserSummaryResponse(
                role_label=str(entry["role_label"]),
                employee=EmployeeResponse.model_validate(entry["employee"]),
                user=(
                    SetupWizardLinkedUserResponse.model_validate(entry["user"])
                    if entry.get("user") is not None
                    else None
                ),
                job_title=(
                    JobTitleResponse.model_validate(entry["job_title"])
                    if entry.get("job_title") is not None
                    else None
                ),
                department=(
                    DepartmentResponse.model_validate(entry["department"])
                    if entry.get("department") is not None
                    else None
                ),
                team=(
                    TeamResponse.model_validate(entry["team"])
                    if entry.get("team") is not None
                    else None
                ),
            )
            for entry in employees
        ]
    )


def _build_review_summary(service: SetupService) -> SetupWizardReviewSummaryResponse:
    review_summary = service.get_review_summary()
    return SetupWizardReviewSummaryResponse(
        organization=_build_organization_summary(service),
        job_titles=_build_job_titles_summary(service),
        permissions=_build_permissions_summary(service),
        job_title_permissions=_build_job_title_permissions_summary(service),
        operational_users=_build_operational_users_summary(service),
        missing_items=list(review_summary.get("missing_items", [])),
        is_ready=bool(review_summary.get("is_ready", False)),
    )


def _build_wizard_state(service: SetupService) -> SetupWizardStateResponse:
    status_snapshot = service.get_status()
    wizard_state = service.get_wizard_state()

    return SetupWizardStateResponse(
        initialized=bool(status_snapshot["initialized"]),
        bootstrap_super_admin_exists=bool(status_snapshot["bootstrap_super_admin_exists"]),
        setup_wizard_required=bool(status_snapshot["setup_wizard_required"]),
        detail=str(status_snapshot["detail"]),
        initialized_at=status_snapshot.get("initialized_at"),
        last_completed_step=int(wizard_state.get("last_completed_step", 0) or 0),
        next_step=service.get_next_wizard_step_number(),
        readiness=_build_readiness_summary(service),
        organization=_build_organization_summary(service),
        job_titles=_build_job_titles_summary(service),
        permissions=_build_permissions_summary(service),
        job_title_permissions=_build_job_title_permissions_summary(service),
        operational_users=_build_operational_users_summary(service),
        review=_build_review_summary(service),
    )


def _build_job_titles_payload(payload: SetupWizardJobTitlesStepRequest) -> dict[str, object]:
    mapping = {
        "rh_manager": payload.rh_manager,
        "department_manager": payload.department_manager,
        "team_leader": payload.team_leader,
        "employee": payload.employee,
    }
    result: dict[str, object] = {}

    for key, value in mapping.items():
        if value.name is not None:
            result[f"{key}_name"] = value.name
        if value.description is not None:
            result[f"{key}_description"] = value.description
        if value.hierarchical_level is not None:
            result[f"{key}_hierarchical_level"] = value.hierarchical_level

    return result


@router.get(
    "/status",
    response_model=SetupStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check whether the system has already been initialized",
)
def get_setup_status(
    service: SetupService = Depends(get_setup_service),
) -> SetupStatusResponse:
    return SetupStatusResponse.model_validate(service.get_status())


@router.post(
    "/initialize",
    response_model=SetupInitializeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize the system and create the first super admin",
)
def initialize_system(
    service: SetupService = Depends(get_setup_service),
) -> SetupInitializeResponse:
    try:
        super_admin = service.initialize_system()
    except (
        SetupAlreadyInitializedError,
        SetupConfigurationError,
        SetupInitializationError,
    ) as exc:
        raise_setup_http_error(exc)

    return SetupInitializeResponse(
        initialized=False,
        bootstrap_super_admin_exists=True,
        setup_wizard_required=True,
        detail=(
            "Bootstrap super admin created successfully. "
            "Continue setup with /api/v1/setup/wizard/state."
        ),
        super_admin=BootstrapSuperAdminResponse.model_validate(super_admin),
    )


@router.get(
    "/wizard/state",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current setup wizard state and step summaries",
)
def get_setup_wizard_state(
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    return _build_wizard_state(service)


@router.post(
    "/wizard/steps/1/readiness",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Acknowledge setup readiness step",
)
def save_setup_readiness_step(
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    try:
        service.save_readiness_step()
    except (SetupAlreadyInitializedError, SetupValidationError) as exc:
        raise_setup_http_error(exc)

    return _build_wizard_state(service)


@router.put(
    "/wizard/steps/2/organization",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Save setup organization step",
)
def save_setup_organization_step(
    payload: SetupWizardOrganizationStepRequest,
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    try:
        service.save_organization_step(payload.model_dump())
    except (SetupAlreadyInitializedError, SetupValidationError) as exc:
        raise_setup_http_error(exc)

    return _build_wizard_state(service)


@router.put(
    "/wizard/steps/3/job-titles",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Save setup job-title step",
)
def save_setup_job_titles_step(
    payload: SetupWizardJobTitlesStepRequest,
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    try:
        service.save_job_titles_step(_build_job_titles_payload(payload))
    except (SetupAlreadyInitializedError, SetupValidationError) as exc:
        raise_setup_http_error(exc)

    return _build_wizard_state(service)


@router.post(
    "/wizard/steps/4/permissions",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Create or refresh default permission catalog",
)
def save_setup_permissions_step(
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    try:
        service.ensure_permission_catalog()
    except (SetupAlreadyInitializedError, SetupValidationError) as exc:
        raise_setup_http_error(exc)

    return _build_wizard_state(service)


@router.post(
    "/wizard/steps/5/job-title-permissions",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply default job-title permission assignments",
)
def save_setup_job_title_permissions_step(
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    try:
        service.ensure_job_title_permission_assignments()
    except (SetupAlreadyInitializedError, SetupValidationError) as exc:
        raise_setup_http_error(exc)

    return _build_wizard_state(service)


@router.put(
    "/wizard/steps/6/operational-users",
    response_model=SetupWizardStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Save setup operational users step",
)
def save_setup_operational_users_step(
    payload: SetupWizardOperationalUsersStepRequest,
    service: SetupService = Depends(get_setup_service),
    _current_user: User = Depends(get_current_super_admin),
) -> SetupWizardStateResponse:
    try:
        service.save_operational_users_step(payload.model_dump())
    except (
        SetupAlreadyInitializedError,
        SetupInitializationError,
        SetupValidationError,
    ) as exc:
        raise_setup_http_error(exc)

    return _build_wizard_state(service)


@router.post(
    "/wizard/finalize",
    response_model=SetupWizardFinalizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Finalize and lock setup installation",
)
def finalize_setup_installation(
    service: SetupService = Depends(get_setup_service),
    current_user: User = Depends(get_current_super_admin),
) -> SetupWizardFinalizeResponse:
    try:
        service.complete_installation(current_user)
    except (
        SetupAlreadyInitializedError,
        SetupInitializationError,
        SetupValidationError,
    ) as exc:
        raise_setup_http_error(exc)

    return SetupWizardFinalizeResponse(
        detail="Installation finalized successfully.",
        state=_build_wizard_state(service),
    )
