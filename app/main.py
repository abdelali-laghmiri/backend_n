from __future__ import annotations

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.apps import api_router
from app.apps.scanner_app.origins import get_merged_browser_origins
from app.core.config import settings
from app.core.database_init import initialize_database_schema
from app.shared.constants import API_TAGS
from app.shared.responses import HealthResponse
from app.shared.uploads import UPLOADS_DIR, ensure_uploads_dir_exists

app = FastAPI(
    title=settings.project_name,
    version=settings.project_version,
    description=settings.project_description,
    debug=settings.debug,
    openapi_tags=API_TAGS,
)

ensure_uploads_dir_exists()

browser_cors_allow_origins = get_merged_browser_origins(settings)

if browser_cors_allow_origins:
    # CORS applies only to browser-based cross-origin requests.
    # Native desktop and mobile clients can use the authenticated API directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=browser_cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
        ],
    )


@app.on_event("startup")
def initialize_database_on_startup() -> None:
    """Create missing tables on first boot without mutating existing tables."""

    initialize_database_schema()


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


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Serve a minimal inline favicon to avoid browser 404 noise."""

    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='12' ry='12' fill='#0ea5e9'/><text x='32' y='42' text-anchor='middle' font-size='32' fill='white' font-family='Arial, sans-serif'>HR</text></svg>"""
    return Response(content=svg, media_type="image/svg+xml")


app.mount(
    "/static/uploads",
    StaticFiles(directory=str(UPLOADS_DIR), check_dir=False),
    name="uploads",
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
