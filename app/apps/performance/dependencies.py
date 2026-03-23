from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.performance.service import PerformanceService
from app.core.dependencies import get_db_session


def get_performance_service(
    db: Session = Depends(get_db_session),
) -> PerformanceService:
    """Provide the performance service instance."""

    return PerformanceService(db=db)
