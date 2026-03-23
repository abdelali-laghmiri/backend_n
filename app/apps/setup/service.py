from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.users.models import User
from app.core.config import Settings
from app.core.security import PasswordManager


class SetupAlreadyInitializedError(RuntimeError):
    """Raised when the system has already been initialized."""


class SetupConfigurationError(RuntimeError):
    """Raised when required bootstrap configuration is missing."""


class SetupInitializationError(RuntimeError):
    """Raised when initialization cannot complete safely."""


class SetupService:
    """Service layer for one-time system setup and bootstrap."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def is_initialized(self) -> bool:
        """Return whether a super admin account already exists."""

        return self.get_super_admin() is not None

    def get_super_admin(self) -> User | None:
        """Return the first super admin account if it exists."""

        statement = (
            select(User)
            .where(User.is_super_admin.is_(True))
            .order_by(User.id.asc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def initialize_system(self) -> User:
        """Create the bootstrap super admin account exactly once."""

        if self.is_initialized():
            raise SetupAlreadyInitializedError(
                "System initialization has already been completed."
            )

        try:
            bootstrap_values = self.settings.get_super_admin_bootstrap()
        except ValueError as exc:
            raise SetupConfigurationError(str(exc)) from exc

        super_admin = User(
            matricule=bootstrap_values["matricule"],
            password_hash=PasswordManager.hash_password(bootstrap_values["password"]),
            first_name=bootstrap_values["first_name"],
            last_name=bootstrap_values["last_name"],
            email=bootstrap_values["email"],
            is_super_admin=True,
            is_active=True,
            must_change_password=True,
        )
        self.db.add(super_admin)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if self.is_initialized():
                raise SetupAlreadyInitializedError(
                    "System initialization has already been completed."
                ) from exc
            raise SetupInitializationError(
                "Failed to create the bootstrap super admin account."
            ) from exc

        self.db.refresh(super_admin)
        return super_admin
