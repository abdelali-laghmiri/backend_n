from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_users_bootstrap.db"

from app.apps.auth.dependencies import get_current_super_admin
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.users.dependencies import get_users_service
from app.apps.users.models import User
from app.apps.users.router import router as users_router
from app.apps.users.service import UsersService
from app.core.config import settings
from app.db.base import Base

API_PREFIX = settings.api_v1_prefix


def _make_user(user_id: int) -> User:
    return User(
        id=user_id,
        matricule=f"ADM-{user_id}",
        password_hash="hash",
        first_name="Admin",
        last_name=f"User{user_id}",
        email=f"admin{user_id}@example.com",
        is_super_admin=True,
        is_active=True,
        must_change_password=False,
    )


class UsersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "users.db"
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
        self.admin_user = _make_user(999)
        self.db.add(self.admin_user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_create_user(self) -> None:
        client = self._build_test_client()

        response = client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "USR-001",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "password": "Test@1234",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["matricule"], "USR-001")
        self.assertEqual(payload["first_name"], "John")
        self.assertEqual(payload["last_name"], "Doe")
        self.assertEqual(payload["email"], "john.doe@example.com")
        self.assertFalse(payload["is_super_admin"])
        self.assertTrue(payload["is_active"])
        self.assertTrue(payload["must_change_password"])
        self.assertIn("id", payload)
        self.assertIn("created_at", payload)
        self.assertIn("updated_at", payload)
        self.assertIsNone(payload["linked_employee"])

    def test_create_user_duplicate_matricule(self) -> None:
        client = self._build_test_client()

        client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "DUP-001",
                "first_name": "First",
                "last_name": "User",
                "email": "first@example.com",
                "password": "Test@1234",
            },
        )

        response = client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "DUP-001",
                "first_name": "Second",
                "last_name": "User",
                "email": "second@example.com",
                "password": "Test@1234",
            },
        )

        self.assertEqual(response.status_code, 409)

    def test_get_user(self) -> None:
        client = self._build_test_client()

        create_response = client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "GET-001",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@example.com",
                "password": "Test@1234",
            },
        )
        user_id = create_response.json()["id"]

        response = client.get(f"{API_PREFIX}/users/{user_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], user_id)
        self.assertEqual(payload["matricule"], "GET-001")
        self.assertEqual(payload["first_name"], "Jane")
        self.assertEqual(payload["last_name"], "Smith")

    def test_get_user_not_found(self) -> None:
        client = self._build_test_client()

        response = client.get(f"{API_PREFIX}/users/99999")

        self.assertEqual(response.status_code, 404)

    def test_update_user(self) -> None:
        client = self._build_test_client()

        create_response = client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "UPD-001",
                "first_name": "Old",
                "last_name": "Name",
                "email": "old.name@example.com",
                "password": "Test@1234",
            },
        )
        user_id = create_response.json()["id"]

        response = client.patch(
            f"{API_PREFIX}/users/{user_id}",
            json={"first_name": "Updated"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["first_name"], "Updated")
        self.assertEqual(payload["last_name"], "Name")

    def test_list_users(self) -> None:
        client = self._build_test_client()

        client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "LST-001",
                "first_name": "Alice",
                "last_name": "A",
                "email": "alice@example.com",
                "password": "Test@1234",
            },
        )
        client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "LST-002",
                "first_name": "Bob",
                "last_name": "B",
                "email": "bob@example.com",
                "password": "Test@1234",
            },
        )

        response = client.get(f"{API_PREFIX}/users")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload), 2)

    def test_list_users_with_pagination(self) -> None:
        client = self._build_test_client()

        for i in range(1, 6):
            client.post(
                f"{API_PREFIX}/users",
                json={
                    "matricule": f"PAG-{i:03d}",
                    "first_name": f"User{i}",
                    "last_name": "Pagination",
                    "email": f"user{i}_pag@example.com",
                    "password": "Test@1234",
                },
            )

        response_page1 = client.get(f"{API_PREFIX}/users", params={"limit": 2})
        self.assertEqual(response_page1.status_code, 200)
        page1 = response_page1.json()
        self.assertEqual(len(page1), 2)

        response_page2 = client.get(
            f"{API_PREFIX}/users", params={"limit": 2, "offset": 2}
        )
        self.assertEqual(response_page2.status_code, 200)
        page2 = response_page2.json()
        self.assertEqual(len(page2), 2)

        page1_ids = {item["id"] for item in page1}
        page2_ids = {item["id"] for item in page2}
        self.assertTrue(page1_ids.isdisjoint(page2_ids))

    def test_list_users_default_limit(self) -> None:
        client = self._build_test_client()

        for i in range(1, 151):
            client.post(
                f"{API_PREFIX}/users",
                json={
                    "matricule": f"DFL-{i:03d}",
                    "first_name": f"Bulk{i}",
                    "last_name": "User",
                    "email": f"bulk{i}_dfl@example.com",
                    "password": "Test@1234",
                },
            )

        response = client.get(f"{API_PREFIX}/users")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 100)

    def test_list_users_max_limit_validation(self) -> None:
        client = self._build_test_client()

        response = client.get(f"{API_PREFIX}/users", params={"limit": 1001})

        self.assertEqual(response.status_code, 422)

    def test_deactivate_and_activate_user(self) -> None:
        client = self._build_test_client()

        create_response = client.post(
            f"{API_PREFIX}/users",
            json={
                "matricule": "ACT-001",
                "first_name": "Toggle",
                "last_name": "Test",
                "email": "toggle.test@example.com",
                "password": "Test@1234",
            },
        )
        user_id = create_response.json()["id"]

        deactivate_response = client.post(f"{API_PREFIX}/users/{user_id}/deactivate")
        self.assertEqual(deactivate_response.status_code, 200)
        self.assertFalse(deactivate_response.json()["user"]["is_active"])

        activate_response = client.post(f"{API_PREFIX}/users/{user_id}/activate")
        self.assertEqual(activate_response.status_code, 200)
        self.assertTrue(activate_response.json()["user"]["is_active"])

    def _build_test_client(self) -> TestClient:
        app = FastAPI()
        app.include_router(users_router, prefix=API_PREFIX)

        request_admin = _make_user(self.admin_user.id)

        class StubPermissionsService:
            def user_has_permission(self, _user: User, permission_code: str) -> bool:
                return True

        def override_users_service():
            db = self.session_factory()
            try:
                yield UsersService(db=db)
            finally:
                db.close()

        app.dependency_overrides[get_users_service] = override_users_service
        app.dependency_overrides[get_current_super_admin] = lambda: request_admin
        app.dependency_overrides[get_permissions_service] = lambda: StubPermissionsService()
        return TestClient(app)


if __name__ == "__main__":
    unittest.main()
