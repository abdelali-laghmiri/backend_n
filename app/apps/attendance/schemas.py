from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.apps.attendance.models import AttendanceReaderTypeEnum, AttendanceStatusEnum
from app.shared.responses import ModuleStatusResponse


def normalize_required_string(value: str) -> str:
    """Normalize required attendance strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


class AttendanceStatusResponse(ModuleStatusResponse):
    """Response schema for the attendance module status endpoint."""

    module: Literal["attendance"] = "attendance"


class AttendanceScanBaseRequest(BaseModel):
    """Shared payload fields used by attendance scan ingestion endpoints."""

    reader_type: AttendanceReaderTypeEnum
    scanned_at: datetime
    source: str = Field(default="external_pointage_app", min_length=1, max_length=120)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        normalized_value = normalize_required_string(value)
        return normalized_value

    @field_validator("scanned_at")
    @classmethod
    def normalize_scanned_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value


class AttendanceScanIngestRequest(AttendanceScanBaseRequest):
    """Payload sent by the external pointage application using matricule identity."""

    matricule: str = Field(min_length=1, max_length=50)

    @field_validator("matricule")
    @classmethod
    def validate_matricule(cls, value: str) -> str:
        return normalize_required_string(value).upper()


class AttendanceNfcScanIngestRequest(AttendanceScanBaseRequest):
    """Payload sent by the external pointage application using NFC identity."""

    nfc_uid: str = Field(min_length=1, max_length=120)

    @field_validator("nfc_uid")
    @classmethod
    def validate_nfc_uid(cls, value: str) -> str:
        return normalize_required_string(value).upper()


class AttendanceNfcCardAssignRequest(BaseModel):
    """Payload used to attach one NFC card to one employee."""

    employee_id: int = Field(ge=1)
    nfc_uid: str = Field(min_length=1, max_length=120)

    @field_validator("nfc_uid")
    @classmethod
    def validate_nfc_uid(cls, value: str) -> str:
        return normalize_required_string(value).upper()


class AttendanceRawScanEventResponse(BaseModel):
    """Raw scan event response schema."""

    id: int
    employee_id: int
    user_id: int | None
    employee_matricule: str
    employee_name: str
    reader_type: AttendanceReaderTypeEnum
    scanned_at: datetime
    source: str
    created_at: datetime


class AttendanceDailySummaryResponse(BaseModel):
    """Day-level attendance summary response schema."""

    id: int
    employee_id: int
    employee_matricule: str
    employee_name: str
    attendance_date: date
    first_check_in_at: datetime | None
    last_check_out_at: datetime | None
    worked_duration_minutes: int | None
    status: AttendanceStatusEnum
    linked_request_id: int | None
    created_at: datetime
    updated_at: datetime


class AttendanceScanIngestResponse(BaseModel):
    """Response returned after ingesting a scan event."""

    raw_event: AttendanceRawScanEventResponse
    daily_summary: AttendanceDailySummaryResponse


class AttendanceNfcCardResponse(BaseModel):
    """Response returned after attaching one NFC card to one employee."""

    id: int
    employee_id: int
    employee_matricule: str
    employee_name: str
    nfc_uid: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AttendanceMonthlyReportGenerateRequest(BaseModel):
    """Request schema for generating monthly attendance reports."""

    report_year: int = Field(ge=2000, le=9999)
    report_month: int = Field(ge=1, le=12)
    employee_id: int | None = Field(default=None, ge=1)
    include_inactive: bool = False


class AttendanceMonthlyReportResponse(BaseModel):
    """Month-level attendance report response schema."""

    id: int
    employee_id: int
    employee_matricule: str
    employee_name: str
    report_year: int
    report_month: int
    total_worked_days: int
    total_worked_minutes: int
    total_present_days: int
    total_absence_days: int
    total_leave_days: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AttendanceMonthlyReportGenerateResponse(BaseModel):
    """Response schema for a monthly report generation trigger."""

    report_year: int
    report_month: int
    generated_count: int
    reports: list[AttendanceMonthlyReportResponse]
