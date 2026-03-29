from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_attendance_nfc_bootstrap.db"

from app.apps.attendance.models import AttendanceStatusEnum, NfcCard
from app.apps.attendance.schemas import (
    AttendanceNfcScanIngestRequest,
    AttendanceScanIngestRequest,
)
from app.apps.attendance.service import (
    AttendanceNotFoundError,
    AttendanceService,
    AttendanceValidationError,
)
from app.apps.employees.models import Employee
from app.apps.organization.models import JobTitle
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
        self.assertEqual(daily_summary.status, AttendanceStatusEnum.INCOMPLETE.value)

    def test_nfc_scan_flow_reuses_daily_summary_logic(self) -> None:
        employee = self._seed_employee(nfc_uid="NFC-0001")

        self.service.ingest_nfc_scan_event(
            AttendanceNfcScanIngestRequest(
                nfc_uid="nfc-0001",
                reader_type="IN",
                scanned_at=datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc),
                source="nfc_terminal",
            )
        )
        raw_event, daily_summary = self.service.ingest_nfc_scan_event(
            AttendanceNfcScanIngestRequest(
                nfc_uid="nfc-0001",
                reader_type="OUT",
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
                    reader_type="IN",
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
                    reader_type="IN",
                    scanned_at=datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc),
                    source="nfc_terminal",
                )
            )

    def _seed_employee(
        self,
        *,
        nfc_uid: str | None = None,
        card_is_active: bool = True,
        employee_is_active: bool = True,
    ) -> Employee:
        next_id = int(self.db.query(User).count()) + 1
        user = _make_user(next_id)
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
                    is_active=card_is_active,
                )
            )

        self.db.commit()
        return employee


if __name__ == "__main__":
    unittest.main()
