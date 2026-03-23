from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.requests.service import RequestsService
from app.core.dependencies import get_db_session


def get_requests_service(
    db: Session = Depends(get_db_session),
) -> RequestsService:
    """Provide the requests service instance."""

    return RequestsService(db=db)
