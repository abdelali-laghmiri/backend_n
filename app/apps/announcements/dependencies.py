from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.announcements.service import AnnouncementsService
from app.core.dependencies import get_db_session


def get_announcements_service(
    db: Session = Depends(get_db_session),
) -> AnnouncementsService:
    """Provide the announcements service instance."""

    return AnnouncementsService(db=db)
