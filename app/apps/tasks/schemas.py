from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.apps.attendance.models import AttendanceStatusEnum
from app.apps.tasks.models import TaskPriorityEnum, TaskStatusEnum
from app.shared.responses import ModuleStatusResponse


def normalize_required_string(value: str) -> str:
    """Normalize a required task text field."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


class TasksStatusResponse(ModuleStatusResponse):
    """Response schema for the tasks module status endpoint."""

    module: Literal["tasks"] = "tasks"


class TaskCreateRequest(BaseModel):
    """Payload used by managers to assign one task."""

    employee_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    priority: TaskPriorityEnum = TaskPriorityEnum.MEDIUM
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized_value = value.strip()
        return normalized_value or None


class TaskResponse(BaseModel):
    """Task item returned to the mobile app."""

    id: int
    employee_id: int
    title: str
    description: str | None
    status: TaskStatusEnum
    priority: TaskPriorityEnum
    due_date: date | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MobileEmployeeSummaryResponse(BaseModel):
    """Compact employee identity for the mobile dashboard."""

    employee_id: int
    matricule: str
    full_name: str


class MobileAttendanceStatusResponse(BaseModel):
    """Today's attendance status for the logged-in employee."""

    attendance_date: date
    status: AttendanceStatusEnum
    first_check_in_at: datetime | None
    last_check_out_at: datetime | None
    worked_duration_minutes: int | None


class MobileTaskStatsResponse(BaseModel):
    """Task counts for the logged-in employee."""

    total: int
    open: int
    done: int
    overdue: int


class MobileTaskSummaryResponse(BaseModel):
    """One payload for the redesigned mobile home screen."""

    employee: MobileEmployeeSummaryResponse
    attendance: MobileAttendanceStatusResponse
    task_stats: MobileTaskStatsResponse
    tasks: list[TaskResponse]
