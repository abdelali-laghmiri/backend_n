from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.users.service import UsersService
from app.core.dependencies import get_db_session


def get_users_service(
    db: Session = Depends(get_db_session),
) -> UsersService:
    """Provide the users service instance."""

    return UsersService(db=db)
