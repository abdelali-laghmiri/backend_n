from __future__ import annotations

from app.apps.performance.service import PerformanceService


def get_performance_service() -> PerformanceService:
    """Provide the performance service instance."""

    return PerformanceService()
