from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.dashboard.service import DashboardService
from app.core.dependencies import get_db_session


def get_dashboard_service(
    db: Session = Depends(get_db_session),
) -> DashboardService:
    """Provide the dashboard service instance."""

    return DashboardService(db=db)
