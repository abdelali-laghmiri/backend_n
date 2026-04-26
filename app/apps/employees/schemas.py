from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_required_string(value: str) -> str:
    """Normalize required employee strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional employee strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def normalize_email(value: str) -> str:
    """Normalize and minimally validate email fields."""

    normalized_value = normalize_required_string(value).lower()
    if "@" not in normalized_value:
        raise ValueError("Email must be a valid email address.")

    return normalized_value


class EmployeeCreateRequest(BaseModel):
    """Request schema for creating an employee."""

    matricule: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    image: str | None = Field(default=None, max_length=500)
    hire_date: date
    contract_type: Literal["INTERNAL", "EXTERNAL"] = Field(default="INTERNAL")
    external_company_name: str | None = Field(default=None, max_length=255)
    available_leave_balance_days: int = Field(default=0, ge=0)
    department_id: int | None = Field(default=None, ge=1)
    team_id: int | None = Field(default=None, ge=1)
    job_title_id: int = Field(ge=1)

    @field_validator("matricule")
    @classmethod
    def validate_matricule(cls, value: str) -> str:
        return normalize_required_string(value).upper()

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name_fields(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("phone", "image", "external_company_name")
    @classmethod
    def validate_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @model_validator(mode="after")
    def validate_external_company_for_external_contract(self) -> "EmployeeCreateRequest":
        if self.contract_type == "EXTERNAL":
            if not self.external_company_name or not self.external_company_name.strip():
                raise ValueError(
                    "External company name is required when contract type is EXTERNAL."
                )
            self.external_company_name = self.external_company_name.strip()
        else:
            self.external_company_name = None
        return self


class EmployeeUpdateRequest(BaseModel):
    """Request schema for updating an employee."""

    matricule: str | None = Field(default=None, min_length=1, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    image: str | None = Field(default=None, max_length=500)
    hire_date: date | None = None
    contract_type: Literal["INTERNAL", "EXTERNAL"] | None = None
    external_company_name: str | None = Field(default=None, max_length=255)
    available_leave_balance_days: int | None = Field(default=None, ge=0)
    department_id: int | None = Field(default=None, ge=1)
    team_id: int | None = Field(default=None, ge=1)
    job_title_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @field_validator("matricule")
    @classmethod
    def validate_matricule(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).upper()

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_email(value)

    @field_validator("phone", "image", "external_company_name")
    @classmethod
    def validate_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @model_validator(mode="after")
    def validate_external_company_for_external_contract(self) -> "EmployeeUpdateRequest":
        if self.contract_type == "EXTERNAL":
            if not self.external_company_name or not self.external_company_name.strip():
                raise ValueError(
                    "External company name is required when contract type is EXTERNAL."
                )
            self.external_company_name = self.external_company_name.strip()
        elif self.contract_type == "INTERNAL":
            self.external_company_name = None
        return self


class EmployeeResponse(BaseModel):
    """Response schema for employee records."""

    id: int
    user_id: int
    matricule: str
    first_name: str
    last_name: str
    email: str
    phone: str | None
    image: str | None
    hire_date: date
    contract_type: str
    external_company_name: str | None
    available_leave_balance_days: int
    department_id: int | None
    team_id: int | None
    job_title_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeAccountBootstrapResponse(BaseModel):
    """Response schema for the generated linked login account."""

    user_id: int
    matricule: str
    email: str
    temporary_password: str
    must_change_password: bool
    is_active: bool


class EmployeeCreateResponse(BaseModel):
    """Response schema for a newly created employee and linked account."""

    employee: EmployeeResponse
    account: EmployeeAccountBootstrapResponse
