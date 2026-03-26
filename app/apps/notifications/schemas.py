from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.apps.notifications.models import NotificationTypeEnum


class NotificationResponse(BaseModel):
    """Notification response payload returned to the recipient user."""

    id: int
    recipient_user_id: int
    title: str
    message: str
    type: NotificationTypeEnum
    is_read: bool
    read_at: datetime | None
    target_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUnreadCountResponse(BaseModel):
    """Unread notification count for the authenticated user."""

    unread_count: int


class NotificationMarkAllReadResponse(BaseModel):
    """Result payload for bulk mark-all-read operations."""

    updated_count: int
