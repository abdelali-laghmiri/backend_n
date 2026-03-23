from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.apps.requests.models import (
    RequestActionEnum,
    RequestFieldTypeEnum,
    RequestResolverTypeEnum,
    RequestStatusEnum,
    RequestStepKindEnum,
)


def normalize_required_string(value: str) -> str:
    """Normalize required request strings."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional request strings."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


class RequestTypeCreateRequest(BaseModel):
    """Request schema for creating a request type."""

    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_required_string(value).lower()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class RequestTypeUpdateRequest(BaseModel):
    """Request schema for updating a request type."""

    code: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).lower()

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


class RequestTypeResponse(BaseModel):
    """Response schema for request type definitions."""

    id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequestTypeFieldBaseRequest(BaseModel):
    """Shared request-field payload."""

    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=120)
    field_type: RequestFieldTypeEnum
    is_required: bool = False
    placeholder: str | None = Field(default=None, max_length=255)
    help_text: str | None = Field(default=None, max_length=2000)
    default_value: Any | None = None
    sort_order: int = Field(default=0, ge=0)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_required_string(value).lower()

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("placeholder", "help_text")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class RequestTypeFieldCreateRequest(RequestTypeFieldBaseRequest):
    """Request schema for creating a request-type field."""


class RequestTypeFieldUpdateRequest(BaseModel):
    """Request schema for updating a request-type field."""

    code: str | None = Field(default=None, min_length=1, max_length=100)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    field_type: RequestFieldTypeEnum | None = None
    is_required: bool | None = None
    placeholder: str | None = Field(default=None, max_length=255)
    help_text: str | None = Field(default=None, max_length=2000)
    default_value: Any | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value).lower()

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value)

    @field_validator("placeholder", "help_text")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)


class RequestTypeFieldResponse(BaseModel):
    """Response schema for request-field definitions."""

    id: int
    request_type_id: int
    code: str
    label: str
    field_type: RequestFieldTypeEnum
    is_required: bool
    placeholder: str | None
    help_text: str | None
    default_value: Any | None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequestWorkflowStepBaseRequest(BaseModel):
    """Shared request workflow-step payload."""

    step_order: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    step_kind: RequestStepKindEnum
    resolver_type: RequestResolverTypeEnum | None = None
    is_required: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_string(value)

    @model_validator(mode="after")
    def validate_step_configuration(self) -> "RequestWorkflowStepBaseRequest":
        if self.step_kind == RequestStepKindEnum.APPROVER and self.resolver_type is None:
            raise ValueError("Approver steps must define a resolver type.")

        if self.step_kind == RequestStepKindEnum.CONCEPTION and self.resolver_type is not None:
            raise ValueError("Conception steps cannot define a resolver type.")

        return self


class RequestWorkflowStepCreateRequest(RequestWorkflowStepBaseRequest):
    """Request schema for creating a workflow step."""


class RequestWorkflowStepUpdateRequest(BaseModel):
    """Request schema for updating a workflow step."""

    step_order: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    step_kind: RequestStepKindEnum | None = None
    resolver_type: RequestResolverTypeEnum | None = None
    is_required: bool | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return normalize_required_string(value)


class RequestWorkflowStepResponse(BaseModel):
    """Response schema for workflow-step definitions."""

    id: int
    request_type_id: int
    step_order: int
    name: str
    step_kind: RequestStepKindEnum
    resolver_type: RequestResolverTypeEnum | None
    is_required: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequestCreateRequest(BaseModel):
    """Request schema for submitting a dynamic request instance."""

    request_type_id: int = Field(ge=1)
    values: dict[str, Any] = Field(default_factory=dict)


class RequestCurrentStepResponse(BaseModel):
    """Summary of the current workflow step."""

    id: int
    step_order: int
    name: str
    step_kind: RequestStepKindEnum
    resolver_type: RequestResolverTypeEnum | None
    is_required: bool
    current_approver_user_id: int | None
    current_approver_matricule: str | None
    current_approver_name: str | None


class RequestFieldValueResponse(BaseModel):
    """Submitted request-field value snapshot."""

    id: int
    request_field_id: int | None
    field_code: str
    field_label: str
    field_type: RequestFieldTypeEnum
    sort_order: int
    value: Any | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequestActionHistoryResponse(BaseModel):
    """Workflow action-history response schema."""

    id: int
    step_id: int | None
    step_name: str | None
    step_order: int | None
    step_kind: RequestStepKindEnum | None
    resolver_type: RequestResolverTypeEnum | None
    actor_user_id: int | None
    actor_matricule: str | None
    actor_name: str | None
    action: RequestActionEnum
    comment: str | None
    created_at: datetime


class RequestWorkflowProgressResponse(BaseModel):
    """Computed workflow-progress state for a request step."""

    step_id: int
    step_order: int
    name: str
    step_kind: RequestStepKindEnum
    resolver_type: RequestResolverTypeEnum | None
    is_required: bool
    state: str
    actor_user_id: int | None
    actor_matricule: str | None
    actor_name: str | None
    comment: str | None
    acted_at: datetime | None


class RequestSummaryResponse(BaseModel):
    """Summary response for a submitted request."""

    id: int
    request_type_id: int
    request_type_code: str
    request_type_name: str
    requester_user_id: int
    requester_employee_id: int
    status: RequestStatusEnum
    current_step: RequestCurrentStepResponse | None
    submitted_at: datetime
    completed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class RequestDetailResponse(RequestSummaryResponse):
    """Detailed response for a submitted request."""

    submitted_values: list[RequestFieldValueResponse]
    action_history: list[RequestActionHistoryResponse]
    workflow_progress: list[RequestWorkflowProgressResponse]


class RequestStepActionRequest(BaseModel):
    """Base payload for step approval or rejection."""

    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        return normalize_optional_string(value)
