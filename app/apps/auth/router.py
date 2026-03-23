from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.apps.auth.dependencies import get_auth_service, get_current_active_user
from app.apps.auth.schemas import (
    AuthenticatedUserResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
)
from app.apps.auth.service import (
    AuthService,
    AuthenticationError,
    InactiveUserError,
    PasswordChangeError,
)
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.permissions.service import PermissionsService
from app.apps.users.models import User

router = APIRouter(prefix="/auth", tags=["Auth"])


def build_authenticated_user_response(
    user: User,
    permissions_service: PermissionsService,
) -> AuthenticatedUserResponse:
    """Build the authenticated user payload with resolved permissions."""

    effective_permissions = permissions_service.resolve_effective_permissions(user)
    return AuthenticatedUserResponse(
        id=user.id,
        matricule=user.matricule,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_super_admin=user.is_super_admin,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        has_full_access=effective_permissions.has_full_access,
        permissions=effective_permissions.permissions,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate a user and issue a JWT access token",
)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> LoginResponse:
    try:
        user = service.authenticate_user(
            matricule=payload.matricule,
            password=payload.password,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    access_token, expires_in = service.create_access_token_for_user(user)
    return LoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=build_authenticated_user_response(user, permissions_service),
    )


@router.get(
    "/me",
    response_model=AuthenticatedUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Return the current authenticated user",
)
def read_current_user(
    current_user: User = Depends(get_current_active_user),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> AuthenticatedUserResponse:
    return build_authenticated_user_response(current_user, permissions_service)


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Change the current authenticated user's password",
)
def change_password(
    payload: ChangePasswordRequest,
    service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_active_user),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> ChangePasswordResponse:
    try:
        updated_user = service.change_password(
            user=current_user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except PasswordChangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ChangePasswordResponse(
        detail="Password updated successfully.",
        user=build_authenticated_user_response(updated_user, permissions_service),
    )
