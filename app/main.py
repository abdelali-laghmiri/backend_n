from __future__ import annotations

from fastapi import FastAPI, status

from app.apps import api_router
from app.core.config import settings
from app.shared.constants import API_TAGS
from app.shared.responses import HealthResponse

app = FastAPI(
    title=settings.project_name,
    version=settings.project_version,
    description=settings.project_description,
    debug=settings.debug,
    openapi_tags=API_TAGS,
)


@app.get(
    "/",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Service root",
)
def read_root() -> HealthResponse:
    return HealthResponse(
        status="ok",
        detail="HR management backend skeleton is running.",
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Application health check",
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", detail="Service is healthy.")


app.include_router(api_router, prefix=settings.api_v1_prefix)
