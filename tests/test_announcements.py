from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_announcements_bootstrap.db"

from app.core.config import settings
from app.apps.announcements.dependencies import get_announcements_service
from app.apps.announcements.models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementRead,
    AnnouncementTypeEnum,
)
import app.apps.announcements.router as announcements_router_module
import app.apps.announcements.storage as announcement_storage_module
from app.apps.announcements.router import router as announcements_router
from app.apps.announcements.schemas import AnnouncementCreateRequest
from app.apps.announcements.service import AnnouncementsService
from app.apps.auth.dependencies import get_current_active_user
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.db.base import Base
from app.shared import uploads as uploads_module

API_PREFIX = settings.api_v1_prefix


def _make_user(user_id: int) -> User:
    return User(
        id=user_id,
        matricule=f"USR-{user_id}",
        password_hash="hash",
        first_name="Test",
        last_name=f"User{user_id}",
        email=f"user{user_id}@example.com",
        is_super_admin=False,
        is_active=True,
        must_change_password=False,
    )


class AnnouncementsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "announcements.db"
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
        self.service = AnnouncementsService(db=self.db)
        self.current_user = _make_user(900)
        self.author_user = _make_user(901)
        self.other_user = _make_user(902)
        self.db.add(self.current_user)
        self.db.add(self.author_user)
        self.db.add(self.other_user)
        self.db.commit()

        self.original_static_dir = uploads_module.STATIC_DIR
        self.original_uploads_dir = uploads_module.UPLOADS_DIR
        self.original_attachment_storage_root = (
            announcement_storage_module.ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT
        )
        uploads_module.STATIC_DIR = Path(self.temp_dir.name) / "static"
        uploads_module.UPLOADS_DIR = uploads_module.STATIC_DIR / "uploads"
        attachment_storage_root = Path(self.temp_dir.name) / "protected_uploads"
        announcement_storage_module.ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT = (
            attachment_storage_root
        )
        announcements_router_module.ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT = (
            attachment_storage_root
        )

    def tearDown(self) -> None:
        uploads_module.STATIC_DIR = self.original_static_dir
        uploads_module.UPLOADS_DIR = self.original_uploads_dir
        announcement_storage_module.ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT = (
            self.original_attachment_storage_root
        )
        announcements_router_module.ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT = (
            self.original_attachment_storage_root
        )
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_mark_seen_is_idempotent_per_user(self) -> None:
        announcement = self._create_announcement(
            published_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        first = self.service.mark_seen(announcement.id, self.current_user)
        second = self.service.mark_seen(announcement.id, self.current_user)

        self.assertEqual(first.announcement_id, announcement.id)
        self.assertEqual(second.announcement_id, announcement.id)
        self.assertEqual(
            self.db.query(AnnouncementRead)
            .filter(
                AnnouncementRead.announcement_id == announcement.id,
                AnnouncementRead.user_id == self.current_user.id,
            )
            .count(),
            1,
        )

    def test_list_endpoint_returns_visible_items(self) -> None:
        now = datetime.now(timezone.utc)
        visible = self._seed_announcement(
            title="Visible notice",
            summary="Visible summary",
            announcement_type=AnnouncementTypeEnum.INFO,
            published_at=now - timedelta(hours=1),
        )
        self._seed_announcement(
            title="Future notice",
            summary="Future summary",
            announcement_type=AnnouncementTypeEnum.INFO,
            published_at=now + timedelta(hours=1),
        )

        with self._build_test_client(allowed_permissions={"announcements.read"}) as client:
            response = client.get(f"{API_PREFIX}/announcements")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual([item["id"] for item in payload], [visible.id])
            self.assertEqual(payload[0]["title"], "Visible notice")

    def test_include_all_requires_manage_permission(self) -> None:
        self._seed_announcement(
            title="Hidden draft",
            summary="Hidden draft summary",
            announcement_type=AnnouncementTypeEnum.INFO,
            published_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        with self._build_test_client(allowed_permissions={"announcements.read"}) as client:
            response = client.get(
                f"{API_PREFIX}/announcements",
                params={"include_all": "true"},
            )

            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.json()["detail"],
                "Announcement management permissions are required to include hidden records.",
            )

    def test_attachment_endpoints_persist_metadata_and_remove_files(self) -> None:
        announcement = self._create_announcement()
        with self._build_test_client(
            allowed_permissions={"announcements.read", "announcements.update"}
        ) as client:
            response = client.post(
                f"{API_PREFIX}/announcements/{announcement.id}/attachments",
                files=[
                    (
                        "files",
                        ("policy.pdf", b"%PDF-1.4 fake payload", "application/pdf"),
                    )
                ],
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["attachments_count"], 1)
            attachment = payload["attachments"][0]
            self.assertEqual(attachment["file_name"], "policy.pdf")
            self.assertEqual(
                attachment["file_url"],
                f"{API_PREFIX}/announcements/{announcement.id}/attachments/{attachment['id']}",
            )

            stored_record = self._get_attachment_record(attachment["id"])
            self.assertIsNotNone(stored_record)
            stored_path = announcement_storage_module.resolve_announcement_attachment_path(
                stored_record
            )
            self.assertIsNotNone(stored_path)
            self.assertTrue(stored_path.exists())

            open_response = client.get(attachment["file_url"])

            self.assertEqual(open_response.status_code, 200)
            self.assertEqual(open_response.content, b"%PDF-1.4 fake payload")

            delete_response = client.delete(
                f"{API_PREFIX}/announcements/{announcement.id}/attachments/{attachment['id']}"
            )

            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["attachments_count"], 0)
            self.assertFalse(stored_path.exists())

    def test_attachment_download_allows_other_reader(self) -> None:
        announcement = self._create_announcement()
        with self._build_test_client(
            allowed_permissions={"announcements.read", "announcements.update"},
            user_id=self.current_user.id,
        ) as uploader_client:
            upload_response = uploader_client.post(
                f"{API_PREFIX}/announcements/{announcement.id}/attachments",
                files=[
                    (
                        "files",
                        ("guide.pdf", b"shared attachment", "application/pdf"),
                    )
                ],
            )

            self.assertEqual(upload_response.status_code, 200)
            attachment_url = upload_response.json()["attachments"][0]["file_url"]

        with self._build_test_client(
            allowed_permissions={"announcements.read"},
            user_id=self.other_user.id,
        ) as reader_client:
            attachment_response = reader_client.get(attachment_url)

        self.assertEqual(attachment_response.status_code, 200)
        self.assertEqual(attachment_response.content, b"shared attachment")

    def test_attachment_download_requires_read_permission(self) -> None:
        announcement = self._create_announcement()
        with self._build_test_client(
            allowed_permissions={"announcements.read", "announcements.update"},
            user_id=self.current_user.id,
        ) as uploader_client:
            upload_response = uploader_client.post(
                f"{API_PREFIX}/announcements/{announcement.id}/attachments",
                files=[
                    (
                        "files",
                        ("guide.pdf", b"shared attachment", "application/pdf"),
                    )
                ],
            )

            self.assertEqual(upload_response.status_code, 200)
            attachment_url = upload_response.json()["attachments"][0]["file_url"]

        with self._build_test_client(
            allowed_permissions=set(),
            user_id=self.other_user.id,
        ) as unauthorized_client:
            attachment_response = unauthorized_client.get(attachment_url)

        self.assertEqual(attachment_response.status_code, 403)
        self.assertEqual(
            attachment_response.json()["detail"],
            "Permission 'announcements.read' is required.",
        )

    def test_attachment_download_hides_unpublished_announcement_from_reader(self) -> None:
        announcement = self._create_announcement(
            published_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        with self._build_test_client(
            allowed_permissions={"announcements.read", "announcements.update"},
            user_id=self.current_user.id,
        ) as manager_client:
            upload_response = manager_client.post(
                f"{API_PREFIX}/announcements/{announcement.id}/attachments",
                files=[
                    (
                        "files",
                        ("guide.pdf", b"shared attachment", "application/pdf"),
                    )
                ],
            )

            self.assertEqual(upload_response.status_code, 200)
            attachment_url = upload_response.json()["attachments"][0]["file_url"]

        with self._build_test_client(
            allowed_permissions={"announcements.read"},
            user_id=self.other_user.id,
        ) as reader_client:
            attachment_response = reader_client.get(attachment_url)

        self.assertEqual(attachment_response.status_code, 404)
        self.assertEqual(
            attachment_response.json()["detail"],
            "Announcement not found.",
        )

    def test_delete_announcement_returns_empty_204_body(self) -> None:
        announcement = self._create_announcement()

        with self._build_test_client(
            allowed_permissions={"announcements.delete"},
            user_id=self.current_user.id,
        ) as client:
            response = client.delete(f"{API_PREFIX}/announcements/{announcement.id}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

    def test_setup_defaults_seed_announcement_permissions(self) -> None:
        default_permission_codes = {
            definition["code"] for definition in SetupService.DEFAULT_PERMISSIONS
        }

        self.assertIn("announcements.view", default_permission_codes)
        self.assertIn("announcements.create", default_permission_codes)
        self.assertIn("announcements.update", default_permission_codes)
        self.assertIn("announcements.delete", default_permission_codes)

        self.assertIn(
            "announcements.view",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["EMPLOYEE"],
        )
        self.assertIn(
            "announcements.view",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["TEAM_LEADER"],
        )
        self.assertIn(
            "announcements.view",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["RH_MANAGER"],
        )

    def _create_announcement(
        self,
        *,
        published_at: datetime | None = None,
    ) -> Announcement:
        return self.service.create_announcement(
            AnnouncementCreateRequest(
                title="Policy update",
                summary="Updated handbook section",
                content="Full content",
                type=AnnouncementTypeEnum.IMPORTANT,
                is_pinned=False,
                is_active=True,
                published_at=published_at
                or (datetime.now(timezone.utc) - timedelta(minutes=5)),
                expires_at=None,
            ),
            self.author_user,
        )

    def _seed_announcement(
        self,
        *,
        title: str,
        summary: str,
        announcement_type: AnnouncementTypeEnum,
        published_at: datetime,
        is_pinned: bool = False,
        expires_at: datetime | None = None,
        is_active: bool = True,
    ) -> Announcement:
        announcement = Announcement(
            title=title,
            summary=summary,
            content=f"Content for {title}",
            type=announcement_type.value,
            is_pinned=is_pinned,
            is_active=is_active,
            published_at=published_at,
            expires_at=expires_at,
            created_by_user_id=self.author_user.id,
            updated_by_user_id=self.author_user.id,
        )
        self.db.add(announcement)
        self.db.commit()
        self.db.refresh(announcement)
        return announcement

    def _build_test_client(
        self,
        *,
        allowed_permissions: set[str],
        user_id: int | None = None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(announcements_router, prefix=API_PREFIX)
        request_user = _make_user(user_id or self.current_user.id)

        class StubPermissionsService:
            def user_has_permission(self, _user: User, permission_code: str) -> bool:
                return permission_code in allowed_permissions

        def override_announcements_service():
            db = self.session_factory()
            try:
                yield AnnouncementsService(db=db)
            finally:
                db.close()

        app.dependency_overrides[get_announcements_service] = override_announcements_service
        app.dependency_overrides[get_current_active_user] = lambda: request_user
        app.dependency_overrides[get_permissions_service] = lambda: StubPermissionsService()
        return TestClient(app)

    def _get_attachment_record(self, attachment_id: int) -> AnnouncementAttachment | None:
        self.db.expire_all()
        return self.db.get(AnnouncementAttachment, attachment_id)


if __name__ == "__main__":
    unittest.main()
