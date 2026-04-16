from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_required_string(value: str) -> str:
    """Normalize required user strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional user strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def normalize_email(value: str) -> str:
    """Normalize and minimally validate email values."""

    normalized_value = normalize_required_string(value).lower()
    if "@" not in normalized_value:
        raise ValueError("Email must be a valid email address.")

    return normalized_value


class UserLinkedEmployeeSummaryResponse(BaseModel):
    """Linked employee metadata for one user account."""

    employee_id: int
    hire_date: date
    department_id: int | None
    team_id: int | None
    job_title_id: int
    is_active: bool


class UserResponse(BaseModel):
    """Response schema for an internal user account."""

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
    linked_employee: UserLinkedEmployeeSummaryResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class UserCreateRequest(BaseModel):
    """Request schema for creating an internal user account."""

    matricule: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    is_super_admin: bool = False
    is_active: bool = True
    must_change_password: bool = True

    @field_validator("matricule")
    @classmethod
    def validate_matricule(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator("first_name", "last_name", "password")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class UserUpdateRequest(BaseModel):
    """Request schema for updating an internal user account."""

    matricule: str | None = Field(default=None, min_length=1, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=255)
    is_super_admin: bool | None = None
    is_active: bool | None = None
    must_change_password: bool | None = None
    department_id: int | None = Field(default=None, ge=1)
    team_id: int | None = Field(default=None, ge=1)
    job_title_id: int | None = Field(default=None, ge=1)

    @field_validator("matricule")
    @classmethod
    def validate_optional_matricule(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).upper()

    @field_validator("first_name", "last_name", "password")
    @classmethod
    def validate_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value)

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_email(value)


class UserActivateResponse(BaseModel):
    """Response schema for activate/deactivate operations."""

    detail: str
    user: UserResponse


class UserPasswordResetResponse(BaseModel):
    """Response schema for one-time user password reset generation."""

    detail: str
    temporary_password: str
    must_change_password: bool
    user: UserResponse


class UserEffectivePermissionsResponse(BaseModel):
    """Resolved permissions for a target user account."""

    user_id: int
    has_full_access: bool
    permissions: list[str]
    linked_employee_job_title_id: int | None = None
