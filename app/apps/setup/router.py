from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.apps.setup.dependencies import get_setup_service
from app.apps.setup.schemas import (
    BootstrapSuperAdminResponse,
    SetupInitializeResponse,
    SetupStatusResponse,
)
from app.apps.setup.service import (
    SetupAlreadyInitializedError,
    SetupConfigurationError,
    SetupInitializationError,
    SetupService,
)

router = APIRouter(prefix="/setup", tags=["Setup"])


@router.get(
    "/status",
    response_model=SetupStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check whether the system has already been initialized",
)
def get_setup_status(
    service: SetupService = Depends(get_setup_service),
) -> SetupStatusResponse:
    return SetupStatusResponse.model_validate(service.get_status())


@router.post(
    "/initialize",
    response_model=SetupInitializeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize the system and create the first super admin",
)
def initialize_system(
    service: SetupService = Depends(get_setup_service),
) -> SetupInitializeResponse:
    try:
        super_admin = service.initialize_system()
    except SetupAlreadyInitializedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SetupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except SetupInitializationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return SetupInitializeResponse(
        initialized=False,
        bootstrap_super_admin_exists=True,
        setup_wizard_required=True,
        detail=(
            "Bootstrap super admin created successfully. "
            "Finish the installation from /admin/setup-wizard."
        ),
        super_admin=BootstrapSuperAdminResponse.model_validate(super_admin),
    )
