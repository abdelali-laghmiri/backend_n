from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.messages.service import MessagesService
from app.apps.notifications.dependencies import get_notifications_service
from app.apps.notifications.service import NotificationsService
from app.core.dependencies import get_db_session


def get_messages_service(
    db: Session = Depends(get_db_session),
    notifications_service: NotificationsService = Depends(get_notifications_service),
) -> MessagesService:
    """Provide the internal messages service instance."""

    return MessagesService(db=db, notifications_service=notifications_service)
