from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.shared.responses import ModuleStatusResponse


def normalize_required_string(value: str) -> str:
    """Normalize required performance strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional performance strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


class PerformanceStatusResponse(ModuleStatusResponse):
    """Response schema for the performance module status endpoint."""

    module: Literal["performance"] = "performance"


class TeamObjectiveCreateRequest(BaseModel):
    """Request schema for creating a team objective."""

    team_id: int = Field(ge=1)
    objective_value: float = Field(gt=0)
    objective_type: str | None = Field(default=None, max_length=50)
    is_active: bool = True

    @field_validator("objective_type")
    @classmethod
    def validate_objective_type(cls, value: str | None) -> str | None:
        normalized_value = normalize_optional_string(value)
        if normalized_value is None:
            return None

        return normalized_value.lower()


class TeamObjectiveUpdateRequest(BaseModel):
    """Request schema for updating a team objective."""

    objective_value: float | None = Field(default=None, gt=0)
    objective_type: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @field_validator("objective_type")
    @classmethod
    def validate_objective_type(cls, value: str | None) -> str | None:
        normalized_value = normalize_optional_string(value)
        if normalized_value is None:
            return None

        return normalized_value.lower()


class TeamObjectiveResponse(BaseModel):
    """Response schema for team objective records."""

    id: int
    team_id: int
    team_code: str
    team_name: str
    objective_value: float
    objective_type: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeamDailyPerformanceCreateRequest(BaseModel):
    """Request schema for submitting a daily team achieved value."""

    team_id: int = Field(ge=1)
    performance_date: date
    achieved_value: float = Field(ge=0)


class TeamDailyPerformanceResponse(BaseModel):
    """Response schema for team daily performance records."""

    id: int
    team_id: int
    team_code: str
    team_name: str
    performance_date: date
    objective_value: float
    achieved_value: float
    performance_percentage: float
    created_by_user_id: int
    created_by_matricule: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
