from __future__ import annotations

from typing import Literal

from app.shared.responses import ModuleStatusResponse


class DashboardStatusResponse(ModuleStatusResponse):
    """Response schema for the dashboard module placeholder endpoint."""

    module: Literal["dashboard"] = "dashboard"
