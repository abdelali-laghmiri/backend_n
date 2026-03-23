from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.admin_panel.service import AdminPanelService
from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session


def get_admin_panel_service(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> AdminPanelService:
    """Provide the admin panel service."""

    return AdminPanelService(db=db, settings=settings)
