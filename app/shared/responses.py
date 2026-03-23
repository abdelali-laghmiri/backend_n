from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Standard response schema for service health endpoints."""

    status: str
    detail: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "detail": "Service is healthy.",
            }
        }
    )


class ModuleStatusResponse(BaseModel):
    """Base response schema for module placeholder endpoints."""

    module: str
    status: str
    detail: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "module": "users",
                "status": "ready",
                "detail": "Users module router is registered.",
            }
        }
    )
