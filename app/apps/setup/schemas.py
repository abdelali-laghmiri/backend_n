from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.apps.employees.schemas import EmployeeResponse
from app.apps.organization.schemas import DepartmentResponse, JobTitleResponse, TeamResponse
from app.apps.permissions.schemas import PermissionResponse


def normalize_required_string(value: str) -> str:
    """Normalize required setup strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional setup strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


class SetupStatusResponse(BaseModel):
    """Response schema for setup initialization status."""

    initialized: bool
    bootstrap_super_admin_exists: bool
    setup_wizard_required: bool
    detail: str
    initialized_at: datetime | None = None


class BootstrapSuperAdminResponse(BaseModel):
    """Response schema for the bootstrap super admin account."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    email: str
    is_super_admin: bool
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SetupInitializeResponse(BaseModel):
    """Response schema for bootstrap super admin creation."""

    initialized: bool
    bootstrap_super_admin_exists: bool
    setup_wizard_required: bool
    detail: str
    super_admin: BootstrapSuperAdminResponse


class SetupWizardOrganizationStepRequest(BaseModel):
    """Payload for setup wizard organization step."""

    department_name: str = Field(min_length=1, max_length=120)
    department_code: str = Field(min_length=1, max_length=50)
    department_description: str | None = Field(default=None, max_length=2000)
    team_one_name: str = Field(min_length=1, max_length=120)
    team_one_code: str = Field(min_length=1, max_length=50)
    team_one_description: str | None = Field(default=None, max_length=2000)
    team_two_name: str = Field(min_length=1, max_length=120)
    team_two_code: str = Field(min_length=1, max_length=50)
    team_two_description: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "department_name",
        "team_one_name",
        "team_two_name",
    )
    @classmethod
    def validate_name_fields(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator(
        "department_code",
        "team_one_code",
        "team_two_code",
    )
    @classmethod
    def validate_code_fields(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator(
        "department_description",
        "team_one_description",
        "team_two_description",
    )
    @classmethod
    def validate_descriptions(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class SetupWizardJobTitleOverrideRequest(BaseModel):
    """Optional override values for one seeded job title."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    hierarchical_level: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class SetupWizardJobTitlesStepRequest(BaseModel):
    """Payload for setup wizard job-title step."""

    rh_manager: SetupWizardJobTitleOverrideRequest = Field(default_factory=SetupWizardJobTitleOverrideRequest)
    department_manager: SetupWizardJobTitleOverrideRequest = Field(
        default_factory=SetupWizardJobTitleOverrideRequest
    )
    team_leader: SetupWizardJobTitleOverrideRequest = Field(default_factory=SetupWizardJobTitleOverrideRequest)
    employee: SetupWizardJobTitleOverrideRequest = Field(default_factory=SetupWizardJobTitleOverrideRequest)


class SetupWizardOperationalUserRoleRequest(BaseModel):
    """Payload for one operational role account in setup step 6."""

    matricule: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=255)
    hire_date: date
    password: str | None = Field(default=None, min_length=8, max_length=255)

    @field_validator("matricule")
    @classmethod
    def validate_matricule(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_required_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized_value = normalize_required_string(value).lower()
        if "@" not in normalized_value:
            raise ValueError("Email must be a valid email address.")

        return normalized_value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value)


class SetupWizardOperationalUsersStepRequest(BaseModel):
    """Payload for setup wizard operational-users step."""

    rh_manager: SetupWizardOperationalUserRoleRequest
    department_manager: SetupWizardOperationalUserRoleRequest
    team_leader_one: SetupWizardOperationalUserRoleRequest
    team_leader_two: SetupWizardOperationalUserRoleRequest


class SetupWizardReadinessSummaryResponse(BaseModel):
    """Readiness summary returned by wizard step 1."""

    initialized: bool
    bootstrap_super_admin_exists: bool
    setup_wizard_required: bool
    detail: str
    initialized_at: datetime | None = None
    database_ready: bool
    migrations_ready: bool
    super_admin: BootstrapSuperAdminResponse | None = None


class SetupWizardOrganizationSummaryResponse(BaseModel):
    """Organization summary returned by wizard step 2."""

    department: DepartmentResponse | None = None
    teams: list[TeamResponse] = Field(default_factory=list)


class SetupWizardJobTitlesSummaryResponse(BaseModel):
    """Job-title summary returned by wizard step 3."""

    job_titles: list[JobTitleResponse] = Field(default_factory=list)


class SetupWizardPermissionsSummaryResponse(BaseModel):
    """Permission-catalog summary returned by wizard step 4."""

    expected_count: int
    permissions: list[PermissionResponse] = Field(default_factory=list)


class SetupWizardJobTitlePermissionAssignmentResponse(BaseModel):
    """Permission assignment snapshot for one seeded job title."""

    job_title_code: str
    permissions: list[PermissionResponse] = Field(default_factory=list)


class SetupWizardJobTitlePermissionsSummaryResponse(BaseModel):
    """Permission assignment summary returned by wizard step 5."""

    assignments: list[SetupWizardJobTitlePermissionAssignmentResponse] = Field(default_factory=list)


class SetupWizardLinkedUserResponse(BaseModel):
    """Minimal linked user representation for setup operational users summary."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    email: str
    is_super_admin: bool
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SetupWizardOperationalUserSummaryResponse(BaseModel):
    """One operational role summary entry."""

    role_label: str
    employee: EmployeeResponse
    user: SetupWizardLinkedUserResponse | None = None
    job_title: JobTitleResponse | None = None
    department: DepartmentResponse | None = None
    team: TeamResponse | None = None


class SetupWizardOperationalUsersSummaryResponse(BaseModel):
    """Operational-users summary returned by wizard step 6."""

    employees: list[SetupWizardOperationalUserSummaryResponse] = Field(default_factory=list)


class SetupWizardReviewSummaryResponse(BaseModel):
    """Final review summary used before installation finalization."""

    organization: SetupWizardOrganizationSummaryResponse
    job_titles: SetupWizardJobTitlesSummaryResponse
    permissions: SetupWizardPermissionsSummaryResponse
    job_title_permissions: SetupWizardJobTitlePermissionsSummaryResponse
    operational_users: SetupWizardOperationalUsersSummaryResponse
    missing_items: list[str] = Field(default_factory=list)
    is_ready: bool


class SetupWizardStateResponse(BaseModel):
    """Full setup-wizard state snapshot for frontend-driven onboarding."""

    initialized: bool
    bootstrap_super_admin_exists: bool
    setup_wizard_required: bool
    detail: str
    initialized_at: datetime | None = None
    last_completed_step: int
    next_step: int
    readiness: SetupWizardReadinessSummaryResponse
    organization: SetupWizardOrganizationSummaryResponse
    job_titles: SetupWizardJobTitlesSummaryResponse
    permissions: SetupWizardPermissionsSummaryResponse
    job_title_permissions: SetupWizardJobTitlePermissionsSummaryResponse
    operational_users: SetupWizardOperationalUsersSummaryResponse
    review: SetupWizardReviewSummaryResponse


class SetupWizardFinalizeResponse(BaseModel):
    """Response returned when setup installation is finalized."""

    detail: str
    state: SetupWizardStateResponse
