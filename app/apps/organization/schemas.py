from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_required_string(value: str) -> str:
    """Normalize required string values used by organization requests."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional string values used by organization requests."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


class DepartmentBaseSchema(BaseModel):
    """Shared department schema fields."""

    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    manager_user_id: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class DepartmentCreateRequest(DepartmentBaseSchema):
    """Request schema for creating a department."""


class DepartmentUpdateRequest(BaseModel):
    """Request schema for updating a department."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    manager_user_id: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class DepartmentResponse(BaseModel):
    """Response schema for department records."""

    id: int
    name: str
    code: str
    description: str | None
    manager_user_id: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamBaseSchema(BaseModel):
    """Shared team schema fields."""

    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    department_id: int = Field(ge=1)
    leader_user_id: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class TeamCreateRequest(TeamBaseSchema):
    """Request schema for creating a team."""


class TeamUpdateRequest(BaseModel):
    """Request schema for updating a team."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    department_id: int | None = Field(default=None, ge=1)
    leader_user_id: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class TeamResponse(BaseModel):
    """Response schema for team records."""

    id: int
    name: str
    code: str
    description: str | None
    department_id: int
    leader_user_id: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobTitleBaseSchema(BaseModel):
    """Shared job title schema fields."""

    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    hierarchical_level: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class JobTitleCreateRequest(JobTitleBaseSchema):
    """Request schema for creating a job title."""


class JobTitleUpdateRequest(BaseModel):
    """Request schema for updating a job title."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    hierarchical_level: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).upper()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class JobTitleResponse(BaseModel):
    """Response schema for job title records."""

    id: int
    name: str
    code: str
    description: str | None
    hierarchical_level: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
