from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.apps.dashboard.dependencies import get_dashboard_service
from app.apps.dashboard.schemas import DashboardStatusResponse
from app.apps.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/status",
    response_model=DashboardStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check dashboard module availability",
)
def get_dashboard_status(
    _service: DashboardService = Depends(get_dashboard_service),
) -> DashboardStatusResponse:
    return DashboardStatusResponse(
        status="ready",
        detail="Dashboard module router is registered.",
    )
