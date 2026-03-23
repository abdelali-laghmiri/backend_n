from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.apps.users.dependencies import get_users_service
from app.apps.users.schemas import UsersStatusResponse
from app.apps.users.service import UsersService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/status",
    response_model=UsersStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check users module availability",
)
def get_users_status(
    _service: UsersService = Depends(get_users_service),
) -> UsersStatusResponse:
    return UsersStatusResponse(
        status="ready",
        detail="Users module router is registered.",
    )
