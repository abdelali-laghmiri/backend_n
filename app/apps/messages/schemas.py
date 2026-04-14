from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.apps.messages.models import MessagePermissionEnum


def _normalize_required_text(value: str, *, label: str, max_length: int | None = None) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{label} cannot be blank.")

    if max_length is not None and len(normalized_value) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters.")

    return normalized_value


class UserSummary(BaseModel):
    """Compact user summary for message metadata."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    full_name: str


class MessageRecipientCandidateResponse(BaseModel):
    """Selectable recipient returned for message composition."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    full_name: str
    department: str | None = None
    team: str | None = None
    job_title: str | None = None
    hierarchical_level: int | None = None


class MessageRecipientInput(BaseModel):
    """Recipient payload for message creation."""

    user_id: int = Field(gt=0)
    can_reply: bool = True


class MessageCreateRequest(BaseModel):
    """Payload for composing a new message."""

    subject: str
    body: str
    recipients: List[MessageRecipientInput]
    parent_message_id: int | None = Field(default=None, gt=0)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _normalize_required_text(value, label="Subject", max_length=200)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        return _normalize_required_text(value, label="Body")


class MessageRecipientResponse(BaseModel):
    """Recipient state returned with a message."""

    user: UserSummary
    permission: MessagePermissionEnum
    is_read: bool
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Full message payload for inbox/sent detail."""

    id: int
    subject: str
    body: str
    conversation_id: int
    parent_message_id: int | None
    sender: UserSummary
    recipients: list[MessageRecipientResponse]
    created_at: datetime
    updated_at: datetime


class MessageListItemResponse(BaseModel):
    """List item view of a message."""

    id: int
    subject: str
    conversation_id: int
    parent_message_id: int | None
    sender: UserSummary
    recipients_count: int
    is_read: bool
    can_reply: bool
    created_at: datetime


class MessageMarkReadResponse(BaseModel):
    """Response when marking a message as read."""

    message: MessageResponse


class MessageUnreadCountResponse(BaseModel):
    """Unread count scoped to the current user."""

    unread_count: int


class MessageTemplateCreateRequest(BaseModel):
    """Payload to create a personal message template."""

    name: str
    subject: str
    body: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_required_text(value, label="Template name", max_length=120)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _normalize_required_text(value, label="Subject", max_length=200)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        return _normalize_required_text(value, label="Body")


class MessageTemplateUpdateRequest(BaseModel):
    """Payload to update a personal message template."""

    name: str | None = Field(default=None, max_length=120)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, label="Template name", max_length=120)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, label="Subject", max_length=200)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, label="Body")


class MessageTemplateResponse(BaseModel):
    """Response schema for message templates."""

    id: int
    name: str
    subject: str
    body: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
