from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.auth.models import AuthRefreshTokenSession
from app.apps.users.models import User
from app.core.config import Settings
from app.core.security import JWTManager, PasswordManager, TokenValidationError


class AuthenticationError(RuntimeError):
    """Raised when user credentials are invalid."""


class InactiveUserError(RuntimeError):
    """Raised when an inactive account attempts an authenticated action."""


class PasswordChangeError(RuntimeError):
    """Raised when a password change request is invalid."""


class RefreshTokenError(RuntimeError):
    """Raised when a refresh token exchange fails."""


class AuthService:
    """Service layer for authentication and current-user operations."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def authenticate_user(self, *, matricule: str, password: str) -> User:
        """Authenticate a user with matricule and password."""

        user = self.get_user_by_matricule(matricule)
        if user is None or not PasswordManager.verify_password(password, user.password_hash):
            raise AuthenticationError("Incorrect matricule or password.")

        if not user.is_active:
            raise InactiveUserError("Inactive user accounts cannot sign in.")

        return user

    def create_access_token_for_user(self, user: User) -> tuple[str, int]:
        """Create a JWT access token for the authenticated user."""

        expires_in = self.settings.access_token_expire_minutes * 60
        token = JWTManager.create_access_token(
            subject=str(user.id),
            secret_key=self.settings.secret_key.get_secret_value(),
            expires_delta=timedelta(minutes=self.settings.access_token_expire_minutes),
            algorithm=self.settings.jwt_algorithm,
            extra_claims={"matricule": user.matricule},
        )
        return token, expires_in

    def create_refresh_token_session(
        self,
        *,
        user: User,
        device_id: str | None = None,
    ) -> tuple[str, int]:
        """Create a long-lived refresh token session for scanner clients."""

        refresh_token = self._generate_refresh_token()
        token_hash = self._hash_refresh_token(refresh_token)
        expires_delta = timedelta(days=self.settings.refresh_token_expire_days)
        expires_at = datetime.now(timezone.utc) + expires_delta

        session = AuthRefreshTokenSession(
            user_id=user.id,
            token_hash=token_hash,
            device_id=device_id,
            expires_at=expires_at,
        )
        self.db.add(session)
        self.db.commit()

        return refresh_token, int(expires_delta.total_seconds())

    def rotate_refresh_token(
        self,
        *,
        refresh_token: str,
        device_id: str | None = None,
    ) -> tuple[User, str, int]:
        """Rotate a valid refresh token and return a new one."""

        token_hash = self._hash_refresh_token(refresh_token)
        statement = (
            select(AuthRefreshTokenSession)
            .where(AuthRefreshTokenSession.token_hash == token_hash)
            .limit(1)
        )
        session = self.db.execute(statement).scalar_one_or_none()
        if session is None:
            raise RefreshTokenError("Refresh token is invalid.")

        now = datetime.now(timezone.utc)
        if session.revoked_at is not None:
            raise RefreshTokenError("Refresh token has been revoked.")
        if session.expires_at <= now:
            raise RefreshTokenError("Refresh token has expired.")
        if device_id and session.device_id and device_id != session.device_id:
            raise RefreshTokenError("Refresh token does not match this device.")

        user = self.get_user_by_id(session.user_id)
        if user is None:
            raise RefreshTokenError("User for refresh token no longer exists.")
        self.ensure_active_user(user)

        session.revoked_at = now
        session.last_used_at = now
        self.db.add(session)

        next_refresh_token = self._generate_refresh_token()
        next_token_hash = self._hash_refresh_token(next_refresh_token)
        expires_delta = timedelta(days=self.settings.refresh_token_expire_days)

        next_session = AuthRefreshTokenSession(
            user_id=user.id,
            token_hash=next_token_hash,
            device_id=device_id or session.device_id,
            expires_at=now + expires_delta,
        )
        self.db.add(next_session)
        self.db.commit()

        return user, next_refresh_token, int(expires_delta.total_seconds())

    def get_authenticated_user_from_token(self, token: str) -> User:
        """Resolve the authenticated user from a JWT access token."""

        payload = JWTManager.decode_token(
            token=token,
            secret_key=self.settings.secret_key.get_secret_value(),
            algorithm=self.settings.jwt_algorithm,
        )
        try:
            user_id = int(payload["sub"])
        except (TypeError, ValueError, KeyError) as exc:
            raise TokenValidationError("Token subject is invalid.") from exc

        user = self.get_user_by_id(user_id)
        if user is None:
            raise TokenValidationError("Authenticated user no longer exists.")

        return user

    def ensure_active_user(self, user: User) -> User:
        """Ensure that the resolved authenticated user is active."""

        if not user.is_active:
            raise InactiveUserError("Inactive user accounts cannot access this resource.")

        return user

    def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
    ) -> User:
        """Change the authenticated user's password."""

        if not PasswordManager.verify_password(current_password, user.password_hash):
            raise PasswordChangeError("Current password is incorrect.")

        user.password_hash = PasswordManager.hash_password(new_password)
        user.must_change_password = False
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_user_by_matricule(self, matricule: str) -> User | None:
        """Return a user by matricule."""

        normalized_matricule = matricule.strip()
        if not normalized_matricule:
            return None

        statement = select(User).where(User.matricule == normalized_matricule).limit(1)
        return self.db.execute(statement).scalar_one_or_none()

    def get_user_by_id(self, user_id: int) -> User | None:
        """Return a user by primary key."""

        statement = select(User).where(User.id == user_id).limit(1)
        return self.db.execute(statement).scalar_one_or_none()

    def _generate_refresh_token(self) -> str:
        return secrets.token_urlsafe(48)

    def _hash_refresh_token(self, refresh_token: str) -> str:
        return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
