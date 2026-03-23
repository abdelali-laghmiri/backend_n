from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.setup.service import SetupService
from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session


def get_setup_service(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> SetupService:
    """Provide the setup service instance."""

    return SetupService(db=db, settings=settings)
