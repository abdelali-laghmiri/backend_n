from __future__ import annotations

from typing import Literal

from app.shared.responses import ModuleStatusResponse


class PerformanceStatusResponse(ModuleStatusResponse):
    """Response schema for the performance module placeholder endpoint."""

    module: Literal["performance"] = "performance"
