from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_dashboard_bootstrap.db"

from app.apps.attendance.models import AttendanceDailySummary, AttendanceStatusEnum
from app.apps.auth.dependencies import get_current_active_user
from app.apps.dashboard.dependencies import get_dashboard_service
from app.apps.dashboard.router import router as dashboard_router
from app.apps.dashboard.service import DashboardService
from app.apps.employees.models import Employee
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.requests.models import RequestStatusEnum, RequestType, WorkflowRequest
from app.apps.users.models import User
from app.db.base import Base

SUPER_ADMIN_ID = 999
NORMAL_USER_ID = 1


def _make_user(user_id: int, is_super_admin: bool = False) -> User:
    return User(
        id=user_id,
        matricule=f"USR-{user_id}",
        password_hash="hash",
        first_name="Test",
        last_name=f"User{user_id}",
        email=f"user{user_id}@example.com",
        is_super_admin=is_super_admin,
        is_active=True,
        must_change_password=False,
    )


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "dashboard.db"
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
        self.admin_user = _make_user(SUPER_ADMIN_ID, is_super_admin=True)
        self.db.add(self.admin_user)
        self._seed_data()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_data(self) -> None:
        today = date.today()

        dept = Department(id=1, name="Engineering", code="ENG", description="", is_active=True)
        team = Team(id=1, name="Alpha", code="ALPHA", department_id=1, leader_user_id=None, is_active=True)
        job_title = JobTitle(id=1, name="Developer", code="DEV", hierarchical_level=1, is_active=True)

        self.db.add_all([dept, team, job_title])

        for i in range(1, 5):
            emp = Employee(
                id=i,
                user_id=i,
                matricule=f"EMP-{i:04d}",
                first_name=f"First{i}",
                last_name=f"Last{i}",
                email=f"emp{i}@example.com",
                hire_date=today,
                gender="MALE" if i % 2 == 0 else "FEMALE",
                contract_type="INTERNAL" if i <= 3 else "EXTERNAL",
                department_id=1,
                team_id=1,
                job_title_id=1,
                is_active=True,
            )
            self.db.add(emp)

        # attendance records for today
        for i in range(1, 4):
            summary = AttendanceDailySummary(
                id=i,
                employee_id=i,
                attendance_date=today,
                status=AttendanceStatusEnum.PRESENT.value,
            )
            self.db.add(summary)

        # one absent
        summary4 = AttendanceDailySummary(
            id=4,
            employee_id=4,
            attendance_date=today,
            status=AttendanceStatusEnum.ABSENT.value,
        )
        self.db.add(summary4)

        # attendance for past days
        for day_offset in range(1, 5):
            past_date = today - timedelta(days=day_offset)
            for i in range(1, 4):
                summary = AttendanceDailySummary(
                    id=i * 10 + day_offset,
                    employee_id=i,
                    attendance_date=past_date,
                    status=AttendanceStatusEnum.PRESENT.value,
                )
                self.db.add(summary)

        request_type = RequestType(
            id=1,
            code="LEAVE",
            name="Leave Request",
            description="Leave request",
            is_active=True,
        )
        pending_request = WorkflowRequest(
            id=1,
            request_type_id=1,
            requester_user_id=SUPER_ADMIN_ID,
            requester_employee_id=1,
            status=RequestStatusEnum.IN_PROGRESS.value,
        )
        self.db.add_all([request_type, pending_request])

        self.db.flush()

    def _build_test_client(self, *, can_read_dashboard: bool = True) -> TestClient:
        app = FastAPI()
        app.include_router(dashboard_router)

        app.dependency_overrides[get_current_active_user] = lambda: self.admin_user
        app.dependency_overrides[get_dashboard_service] = lambda: DashboardService(self.db)

        mock_permissions_service = unittest.mock.Mock()
        mock_permissions_service.user_has_permission.return_value = can_read_dashboard

        from app.apps.permissions.dependencies import get_permissions_service
        app.dependency_overrides[get_permissions_service] = lambda: mock_permissions_service

        return TestClient(app)

    def _clear_dashboard_data(self) -> None:
        self.db.query(WorkflowRequest).delete(synchronize_session=False)
        self.db.query(RequestType).delete(synchronize_session=False)
        self.db.query(AttendanceDailySummary).delete(synchronize_session=False)
        self.db.query(Employee).delete(synchronize_session=False)
        self.db.query(Team).delete(synchronize_session=False)
        self.db.query(Department).delete(synchronize_session=False)
        self.db.query(JobTitle).delete(synchronize_session=False)
        self.db.commit()

    # ----- Employees Summary -----

    def test_employees_summary_has_gender_breakdown(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/employees-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("employees_by_gender", data)
        total = sum(item["employee_count"] for item in data["employees_by_gender"])
        self.assertEqual(total, data["total_employees"])

    def test_employees_summary_has_contract_type_breakdown(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/employees-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("employees_by_contract_type", data)
        types = {item["contract_type"]: item["employee_count"] for item in data["employees_by_contract_type"]}
        self.assertIn("INTERNAL", types)
        self.assertIn("EXTERNAL", types)

    def test_employees_summary_has_job_title_breakdown(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/employees-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("employees_by_job_title", data)
        self.assertGreater(len(data["employees_by_job_title"]), 0)
        self.assertEqual(data["employees_by_job_title"][0]["job_title_code"], "DEV")

    # ----- Attendance Summary -----

    def test_attendance_summary_has_attendance_rate(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/attendance-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("attendance_rate", data["today"])
        self.assertGreater(data["today"]["attendance_rate"], 0)

    def test_attendance_summary_daily_stats_have_rate(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/attendance-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for point in data["daily_stats"]:
            self.assertIn("attendance_rate", point)
            self.assertGreaterEqual(point["attendance_rate"], 0)

    def test_attendance_summary_totals_have_rate(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/attendance-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("attendance_rate", data["totals"])
        self.assertGreater(data["totals"]["attendance_rate"], 0)

    # ----- Request Trend -----

    def test_requests_summary_has_trend(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/requests-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("request_trend", data)
        self.assertIsInstance(data["request_trend"], list)

    # ----- Clean Attendance Dashboard -----

    def test_attendance_dashboard_returns_today_stats(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/attendance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["today"]["present_count"], 3)
        self.assertEqual(data["today"]["absent_count"], 1)
        self.assertEqual(data["today"]["incomplete_count"], 0)
        self.assertEqual(data["today"]["leave_count"], 0)
        self.assertEqual(data["today"]["attendance_rate"], 75.0)

    def test_attendance_dashboard_returns_recent_activity(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/attendance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("recent_activity", data)
        self.assertGreater(len(data["recent_activity"]), 0)
        first_item = data["recent_activity"][0]
        self.assertIn("attendance_id", first_item)
        self.assertIn("employee_matricule", first_item)
        self.assertIn("employee_name", first_item)
        self.assertIn("status", first_item)

    def test_attendance_dashboard_empty_database(self) -> None:
        self._clear_dashboard_data()
        client = self._build_test_client()
        response = client.get("/dashboard/attendance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["today"]["total_active_employees"], 0)
        self.assertEqual(data["today"]["present_count"], 0)
        self.assertEqual(data["today"]["absent_count"], 0)
        self.assertEqual(data["today"]["attendance_rate"], 0.0)
        self.assertEqual(data["recent_activity"], [])

    def test_attendance_dashboard_permission_denied(self) -> None:
        client = self._build_test_client(can_read_dashboard=False)
        response = client.get("/dashboard/attendance")
        self.assertEqual(response.status_code, 403)

    # ----- Clean Employee Stats Dashboard -----

    def test_employee_stats_has_gender_breakdown(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/employees")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        genders = {item["gender"]: item["employee_count"] for item in data["employees_by_gender"]}
        self.assertEqual(genders["FEMALE"], 2)
        self.assertEqual(genders["MALE"], 2)

    def test_employee_stats_has_contract_type_breakdown(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/employees")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        contract_types = {item["contract_type"]: item["employee_count"] for item in data["employees_by_contract_type"]}
        self.assertEqual(contract_types["INTERNAL"], 3)
        self.assertEqual(contract_types["EXTERNAL"], 1)

    def test_employee_stats_has_department_team_and_job_title_breakdowns(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/employees")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["employees_by_department"][0]["department_code"], "ENG")
        self.assertEqual(data["employees_by_department"][0]["employee_count"], 4)
        self.assertEqual(data["employees_by_team"][0]["team_code"], "ALPHA")
        self.assertEqual(data["employees_by_team"][0]["employee_count"], 4)
        self.assertEqual(data["employees_by_job_title"][0]["job_title_code"], "DEV")
        self.assertEqual(data["employees_by_job_title"][0]["employee_count"], 4)

    def test_employee_stats_empty_database(self) -> None:
        self._clear_dashboard_data()
        client = self._build_test_client()
        response = client.get("/dashboard/employees")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_employees"], 0)
        self.assertEqual(data["active_employees"], 0)
        self.assertEqual(data["inactive_employees"], 0)
        self.assertEqual(data["employees_by_department"], [])
        self.assertEqual(data["employees_by_team"], [])
        self.assertEqual(data["employees_by_gender"], [])
        self.assertEqual(data["employees_by_contract_type"], [])
        self.assertEqual(data["employees_by_job_title"], [])

    def test_employee_stats_permission_denied(self) -> None:
        client = self._build_test_client(can_read_dashboard=False)
        response = client.get("/dashboard/employees")
        self.assertEqual(response.status_code, 403)

    # ----- Company Stats Dashboard -----

    def test_company_stats_has_company_totals(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/company-stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_employees"], 4)
        self.assertEqual(data["active_employees"], 4)
        self.assertEqual(data["inactive_employees"], 0)
        self.assertEqual(data["total_departments"], 1)
        self.assertEqual(data["total_teams"], 1)
        self.assertEqual(data["total_job_titles"], 1)

    def test_company_stats_has_attendance_totals_today(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/company-stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["present_today"], 3)
        self.assertEqual(data["absent_today"], 1)
        self.assertEqual(data["incomplete_count"], 0)
        self.assertEqual(data["on_leave_today"], 0)
        self.assertEqual(data["attendance_rate_today"], 75.0)

    def test_company_stats_has_pending_requests_count(self) -> None:
        client = self._build_test_client()
        response = client.get("/dashboard/company-stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pending_requests_count"], 1)

    def test_company_stats_empty_database(self) -> None:
        self._clear_dashboard_data()
        client = self._build_test_client()
        response = client.get("/dashboard/company-stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_employees"], 0)
        self.assertEqual(data["total_departments"], 0)
        self.assertEqual(data["total_teams"], 0)
        self.assertEqual(data["total_job_titles"], 0)
        self.assertEqual(data["pending_requests_count"], 0)
        self.assertEqual(data["present_today"], 0)
        self.assertEqual(data["absent_today"], 0)
        self.assertEqual(data["attendance_rate_today"], 0.0)

    def test_company_stats_permission_denied(self) -> None:
        client = self._build_test_client(can_read_dashboard=False)
        response = client.get("/dashboard/company-stats")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
