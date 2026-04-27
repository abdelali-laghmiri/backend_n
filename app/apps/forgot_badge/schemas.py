from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.apps.forgot_badge.models import (
    ForgotBadgeRequestStatusEnum,
    TemporaryNfcAssignmentStatusEnum,
)


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


class ForgotBadgeRequestCreateRequest(BaseModel):
    """Request schema for creating a forgot badge request."""

    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class ForgotBadgeRequestApproveRequest(BaseModel):
    """Request schema for approving a forgot badge request."""

    nfc_card_id: int | None = Field(default=None, ge=1)
    nfc_uid: str | None = Field(default=None, min_length=1, max_length=120)
    valid_for_date: date
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("nfc_uid")
    @classmethod
    def validate_nfc_uid(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized_value = value.strip().upper()
        return normalized_value or None

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)

    @model_validator(mode="after")
    def validate_card_selector(self) -> "ForgotBadgeRequestApproveRequest":
        if self.nfc_card_id is None and self.nfc_uid is None:
            raise ValueError("Either nfc_card_id or nfc_uid is required.")

        return self


class ForgotBadgeRequestRejectRequest(BaseModel):
    """Request schema for rejecting a forgot badge request."""

    notes: str | None = Field(default=None, max_length=500)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class ForgotBadgeRequestCompleteRequest(BaseModel):
    """Request schema for marking a forgot badge request as completed."""

    notes: str | None = Field(default=None, max_length=500)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class ForgotBadgeRequestCancelRequest(BaseModel):
    """Request schema for cancelling a forgot badge request."""

    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class ForgotBadgeRequestResponse(BaseModel):
    """Response schema for forgot badge requests."""

    id: int
    employee_id: int
    user_id: int | None
    status: str
    reason: str | None
    requested_at: datetime
    handled_by_user_id: int | None
    handled_at: datetime | None
    nfc_card_id: int | None
    temporary_card_id: int | None = None
    temporary_card_label: str | None = None
    temporary_card_nfc_uid: str | None = None
    valid_for_date: date | None
    assignment_status: str | None = None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ForgotBadgeRequestWithEmployeeResponse(BaseModel):
    """Response schema for forgot badge requests with employee details."""

    id: int
    employee_id: int
    employee_matricule: str
    employee_name: str
    employee_department: str | None = None
    user_id: int | None
    status: str
    reason: str | None
    requested_at: datetime
    handled_by_user_id: int | None
    handled_at: datetime | None
    nfc_card_id: int | None
    temporary_card_id: int | None = None
    temporary_card_label: str | None = None
    temporary_card_nfc_uid: str | None = None
    valid_for_date: date | None
    assignment_status: str | None = None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemporaryNfcAssignmentResponse(BaseModel):
    """Response schema for temporary NFC assignments."""

    id: int
    employee_id: int
    nfc_card_id: int
    forgot_badge_request_id: int | None
    assigned_by_user_id: int
    assigned_at: datetime
    valid_for_date: date
    status: str
    check_in_attendance_id: int | None
    check_out_attendance_id: int | None
    released_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ForgotBadgeRequestWithAssignmentResponse(BaseModel):
    """Response schema combining forgot badge request with temporary assignment."""

    request: ForgotBadgeRequestResponse
    temporary_assignment: TemporaryNfcAssignmentResponse | None
