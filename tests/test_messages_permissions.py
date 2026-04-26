from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_messages_permissions_bootstrap.db"

from app.apps.auth.dependencies import get_current_active_user
from app.apps.employees.models import Employee
from app.apps.messages.dependencies import get_messages_service
from app.apps.messages.models import Message, MessagePermissionEnum, MessageRecipient
from app.apps.messages.router import router as messages_router
from app.apps.messages.service import MessagesService
from app.apps.notifications.service import NotificationsService
from app.apps.organization.models import JobTitle
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.core.config import settings
from app.db.base import Base

API_PREFIX = settings.api_v1_prefix


def _make_user(user_id: int, *, first_name: str, last_name: str) -> User:
    return User(
        id=user_id,
        matricule=f"USR-{user_id}",
        password_hash="hash",
        first_name=first_name,
        last_name=last_name,
        email=f"user{user_id}@example.com",
        is_super_admin=False,
        is_active=True,
        must_change_password=False,
    )


def _make_job_title(job_title_id: int, *, level: int) -> JobTitle:
    return JobTitle(
        id=job_title_id,
        name=f"Level {level}",
        code=f"LEVEL_{level}_{job_title_id}",
        description=None,
        hierarchical_level=level,
        is_active=True,
    )


def _make_employee(employee_id: int, *, user_id: int, job_title_id: int) -> Employee:
    return Employee(
        id=employee_id,
        user_id=user_id,
        matricule=f"EMP-{employee_id}",
        first_name="Employee",
        last_name=str(employee_id),
        email=f"employee{employee_id}@example.com",
        phone=None,
        image=None,
        hire_date=date(2024, 1, 1),
        available_leave_balance_days=0,
        department_id=None,
        team_id=None,
        job_title_id=job_title_id,
        is_active=True,
    )


class MessagesPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "messages_permissions.db"
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
        self._seed_hierarchy_users()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_user_selection_shows_only_same_or_down_scope(self) -> None:
        client = self._build_test_client(
            current_user_id=3,
            allowed_permissions={"messages.read_users", "messages.send_same_or_down"},
        )

        response = client.get(f"{API_PREFIX}/messages/users")

        self.assertEqual(response.status_code, 200)
        returned_ids = {item["id"] for item in response.json()}
        self.assertEqual(returned_ids, {3, 4, 5})

    def test_send_all_can_message_anyone(self) -> None:
        client = self._build_test_client(
            current_user_id=3,
            allowed_permissions={"messages.send_all"},
        )

        response = client.post(
            f"{API_PREFIX}/messages",
            json={
                "subject": "Cross-level notice",
                "body": "This should be allowed.",
                "recipients": [{"user_id": 1, "can_reply": True}],
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["sender"]["id"], 3)
        self.assertEqual(payload["recipients"][0]["user"]["id"], 1)

    def test_send_same_or_down_rejects_higher_level_recipient(self) -> None:
        client = self._build_test_client(
            current_user_id=3,
            allowed_permissions={"messages.send_same_or_down"},
        )

        response = client.post(
            f"{API_PREFIX}/messages",
            json={
                "subject": "Unauthorized upward send",
                "body": "This should be blocked.",
                "recipients": [{"user_id": 1, "can_reply": True}],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "You can only message users from the same hierarchy level or below.",
        )

    def test_reply_permission_allows_reply_without_new_send_permissions(self) -> None:
        parent_message = self._seed_message(sender_user_id=1, recipient_user_id=4)
        client = self._build_test_client(
            current_user_id=4,
            allowed_permissions={"messages.reply"},
        )

        response = client.post(
            f"{API_PREFIX}/messages/{parent_message.id}/reply",
            json={
                "subject": "Re: Original",
                "body": "Reply from recipient.",
                "recipients": [{"user_id": 1, "can_reply": True}],
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["parent_message_id"], parent_message.id)
        self.assertEqual(payload["sender"]["id"], 4)

    def test_reply_permission_cannot_add_non_participant_recipient(self) -> None:
        parent_message = self._seed_message(sender_user_id=1, recipient_user_id=4)
        client = self._build_test_client(
            current_user_id=4,
            allowed_permissions={"messages.reply"},
        )

        response = client.post(
            f"{API_PREFIX}/messages/{parent_message.id}/reply",
            json={
                "subject": "Re: Original",
                "body": "Invalid extra recipient.",
                "recipients": [{"user_id": 2, "can_reply": True}],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Reply recipients must belong to the current conversation participants.",
        )

    def test_unauthorized_send_is_blocked(self) -> None:
        client = self._build_test_client(current_user_id=3, allowed_permissions=set())

        response = client.post(
            f"{API_PREFIX}/messages",
            json={
                "subject": "Blocked",
                "body": "No permissions.",
                "recipients": [{"user_id": 4, "can_reply": True}],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "One of permissions 'messages.send_all', 'messages.send_same_or_down', 'messages.send' is required.",
        )

    def _seed_hierarchy_users(self) -> None:
        users = [
            _make_user(1, first_name="Director", last_name="One"),
            _make_user(2, first_name="Manager", last_name="Two"),
            _make_user(3, first_name="Leader", last_name="Three"),
            _make_user(4, first_name="Specialist", last_name="Four"),
            _make_user(5, first_name="Associate", last_name="Five"),
        ]
        job_titles = [
            _make_job_title(1, level=5),
            _make_job_title(2, level=4),
            _make_job_title(3, level=3),
            _make_job_title(4, level=2),
            _make_job_title(5, level=1),
        ]
        employees = [
            _make_employee(1, user_id=1, job_title_id=1),
            _make_employee(2, user_id=2, job_title_id=2),
            _make_employee(3, user_id=3, job_title_id=3),
            _make_employee(4, user_id=4, job_title_id=4),
            _make_employee(5, user_id=5, job_title_id=5),
        ]

        self.db.add_all(users)
        self.db.add_all(job_titles)
        self.db.add_all(employees)
        self.db.commit()

    def _seed_message(self, *, sender_user_id: int, recipient_user_id: int) -> Message:
        message = Message(
            subject="Original",
            body="Original message",
            sender_user_id=sender_user_id,
            conversation_id=None,
            parent_message_id=None,
        )
        self.db.add(message)
        self.db.flush()

        message.conversation_id = message.id
        self.db.add(message)
        self.db.add(
            MessageRecipient(
                message_id=message.id,
                recipient_user_id=recipient_user_id,
                permission=MessagePermissionEnum.CAN_REPLY.value,
                is_read=False,
                read_at=None,
            )
        )
        self.db.commit()
        self.db.refresh(message)
        return message

    def _build_test_client(
        self,
        *,
        current_user_id: int,
        allowed_permissions: set[str],
    ) -> TestClient:
        app = FastAPI()
        app.include_router(messages_router, prefix=API_PREFIX)

        base_user = self.db.get(User, current_user_id)
        assert base_user is not None
        request_user = _make_user(
            current_user_id,
            first_name=base_user.first_name,
            last_name=base_user.last_name,
        )

        class StubPermissionsService:
            def user_has_permission(self, _user: User, permission_code: str) -> bool:
                return permission_code in allowed_permissions

        def override_messages_service():
            db = self.session_factory()
            try:
                yield MessagesService(
                    db=db,
                    notifications_service=NotificationsService(db=db),
                    permissions_service=StubPermissionsService(),
                )
            finally:
                db.close()

        app.dependency_overrides[get_messages_service] = override_messages_service
        app.dependency_overrides[get_current_active_user] = lambda: request_user
        app.dependency_overrides[get_permissions_service] = lambda: StubPermissionsService()
        return TestClient(app)


class MessagesSetupDefaultsTests(unittest.TestCase):
    def test_setup_defaults_seed_messages_permission_refactor_codes(self) -> None:
        default_permission_codes = {
            definition["code"] for definition in SetupService.DEFAULT_PERMISSIONS
        }

        self.assertIn("messages.view", default_permission_codes)
        self.assertIn("messages.recipients.view", default_permission_codes)
        self.assertIn("messages.send_all", default_permission_codes)
        self.assertIn("messages.send_same_or_down", default_permission_codes)
        self.assertIn("messages.reply", default_permission_codes)
        self.assertIn("messages.templates.manage", default_permission_codes)
        self.assertIn("messages.send", default_permission_codes)

        self.assertIn(
            "messages.send_all",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["RH_MANAGER"],
        )
        self.assertIn(
            "messages.templates.manage",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["RH_MANAGER"],
        )
        self.assertIn(
            "messages.send_same_or_down",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["DEPARTMENT_MANAGER"],
        )
        self.assertIn(
            "messages.send_same_or_down",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["TEAM_LEADER"],
        )
        self.assertIn(
            "messages.send_same_or_down",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["EMPLOYEE"],
        )
        self.assertIn(
            "messages.reply",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["EMPLOYEE"],
        )
        self.assertNotIn(
            "messages.send_all",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["DEPARTMENT_MANAGER"],
        )
        self.assertNotIn(
            "messages.send",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["DEPARTMENT_MANAGER"],
        )
        self.assertNotIn(
            "messages.send",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["TEAM_LEADER"],
        )
        self.assertNotIn(
            "messages.send",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["EMPLOYEE"],
        )


if __name__ == "__main__":
    unittest.main()
