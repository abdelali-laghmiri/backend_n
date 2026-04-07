from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from app.apps.announcements.models import AnnouncementTypeEnum


def normalize_required_string(value: str) -> str:
    """Normalize a required announcement text field."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("This field cannot be blank.")

    return normalized_value


def normalize_datetime(value: datetime) -> datetime:
    """Normalize one datetime to UTC and require an explicit timezone."""

    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("Datetime values must include a timezone offset.")

    return value.astimezone(timezone.utc)


class AnnouncementWriteBase(BaseModel):
    """Shared request schema for creating or fully updating an announcement."""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    type: AnnouncementTypeEnum
    is_pinned: bool = False
    is_active: bool = True
    published_at: datetime
    expires_at: datetime | None = None

    @field_validator("title", "summary", "content")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return normalize_required_string(value)

    @field_validator("published_at", "expires_at")
    @classmethod
    def validate_datetime_fields(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        return normalize_datetime(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> "AnnouncementWriteBase":
        if self.expires_at is not None and self.expires_at <= self.published_at:
            raise ValueError("expires_at must be later than published_at.")

        return self


class AnnouncementCreateRequest(AnnouncementWriteBase):
    """Request schema for creating an announcement."""


class AnnouncementUpdateRequest(AnnouncementWriteBase):
    """Request schema for fully updating an announcement."""


class AnnouncementUserSummary(BaseModel):
    """Compact author/editor information returned with announcements."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    full_name: str


class AnnouncementAttachmentResponse(BaseModel):
    """Attachment metadata returned in announcement detail responses."""

    id: int
    file_name: str
    file_url: str
    content_type: str
    file_extension: str
    file_size_bytes: int
    created_at: datetime


class AnnouncementListItemResponse(BaseModel):
    """Announcement item returned by list endpoints."""

    id: int
    title: str
    summary: str
    type: AnnouncementTypeEnum
    is_pinned: bool
    is_active: bool
    is_currently_visible: bool
    published_at: datetime
    expires_at: datetime | None
    is_seen: bool
    seen_at: datetime | None
    has_attachments: bool
    attachments_count: int
    created_at: datetime
    updated_at: datetime
    created_by: AnnouncementUserSummary


class AnnouncementDetailResponse(AnnouncementListItemResponse):
    """Detailed announcement payload for the announcement page and management UI."""

    content: str
    updated_by: AnnouncementUserSummary
    attachments: list[AnnouncementAttachmentResponse]


class AnnouncementMarkSeenResponse(BaseModel):
    """Idempotent mark-seen result for the current authenticated user."""

    announcement_id: int
    is_seen: bool
    seen_at: datetime
