from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_requests_permissions_bootstrap.db"

from app.apps.auth.dependencies import get_current_active_user
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.requests.dependencies import get_requests_service
from app.apps.requests.models import RequestFieldTypeEnum, RequestType, RequestTypeField
from app.apps.requests.router import router as requests_router
from app.apps.requests.service import RequestsService
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.core.config import settings
from app.db.base import Base

API_PREFIX = settings.api_v1_prefix


def _make_user(user_id: int) -> User:
    return User(
        id=user_id,
        matricule=f"USR-{user_id}",
        password_hash="hash",
        first_name="Request",
        last_name=f"User{user_id}",
        email=f"request-user-{user_id}@example.com",
        is_super_admin=False,
        is_active=True,
        must_change_password=False,
    )


class RequestsPermissionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "requests_permissions.db"
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
        self.current_user = _make_user(100)
        self.db.add(self.current_user)
        self.db.add(
            RequestType(
                id=1,
                code="leave",
                name="Leave Request",
                description="Paid leave request",
                is_active=True,
            )
        )
        self.db.add(
            RequestTypeField(
                id=1,
                request_type_id=1,
                code="reason",
                label="Reason",
                field_type=RequestFieldTypeEnum.TEXT.value,
                is_required=True,
                placeholder=None,
                help_text=None,
                default_value=None,
                sort_order=1,
                is_active=True,
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_create_permission_can_list_request_types(self) -> None:
        with self._build_test_client(allowed_permissions={"requests.create"}) as client:
            response = client.get(f"{API_PREFIX}/requests/types")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["code"], "leave")

    def test_create_permission_can_list_request_fields(self) -> None:
        with self._build_test_client(allowed_permissions={"requests.create"}) as client:
            response = client.get(f"{API_PREFIX}/requests/types/1/fields")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["code"], "reason")

    def test_list_request_types_without_create_or_manage_is_forbidden(self) -> None:
        with self._build_test_client(allowed_permissions=set()) as client:
            response = client.get(f"{API_PREFIX}/requests/types")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "One of permissions 'requests.create', 'requests.manage' is required.",
        )

    def test_create_endpoint_requires_requests_create(self) -> None:
        with self._build_test_client(allowed_permissions=set()) as client:
            response = client.post(
                f"{API_PREFIX}/requests",
                json={"request_type_id": 1, "values": {"reason": "Annual leave"}},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Permission 'requests.create' is required.",
        )

    def test_create_endpoint_allows_requests_create_without_manage(self) -> None:
        class StubRequestsService:
            def create_request(self, current_user: User, payload):
                return {"current_user_id": current_user.id, "payload": payload}

            def build_request_detail(self, workflow_request):
                submitted_at = datetime.now(timezone.utc).isoformat()
                return {
                    "id": 99,
                    "request_type_id": workflow_request["payload"].request_type_id,
                    "request_type_code": "leave",
                    "request_type_name": "Leave Request",
                    "requester_user_id": workflow_request["current_user_id"],
                    "requester_employee_id": 50,
                    "requester_name": "Request User100",
                    "requester_matricule": "USR-100",
                    "status": "in_progress",
                    "current_step": None,
                    "submitted_at": submitted_at,
                    "completed_at": None,
                    "rejection_reason": None,
                    "created_at": submitted_at,
                    "updated_at": submitted_at,
                    "submitted_values": [],
                    "action_history": [],
                    "workflow_progress": [],
                }

        with self._build_test_client(
            allowed_permissions={"requests.create"},
            requests_service=StubRequestsService(),
        ) as client:
            response = client.post(
                f"{API_PREFIX}/requests",
                json={"request_type_id": 1, "values": {"reason": "Annual leave"}},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["requester_user_id"], self.current_user.id)
        self.assertEqual(payload["request_type_id"], 1)
        self.assertEqual(payload["status"], "in_progress")

    def _build_test_client(
        self,
        *,
        allowed_permissions: set[str],
        requests_service: RequestsService | object | None = None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(requests_router, prefix=API_PREFIX)

        request_user = _make_user(self.current_user.id)

        class StubPermissionsService:
            def user_has_permission(self, _user: User, permission_code: str) -> bool:
                return permission_code in allowed_permissions

        if requests_service is None:

            def override_requests_service():
                db = self.session_factory()
                try:
                    yield RequestsService(db=db)
                finally:
                    db.close()

            app.dependency_overrides[get_requests_service] = override_requests_service
        else:
            app.dependency_overrides[get_requests_service] = lambda: requests_service

        app.dependency_overrides[get_current_active_user] = lambda: request_user
        app.dependency_overrides[get_permissions_service] = lambda: StubPermissionsService()
        return TestClient(app)


class RequestsSetupDefaultsTests(unittest.TestCase):
    def test_setup_defaults_include_separate_request_create_permission(self) -> None:
        default_permission_codes = {
            definition["code"] for definition in SetupService.DEFAULT_PERMISSIONS
        }

        self.assertIn("requests.create", default_permission_codes)
        self.assertIn("requests.manage", default_permission_codes)
