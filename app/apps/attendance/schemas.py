from __future__ import annotations

from typing import Literal

from app.shared.responses import ModuleStatusResponse


class AttendanceStatusResponse(ModuleStatusResponse):
    """Response schema for the attendance module placeholder endpoint."""

    module: Literal["attendance"] = "attendance"
