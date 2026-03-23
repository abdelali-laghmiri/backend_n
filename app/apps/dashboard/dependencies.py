from __future__ import annotations

from app.apps.dashboard.service import DashboardService


def get_dashboard_service() -> DashboardService:
    """Provide the dashboard service instance."""

    return DashboardService()
