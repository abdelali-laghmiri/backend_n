from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.scanner_app.service import ScannerAppService
from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session


def get_scanner_app_service(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> ScannerAppService:
    return ScannerAppService(db=db, settings=settings)
