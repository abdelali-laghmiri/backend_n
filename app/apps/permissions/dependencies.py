from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.apps.auth.dependencies import get_current_active_user
from app.apps.permissions.schemas import EffectivePermissionResponse
from app.apps.permissions.service import PermissionsService
from app.apps.users.models import User
from app.core.dependencies import get_db_session


def get_permissions_service(
    db: Session = Depends(get_db_session),
) -> PermissionsService:
    """Provide the permissions service instance."""

    return PermissionsService(db=db)


def get_current_effective_permissions(
    current_user: User = Depends(get_current_active_user),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> EffectivePermissionResponse:
    """Resolve the effective permissions for the current authenticated user."""

    return permissions_service.resolve_effective_permissions(current_user)


def require_permission(permission_code: str) -> Callable[[User, PermissionsService], User]:
    """Require a specific permission code with automatic super-admin bypass."""

    def dependency(
        current_user: User = Depends(get_current_active_user),
        permissions_service: PermissionsService = Depends(get_permissions_service),
    ) -> User:
        if permissions_service.user_has_permission(current_user, permission_code):
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{permission_code}' is required.",
        )

    return dependency


def require_any_permission(
    *permission_codes: str,
) -> Callable[[User, PermissionsService], User]:
    """Require at least one permission code with automatic super-admin bypass."""

    if not permission_codes:
        raise ValueError("At least one permission code is required.")

    def dependency(
        current_user: User = Depends(get_current_active_user),
        permissions_service: PermissionsService = Depends(get_permissions_service),
    ) -> User:
        for permission_code in permission_codes:
            if permissions_service.user_has_permission(current_user, permission_code):
                return current_user

        required_permissions = ", ".join(f"'{code}'" for code in permission_codes)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of permissions {required_permissions} is required.",
        )

    return dependency
