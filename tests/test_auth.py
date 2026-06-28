from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_auth_bootstrap.db"

import app.core.rate_limit as rate_limit_module
from app.apps.auth.dependencies import get_auth_service
from app.apps.auth.models import AuthRefreshTokenSession
from app.apps.auth.router import router as auth_router
from app.apps.auth.schemas import ChangePasswordRequest
from app.apps.auth.service import AuthService, RefreshTokenError
from app.apps.users.models import User
from app.core.config import settings
from app.core.dependencies import get_db_session
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import PasswordManager
from app.db.base import Base

API_PREFIX = settings.api_v1_prefix


class _TimezoneSafeAuthService(AuthService):
    """AuthService subclass that handles SQLite timezone loss in datetime columns."""

    def rotate_refresh_token(self, *, refresh_token, device_id=None):
        token_hash = self._hash_refresh_token(refresh_token)
        stmt = select(AuthRefreshTokenSession).where(
            AuthRefreshTokenSession.token_hash == token_hash
        ).limit(1)
        session = self.db.execute(stmt).scalar_one_or_none()
        if session is None:
            raise RefreshTokenError("Refresh token is invalid.")

        now = datetime.now(timezone.utc)
        if session.revoked_at is not None:
            raise RefreshTokenError("Refresh token has been revoked.")

        expires_at = session.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise RefreshTokenError("Refresh token has expired.")

        if device_id and session.device_id and device_id != session.device_id:
            raise RefreshTokenError("Refresh token is invalid.")

        user = self.get_user_by_id(session.user_id)
        if user is None:
            raise RefreshTokenError("Refresh token is invalid.")
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


def _make_user(user_id: int, **kwargs) -> User:
    return User(
        id=user_id,
        matricule=kwargs.get("matricule", f"USR-{user_id}"),
        password_hash=kwargs.get("password_hash", "hash"),
        first_name=kwargs.get("first_name", "Test"),
        last_name=kwargs.get("last_name", f"User{user_id}"),
        email=kwargs.get("email", f"user{user_id}@example.com"),
        is_super_admin=kwargs.get("is_super_admin", False),
        is_active=kwargs.get("is_active", True),
        must_change_password=kwargs.get("must_change_password", False),
    )


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_limiter = rate_limit_module._limiter
        rate_limit_module._limiter = InMemoryRateLimiter()

        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "auth.db"
        self.engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        self.db: Session = self.session_factory()

        password_hash = PasswordManager.hash_password("MyStr0ng!Pass")
        self.active_user = _make_user(
            1,
            matricule="ACTIVE-001",
            password_hash=password_hash,
            first_name="Active",
            last_name="User",
            email="active@example.com",
        )
        self.inactive_user = _make_user(
            2,
            matricule="INACTIVE-001",
            password_hash=password_hash,
            first_name="Inactive",
            last_name="User",
            email="inactive@example.com",
            is_active=False,
        )
        self.db.add(self.active_user)
        self.db.add(self.inactive_user)
        self.db.commit()

    def tearDown(self) -> None:
        rate_limit_module._limiter = self._original_limiter
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_login_success(self) -> None:
        with self._build_test_client() as client:
            response = client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "matricule": "ACTIVE-001",
                    "password": "MyStr0ng!Pass",
                    "issue_refresh_token": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("access_token", payload)
        self.assertEqual(payload["token_type"], "bearer")
        self.assertIsNotNone(payload["expires_in"])
        self.assertIsNone(payload["refresh_token"])
        self.assertIsNone(payload["refresh_expires_in"])
        self.assertEqual(payload["user"]["id"], 1)
        self.assertEqual(payload["user"]["matricule"], "ACTIVE-001")
        self.assertEqual(payload["user"]["first_name"], "Active")

    def test_login_failure_wrong_password(self) -> None:
        with self._build_test_client() as client:
            response = client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "matricule": "ACTIVE-001",
                    "password": "WrongPass1!",
                    "issue_refresh_token": False,
                },
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect matricule or password.")

    def test_login_failure_inactive_user(self) -> None:
        with self._build_test_client() as client:
            response = client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "matricule": "INACTIVE-001",
                    "password": "MyStr0ng!Pass",
                    "issue_refresh_token": False,
                },
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect matricule or password.")

    def test_login_rate_limiting(self) -> None:
        with self._build_test_client() as client:
            for i in range(10):
                response = client.post(
                    f"{API_PREFIX}/auth/login",
                    json={
                        "matricule": "ACTIVE-001",
                        "password": "MyStr0ng!Pass",
                        "issue_refresh_token": False,
                    },
                )
                self.assertEqual(response.status_code, 200, f"Request {i + 1} should succeed")

            response = client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "matricule": "ACTIVE-001",
                    "password": "MyStr0ng!Pass",
                    "issue_refresh_token": False,
                },
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Too many requests. Please try again later.")

    def test_refresh_token(self) -> None:
        with self._build_test_client(timezone_safe=True) as client:
            login_response = client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "matricule": "ACTIVE-001",
                    "password": "MyStr0ng!Pass",
                    "issue_refresh_token": True,
                },
            )
            self.assertEqual(login_response.status_code, 200)
            refresh_token = login_response.json()["refresh_token"]
            self.assertIsNotNone(refresh_token)

            response = client.post(
                f"{API_PREFIX}/auth/refresh",
                json={
                    "refresh_token": refresh_token,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("access_token", payload)
        self.assertIn("refresh_token", payload)
        self.assertIsNotNone(payload["access_token"])
        self.assertIsNotNone(payload["refresh_token"])
        self.assertEqual(payload["token_type"], "bearer")

    def test_refresh_rate_limiting(self) -> None:
        with self._build_test_client() as client:
            for i in range(20):
                response = client.post(
                    f"{API_PREFIX}/auth/refresh",
                    json={
                        "refresh_token": "dummy_token_for_rate_limit_test",
                    },
                )
                self.assertEqual(response.status_code, 401, f"Request {i + 1} should be 401")

            response = client.post(
                f"{API_PREFIX}/auth/refresh",
                json={
                    "refresh_token": "dummy_token_for_rate_limit_test",
                },
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Too many requests. Please try again later.")

    def test_me_endpoint(self) -> None:
        with self._build_test_client() as client:
            login_response = client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "matricule": "ACTIVE-001",
                    "password": "MyStr0ng!Pass",
                    "issue_refresh_token": False,
                },
            )
            self.assertEqual(login_response.status_code, 200)
            access_token = login_response.json()["access_token"]

            response = client.get(
                f"{API_PREFIX}/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["matricule"], "ACTIVE-001")
        self.assertEqual(payload["first_name"], "Active")
        self.assertEqual(payload["last_name"], "User")
        self.assertEqual(payload["email"], "active@example.com")
        self.assertFalse(payload["is_super_admin"])
        self.assertTrue(payload["is_active"])
        self.assertFalse(payload["must_change_password"])

    def _build_test_client(self, *, timezone_safe: bool = False) -> TestClient:
        app = FastAPI()
        app.include_router(auth_router, prefix=API_PREFIX)

        def override_get_db_session():
            yield self.db

        app.dependency_overrides[get_db_session] = override_get_db_session

        if timezone_safe:
            app.dependency_overrides[get_auth_service] = lambda: _TimezoneSafeAuthService(
                db=self.db, settings=settings
            )

        return TestClient(app)


class ChangePasswordValidationTests(unittest.TestCase):
    def test_valid_password_passes(self) -> None:
        request = ChangePasswordRequest(
            current_password="OldPass1!",
            new_password="NewStr0ng!Pass",
        )
        self.assertEqual(request.new_password, "NewStr0ng!Pass")

    def test_password_too_short(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="OldPass1!",
                new_password="Short1!",
            )

    def test_password_missing_uppercase(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="OldPass1!",
                new_password="nouppercase1!",
            )

    def test_password_missing_lowercase(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="OldPass1!",
                new_password="NOLOWERCASE1!",
            )

    def test_password_missing_digit(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="OldPass1!",
                new_password="NoDigitStr!",
            )

    def test_password_missing_special_char(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="OldPass1!",
                new_password="NoSpecial1Char",
            )

    def test_passwords_must_differ(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="SamePass1!",
                new_password="SamePass1!",
            )


if __name__ == "__main__":
    unittest.main()
