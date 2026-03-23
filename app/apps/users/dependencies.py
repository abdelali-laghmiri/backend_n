from __future__ import annotations

from app.apps.users.service import UsersService


def get_users_service() -> UsersService:
    """Provide the users service instance."""

    return UsersService()
