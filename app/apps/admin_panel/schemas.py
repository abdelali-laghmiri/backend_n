from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def normalize_required_string(value: str) -> str:
    """Normalize required admin form strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional admin form strings."""

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


class AdminUserCreateRequest(BaseModel):
    """Request schema for creating an internal user account."""

    matricule: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)
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


class AdminUserUpdateRequest(BaseModel):
    """Request schema for updating an internal user account."""

    matricule: str | None = Field(default=None, min_length=1, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    is_super_admin: bool | None = None
    is_active: bool | None = None
    must_change_password: bool | None = None

    @field_validator("matricule")
    @classmethod
    def validate_matricule(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).upper()

    @field_validator("first_name", "last_name")
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

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)
