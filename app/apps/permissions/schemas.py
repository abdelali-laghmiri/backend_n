from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

PERMISSION_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MODULE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def normalize_required_string(value: str) -> str:
    """Normalize required permission strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional permission strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


class PermissionCreateRequest(BaseModel):
    """Request schema for creating a permission."""

    code: str = Field(min_length=3, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    module: str = Field(min_length=1, max_length=50)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized_value = normalize_required_string(value).lower()
        if not PERMISSION_CODE_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Permission code must look like module.action using lowercase letters."
            )

        return normalized_value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @field_validator("module")
    @classmethod
    def validate_module(cls, value: str) -> str:
        normalized_value = normalize_required_string(value).lower()
        if not MODULE_PATTERN.fullmatch(normalized_value):
            raise ValueError("Module must use lowercase letters, digits, or underscores.")

        return normalized_value


class PermissionUpdateRequest(BaseModel):
    """Request schema for updating a permission."""

    code: str | None = Field(default=None, min_length=3, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    module: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized_value = normalize_required_string(value).lower()
        if not PERMISSION_CODE_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Permission code must look like module.action using lowercase letters."
            )

        return normalized_value

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

    @field_validator("module")
    @classmethod
    def validate_module(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized_value = normalize_required_string(value).lower()
        if not MODULE_PATTERN.fullmatch(normalized_value):
            raise ValueError("Module must use lowercase letters, digits, or underscores.")

        return normalized_value


class PermissionResponse(BaseModel):
    """Response schema for permission catalog records."""

    id: int
    code: str
    name: str
    description: str | None
    module: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobTitlePermissionAssignmentRequest(BaseModel):
    """Request schema for replacing a job title permission set."""

    permission_ids: list[int] = Field(default_factory=list)

    @field_validator("permission_ids")
    @classmethod
    def validate_permission_ids(cls, value: list[int]) -> list[int]:
        seen_ids: set[int] = set()
        normalized_ids: list[int] = []
        for permission_id in value:
            if permission_id < 1:
                raise ValueError("Permission ids must be positive integers.")
            if permission_id in seen_ids:
                continue

            seen_ids.add(permission_id)
            normalized_ids.append(permission_id)

        return normalized_ids


class JobTitlePermissionAssignmentResponse(BaseModel):
    """Response schema for the permissions assigned to a job title."""

    job_title_id: int
    job_title_name: str
    job_title_code: str
    permissions: list[PermissionResponse]


class EffectivePermissionResponse(BaseModel):
    """Resolved permissions for an authenticated user."""

    has_full_access: bool
    permissions: list[str]
