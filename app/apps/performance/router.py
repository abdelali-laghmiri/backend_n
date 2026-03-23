from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.apps.performance.dependencies import get_performance_service
from app.apps.performance.schemas import PerformanceStatusResponse
from app.apps.performance.service import PerformanceService

router = APIRouter(prefix="/performance", tags=["Performance"])


@router.get(
    "/status",
    response_model=PerformanceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check performance module availability",
)
def get_performance_status(
    _service: PerformanceService = Depends(get_performance_service),
) -> PerformanceStatusResponse:
    return PerformanceStatusResponse(
        status="ready",
        detail="Performance module router is registered.",
    )
