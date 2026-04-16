from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.apps.auth.dependencies import get_current_super_admin
from app.apps.scanner_app.dependencies import get_scanner_app_service
from app.apps.scanner_app.schemas import (
    AllowedOriginResponse,
    ScannerAppBuildGenerateRequest,
    ScannerAppBuildResponse,
    ScannerAppDownloadQueryResponse,
)
from app.apps.scanner_app.service import (
    ScannerAppNotFoundError,
    ScannerAppService,
    ScannerAppValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/scanner-app", tags=["Scanner App"])


def raise_scanner_app_error(exc: Exception) -> None:
    if isinstance(exc, ScannerAppValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, ScannerAppNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    raise exc


@router.post(
    "/build/generate",
    response_model=ScannerAppBuildResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate scanner app distribution metadata",
)
def generate_scanner_app_build(
    payload: ScannerAppBuildGenerateRequest,
    service: ScannerAppService = Depends(get_scanner_app_service),
    current_user: User = Depends(get_current_super_admin),
) -> ScannerAppBuildResponse:
    try:
        build = service.generate_build(payload=payload, current_user=current_user)
    except (ScannerAppValidationError, ScannerAppNotFoundError) as exc:
        raise_scanner_app_error(exc)

    return ScannerAppBuildResponse(
        id=build.id,
        target_name=build.target_name,
        backend_base_url=build.backend_base_url,
        allowed_origin=build.allowed_origin,
        android_download_url=build.android_download_url,
        windows_download_url=build.windows_download_url,
        linux_download_url=build.linux_download_url,
        generated_by_user_id=build.generated_by_user_id,
        is_active=build.is_active,
        created_at=build.created_at,
        updated_at=build.updated_at,
    )


@router.get(
    "/build/current",
    response_model=ScannerAppBuildResponse,
    status_code=status.HTTP_200_OK,
    summary="Get latest active scanner app build metadata",
)
def get_current_scanner_app_build(
    service: ScannerAppService = Depends(get_scanner_app_service),
    _current_user: User = Depends(get_current_super_admin),
) -> ScannerAppBuildResponse:
    try:
        build = service.get_active_build()
    except (ScannerAppValidationError, ScannerAppNotFoundError) as exc:
        raise_scanner_app_error(exc)

    return ScannerAppBuildResponse(
        id=build.id,
        target_name=build.target_name,
        backend_base_url=build.backend_base_url,
        allowed_origin=build.allowed_origin,
        android_download_url=build.android_download_url,
        windows_download_url=build.windows_download_url,
        linux_download_url=build.linux_download_url,
        generated_by_user_id=build.generated_by_user_id,
        is_active=build.is_active,
        created_at=build.created_at,
        updated_at=build.updated_at,
    )


@router.get(
    "/build/download",
    response_model=ScannerAppDownloadQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve scanner app download URL by platform",
)
def get_scanner_app_download_link(
    platform: str = Query(pattern="^(android|windows|linux)$"),
    service: ScannerAppService = Depends(get_scanner_app_service),
    _current_user: User = Depends(get_current_super_admin),
) -> ScannerAppDownloadQueryResponse:
    try:
        build = service.get_active_build()
        download_url = service.get_download_url(platform=platform, build=build)
    except (ScannerAppValidationError, ScannerAppNotFoundError) as exc:
        raise_scanner_app_error(exc)

    return ScannerAppDownloadQueryResponse(platform=platform, download_url=download_url)


@router.get(
    "/allowed-origins",
    response_model=list[AllowedOriginResponse],
    status_code=status.HTTP_200_OK,
    summary="List active dynamic allowed browser origins",
)
def list_allowed_origins(
    service: ScannerAppService = Depends(get_scanner_app_service),
    _current_user: User = Depends(get_current_super_admin),
) -> list[AllowedOriginResponse]:
    origins = service.list_active_allowed_origins()
    return [AllowedOriginResponse.model_validate(origin.model_dump()) for origin in origins]
