from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.notifications.service import NotificationsService
from app.core.dependencies import get_db_session


def get_notifications_service(
    db: Session = Depends(get_db_session),
) -> NotificationsService:
    """Provide the notifications service instance."""

    return NotificationsService(db=db)
