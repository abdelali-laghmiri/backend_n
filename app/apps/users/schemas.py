from __future__ import annotations

from typing import Literal

from app.shared.responses import ModuleStatusResponse


class UsersStatusResponse(ModuleStatusResponse):
    """Response schema for the users module placeholder endpoint."""

    module: Literal["users"] = "users"
