from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_attendance_nfc_bootstrap.db"

from app.apps.attendance.dependencies import get_attendance_service
from app.apps.attendance.router import router as attendance_router
from app.apps.attendance.models import (
    AttendanceStatusEnum,
    NfcCard,
    NfcCardStatusEnum,
    NfcCardTypeEnum,
)
from app.apps.attendance.schemas import (
    AttendanceEventTypeEnum,
    AttendanceNfcCardAssignRequest,
    AttendanceNfcScanIngestRequest,
    AttendanceScanIngestRequest,
)
from app.apps.attendance.service import (
    AttendanceConflictError,
    AttendanceNotFoundError,
    AttendanceService,
    AttendanceValidationError,
)
from app.apps.auth.dependencies import get_current_active_user
from app.apps.employees.models import Employee
from app.apps.organization.models import JobTitle
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.forgot_badge.models import TemporaryNfcAssignment
from app.apps.forgot_badge.schemas import ForgotBadgeRequestApproveRequest
from app.apps.forgot_badge.service import ForgotBadgeService, ForgotBadgeConflictError
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.db.base import Base


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


def _make_job_title(job_title_id: int) -> JobTitle:
    return JobTitle(
        id=job_title_id,
        name="Operator",
        code=f"OPERATOR_{job_title_id}",
        description=None,
        hierarchical_level=1,
        is_active=True,
    )


def _make_employee(
    employee_id: int,
    *,
    user_id: int,
    job_title_id: int,
    is_active: bool = True,
) -> Employee:
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
        is_active=is_active,
    )


class AttendanceNfcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "attendance_nfc.db"
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
        self.service = AttendanceService(db=self.db)
        self.forgot_badge_service = ForgotBadgeService(db=self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_matricule_scan_flow_still_works(self) -> None:
        employee = self._seed_employee()

        scanned_at = datetime(2026, 3, 29, 8, 15, tzinfo=timezone.utc)
        raw_event, daily_summary = self.service.ingest_scan_event(
            AttendanceScanIngestRequest(
                matricule=employee.matricule.lower(),
                reader_type="IN",
                scanned_at=scanned_at,
                source="legacy_terminal",
            )
        )

        self.assertEqual(raw_event.employee_id, employee.id)
        self.assertEqual(raw_event.user_id, employee.user_id)
        self.assertEqual(daily_summary.employee_id, employee.id)
        self.assertEqual(daily_summary.first_check_in_at, scanned_at)
        self.assertIsNone(daily_summary.last_check_out_at)
        self.assertEqual(daily_summary.status, AttendanceStatusEnum.PRESENT.value)

    def test_nfc_scan_flow_reuses_daily_summary_logic(self) -> None:
        employee = self._seed_employee(nfc_uid="NFC-0001")

        self.service.ingest_nfc_scan_event(
            AttendanceNfcScanIngestRequest(
                nfc_uid="nfc-0001",
                attendance_type=AttendanceEventTypeEnum.CHECK_IN,
                scanned_at=datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc),
                source="nfc_terminal",
            )
        )
        raw_event, daily_summary = self.service.ingest_nfc_scan_event(
            AttendanceNfcScanIngestRequest(
                nfc_uid="nfc-0001",
                attendance_type=AttendanceEventTypeEnum.CHECK_OUT,
                scanned_at=datetime(2026, 3, 29, 17, 30, tzinfo=timezone.utc),
                source="nfc_terminal",
            )
        )

        self.assertEqual(raw_event.employee_id, employee.id)
        self.assertEqual(raw_event.user_id, employee.user_id)
        self.assertEqual(daily_summary.employee_id, employee.id)
        self.assertEqual(daily_summary.status, AttendanceStatusEnum.PRESENT.value)
        self.assertEqual(daily_summary.worked_duration_minutes, 570)

    def test_nfc_scan_rejects_inactive_card(self) -> None:
        self._seed_employee(nfc_uid="NFC-INACTIVE", card_is_active=False)

        with self.assertRaises(AttendanceValidationError):
            self.service.ingest_nfc_scan_event(
                AttendanceNfcScanIngestRequest(
                    nfc_uid="nfc-inactive",
                    attendance_type=AttendanceEventTypeEnum.CHECK_IN,
                    scanned_at=datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc),
                    source="nfc_terminal",
                )
            )

    def test_nfc_scan_rejects_unknown_uid(self) -> None:
        self._seed_employee()

        with self.assertRaises(AttendanceNotFoundError):
            self.service.ingest_nfc_scan_event(
                AttendanceNfcScanIngestRequest(
                    nfc_uid="missing-card",
                    attendance_type=AttendanceEventTypeEnum.CHECK_IN,
                    scanned_at=datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc),
                    source="nfc_terminal",
                )
            )

    def test_assign_nfc_card_creates_active_mapping(self) -> None:
        employee = self._seed_employee()

        nfc_card = self.service.assign_nfc_card(
            AttendanceNfcCardAssignRequest(
                employee_id=employee.id,
                nfc_uid="04aabbccdd11",
            )
        )

        self.assertEqual(nfc_card.employee_id, employee.id)
        self.assertEqual(nfc_card.nfc_uid, "04AABBCCDD11")
        self.assertTrue(nfc_card.is_active)
        self.assertEqual(nfc_card.card_type, NfcCardTypeEnum.PERMANENT.value)
        self.assertEqual(nfc_card.status, NfcCardStatusEnum.ASSIGNED.value)

    def test_assign_nfc_card_is_idempotent_for_same_employee_and_card(self) -> None:
        employee = self._seed_employee(nfc_uid="04AABBCCDD11")

        first_card = self.db.query(NfcCard).filter(NfcCard.employee_id == employee.id).one()
        second_card = self.service.assign_nfc_card(
            AttendanceNfcCardAssignRequest(
                employee_id=employee.id,
                nfc_uid="04aabbccdd11",
            )
        )

        self.assertEqual(second_card.id, first_card.id)
        self.assertEqual(self.db.query(NfcCard).count(), 1)

    def test_assign_nfc_card_rejects_duplicate_uid_for_other_employee(self) -> None:
        self._seed_employee(nfc_uid="04AABBCCDD11")
        other_employee = self._seed_employee()

        with self.assertRaises(AttendanceConflictError):
            self.service.assign_nfc_card(
                AttendanceNfcCardAssignRequest(
                    employee_id=other_employee.id,
                    nfc_uid="04AABBCCDD11",
                )
            )

    def test_assign_nfc_card_rejects_second_active_card_for_same_employee(self) -> None:
        employee = self._seed_employee(nfc_uid="CARD-ONE")

        with self.assertRaises(AttendanceConflictError):
            self.service.assign_nfc_card(
                AttendanceNfcCardAssignRequest(
                    employee_id=employee.id,
                    nfc_uid="CARD-TWO",
                )
            )

    def test_assign_nfc_card_rejects_inactive_employee(self) -> None:
        employee = self._seed_employee(employee_is_active=False)

        with self.assertRaises(AttendanceValidationError):
            self.service.assign_nfc_card(
                AttendanceNfcCardAssignRequest(
                    employee_id=employee.id,
                    nfc_uid="04AABBCCDD11",
                )
            )

    def test_assign_nfc_card_endpoint_requires_permission(self) -> None:
        employee = self._seed_employee()
        client = self._build_test_client(allowed_permissions=set())

        response = client.post(
            "/attendance/nfc-cards/assign",
            json={
                "employee_id": employee.id,
                "nfc_uid": "04AABBCCDD11",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Permission 'attendance.nfc.assign_card' is required.",
        )

    def test_assign_nfc_card_endpoint_assigns_card_with_permission(self) -> None:
        employee = self._seed_employee()
        client = self._build_test_client(
            allowed_permissions={"attendance.nfc.assign_card"}
        )

        response = client.post(
            "/attendance/nfc-cards/assign",
            json={
                "employee_id": employee.id,
                "nfc_uid": "04aabbccdd11",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["employee_id"], employee.id)
        self.assertEqual(response.json()["employee_matricule"], employee.matricule)
        self.assertEqual(response.json()["nfc_uid"], "04AABBCCDD11")

    def test_setup_defaults_seed_nfc_assign_permission_for_rh_manager_only(self) -> None:
        default_permission_codes = {
            definition["code"] for definition in SetupService.DEFAULT_PERMISSIONS
        }

        self.assertIn("attendance.nfc.assign_card", default_permission_codes)
        self.assertIn(
            "attendance.nfc.assign_card",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["RH_MANAGER"],
        )
        self.assertNotIn(
            "attendance.nfc.assign_card",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["DEPARTMENT_MANAGER"],
        )
        self.assertNotIn(
            "attendance.nfc.assign_card",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["TEAM_LEADER"],
        )
        self.assertNotIn(
            "attendance.nfc.assign_card",
            SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES["EMPLOYEE"],
        )

    def test_list_available_temporary_cards_returns_only_existing_available_pool(self) -> None:
        self._seed_employee(nfc_uid="PERM-001")
        available_card = self._seed_temporary_card("TEMP-001", "TEMP-UID-001")
        assigned_card = self._seed_temporary_card(
            "TEMP-002",
            "TEMP-UID-002",
            status=NfcCardStatusEnum.ASSIGNED.value,
        )
        disabled_card = self._seed_temporary_card(
            "TEMP-003",
            "TEMP-UID-003",
            is_active=False,
            status=NfcCardStatusEnum.DISABLED.value,
        )
        permanent_card = self.db.query(NfcCard).filter(NfcCard.nfc_uid == "PERM-001").one()

        cards = self.service.list_nfc_cards(
            card_type=NfcCardTypeEnum.TEMPORARY,
            status=NfcCardStatusEnum.AVAILABLE,
            valid_for_date=date(2026, 3, 29),
        )

        self.assertEqual([card.id for card in cards], [available_card.id])
        self.assertNotIn(assigned_card.id, [card.id for card in cards])
        self.assertNotIn(disabled_card.id, [card.id for card in cards])
        self.assertNotIn(permanent_card.id, [card.id for card in cards])

    def test_assigned_temporary_card_disappears_from_available_list(self) -> None:
        employee = self._seed_employee()
        manager = self._seed_employee()
        card = self._seed_temporary_card("TEMP-001", "TEMP-UID-001")
        request = self._seed_forgot_badge_request(employee_id=employee.id, user_id=employee.user_id)

        self.forgot_badge_service.approve_request(
            request.id,
            ForgotBadgeRequestApproveRequest(
                nfc_card_id=card.id,
                valid_for_date=date(2026, 3, 29),
            ),
            self.db.get(User, manager.user_id),
        )

        cards = self.service.list_nfc_cards(
            card_type=NfcCardTypeEnum.TEMPORARY,
            status=NfcCardStatusEnum.AVAILABLE,
            valid_for_date=date(2026, 3, 29),
        )

        self.assertEqual(cards, [])
        self.assertEqual(self.db.get(NfcCard, card.id).status, NfcCardStatusEnum.ASSIGNED.value)

    def test_checkout_releases_temporary_card_and_it_becomes_available_again(self) -> None:
        employee = self._seed_employee()
        manager = self._seed_employee()
        card = self._seed_temporary_card("TEMP-001", "TEMP-UID-001")
        request = self._seed_forgot_badge_request(employee_id=employee.id, user_id=employee.user_id)

        self.forgot_badge_service.approve_request(
            request.id,
            ForgotBadgeRequestApproveRequest(
                nfc_card_id=card.id,
                valid_for_date=date(2026, 3, 29),
            ),
            self.db.get(User, manager.user_id),
        )

        self.service.ingest_nfc_scan_event(
            AttendanceNfcScanIngestRequest(
                nfc_uid="temp-uid-001",
                attendance_type=AttendanceEventTypeEnum.CHECK_IN,
                scanned_at=datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc),
                source="nfc_terminal",
            )
        )
        self.service.ingest_nfc_scan_event(
            AttendanceNfcScanIngestRequest(
                nfc_uid="temp-uid-001",
                attendance_type=AttendanceEventTypeEnum.CHECK_OUT,
                scanned_at=datetime(2026, 3, 29, 17, 0, tzinfo=timezone.utc),
                source="nfc_terminal",
            )
        )

        assignment = self.db.query(TemporaryNfcAssignment).filter(
            TemporaryNfcAssignment.nfc_card_id == card.id
        ).one()
        cards = self.service.list_nfc_cards(
            card_type=NfcCardTypeEnum.TEMPORARY,
            status=NfcCardStatusEnum.AVAILABLE,
            valid_for_date=date(2026, 3, 29),
        )

        self.assertEqual(assignment.status, "USED")
        self.assertEqual(self.db.get(NfcCard, card.id).status, NfcCardStatusEnum.AVAILABLE.value)
        self.assertEqual([listed_card.id for listed_card in cards], [card.id])

    def test_cannot_assign_same_temporary_card_to_two_active_requests(self) -> None:
        employee_one = self._seed_employee()
        employee_two = self._seed_employee()
        manager = self._seed_employee()
        card = self._seed_temporary_card("TEMP-001", "TEMP-UID-001")
        request_one = self._seed_forgot_badge_request(
            employee_id=employee_one.id,
            user_id=employee_one.user_id,
        )
        request_two = self._seed_forgot_badge_request(
            employee_id=employee_two.id,
            user_id=employee_two.user_id,
        )

        manager_user = self.db.get(User, manager.user_id)
        self.forgot_badge_service.approve_request(
            request_one.id,
            ForgotBadgeRequestApproveRequest(
                nfc_card_id=card.id,
                valid_for_date=date(2026, 3, 29),
            ),
            manager_user,
        )

        with self.assertRaises(ForgotBadgeConflictError):
            self.forgot_badge_service.approve_request(
                request_two.id,
                ForgotBadgeRequestApproveRequest(
                    nfc_card_id=card.id,
                    valid_for_date=date(2026, 3, 29),
                ),
                manager_user,
            )

    def test_list_temporary_cards_endpoint_requires_permission(self) -> None:
        self._seed_temporary_card("TEMP-001", "TEMP-UID-001")
        client = self._build_test_client(allowed_permissions=set())

        response = client.get("/attendance/nfc-cards?type=TEMPORARY&status=AVAILABLE")

        self.assertEqual(response.status_code, 403)

    def test_list_temporary_cards_endpoint_returns_available_cards(self) -> None:
        self._seed_temporary_card("TEMP-001", "TEMP-UID-001")
        client = self._build_test_client(allowed_permissions={"attendance.nfc.view_cards"})

        response = client.get("/attendance/nfc-cards?type=TEMPORARY&status=AVAILABLE")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["label"], "TEMP-001")
        self.assertEqual(payload[0]["type"], "TEMPORARY")
        self.assertEqual(payload[0]["status"], "AVAILABLE")

    def _seed_employee(
        self,
        *,
        employee_id: int | None = None,
        user_id: int | None = None,
        nfc_uid: str | None = None,
        card_is_active: bool = True,
        employee_is_active: bool = True,
    ) -> Employee:
        next_id = employee_id or int(self.db.query(User).count()) + 1
        user = _make_user(user_id or next_id)
        job_title = _make_job_title(next_id)
        employee = _make_employee(
            next_id,
            user_id=user.id,
            job_title_id=job_title.id,
            is_active=employee_is_active,
        )
        self.db.add(user)
        self.db.add(job_title)
        self.db.add(employee)

        if nfc_uid is not None:
            self.db.add(
                NfcCard(
                    employee_id=employee.id,
                    nfc_uid=nfc_uid,
                    card_type=NfcCardTypeEnum.PERMANENT.value,
                    status=NfcCardStatusEnum.ASSIGNED.value,
                    is_active=card_is_active,
                )
            )

        self.db.commit()
        return employee

    def _seed_temporary_card(
        self,
        label: str,
        nfc_uid: str,
        *,
        is_active: bool = True,
        status: str = NfcCardStatusEnum.AVAILABLE.value,
    ) -> NfcCard:
        card = NfcCard(
            employee_id=None,
            nfc_uid=nfc_uid,
            label=label,
            card_type=NfcCardTypeEnum.TEMPORARY.value,
            status=status,
            is_active=is_active,
        )
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    def _seed_forgot_badge_request(self, *, employee_id: int, user_id: int) -> object:
        from app.apps.forgot_badge.models import ForgotBadgeRequest

        request = ForgotBadgeRequest(
            employee_id=employee_id,
            user_id=user_id,
            status="PENDING",
            reason="Forgot badge",
            requested_at=datetime(2026, 3, 29, 7, 45, tzinfo=timezone.utc),
        )
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def _build_test_client(self, *, allowed_permissions: set[str]) -> TestClient:
        app = FastAPI()
        app.include_router(attendance_router)
        current_user = _make_user(999)

        class StubPermissionsService:
            def user_has_permission(self, _user: User, permission_code: str) -> bool:
                return permission_code in allowed_permissions

        app.dependency_overrides[get_attendance_service] = lambda: self.service
        app.dependency_overrides[get_current_active_user] = lambda: current_user
        app.dependency_overrides[get_permissions_service] = lambda: StubPermissionsService()
        return TestClient(app)


if __name__ == "__main__":
    unittest.main()
