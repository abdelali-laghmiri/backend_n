from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.apps.auth.service import AuthService, InactiveUserError
from app.apps.users.models import User
from app.core.config import Settings
from app.core.dependencies import get_app_settings, get_db_session
from app.core.security import TokenValidationError, bearer_scheme, get_bearer_token


def get_auth_service(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> AuthService:
    """Provide the auth service instance."""

    return AuthService(db=db, settings=settings)


def get_current_user(
    auth_service: AuthService = Depends(get_auth_service),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> User:
    """Resolve the current authenticated user from the bearer token."""

    token = get_bearer_token(credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return auth_service.get_authenticated_user_from_token(token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_active_user(
    auth_service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
) -> User:
    """Resolve the current authenticated user and require an active account."""

    try:
        return auth_service.ensure_active_user(current_user)
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


def get_current_super_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Resolve the current authenticated user and require super admin access."""

    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges are required.",
        )

    return current_user
