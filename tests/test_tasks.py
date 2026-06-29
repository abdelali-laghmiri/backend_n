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

os.environ["DATABASE_URL"] = "sqlite:///./test_tasks_bootstrap.db"

from app.apps.attendance.models import AttendanceDailySummary, AttendanceStatusEnum
from app.apps.auth.dependencies import get_current_active_user
from app.apps.employees.models import Employee
from app.apps.organization.models import JobTitle
from app.apps.permissions.dependencies import get_permissions_service
from app.apps.tasks.dependencies import get_tasks_service
from app.apps.tasks.models import EmployeeTask, TaskPriorityEnum, TaskStatusEnum
from app.apps.tasks.router import router as tasks_router
from app.apps.tasks.service import TasksService
from app.apps.users.models import User
from app.db.base import Base


class TasksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "tasks.db"
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
        self.user = User(
            id=1,
            matricule="EMP-0001",
            password_hash="hash",
            first_name="Lina",
            last_name="Zeroual",
            email="lina@example.com",
            is_super_admin=False,
            is_active=True,
            must_change_password=False,
        )
        self.db.add(self.user)
        self._seed_data()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_data(self) -> None:
        today = date.today()
        self.db.add(
            JobTitle(
                id=1,
                name="Employee",
                code="EMPLOYEE",
                hierarchical_level=1,
                is_active=True,
            )
        )
        employee = Employee(
            id=1,
            user_id=1,
            matricule="EMP-0001",
            first_name="Lina",
            last_name="Zeroual",
            email="lina@example.com",
            hire_date=today,
            gender="FEMALE",
            contract_type="INTERNAL",
            job_title_id=1,
            is_active=True,
        )
        self.db.add(employee)
        self.db.add(
            AttendanceDailySummary(
                id=1,
                employee_id=1,
                attendance_date=today,
                status=AttendanceStatusEnum.PRESENT.value,
                worked_duration_minutes=480,
            )
        )
        self.db.add_all(
            [
                EmployeeTask(
                    id=1,
                    employee_id=1,
                    created_by_user_id=1,
                    title="Review attendance status",
                    description="Check today's presence status.",
                    status=TaskStatusEnum.TODO.value,
                    priority=TaskPriorityEnum.HIGH.value,
                    due_date=today,
                ),
                EmployeeTask(
                    id=2,
                    employee_id=1,
                    created_by_user_id=1,
                    title="Complete daily handover",
                    status=TaskStatusEnum.DONE.value,
                    priority=TaskPriorityEnum.MEDIUM.value,
                    due_date=today - timedelta(days=1),
                ),
            ]
        )

    def _build_test_client(self, *, allowed: bool = True) -> TestClient:
        app = FastAPI()
        app.include_router(tasks_router)
        app.dependency_overrides[get_current_active_user] = lambda: self.user
        app.dependency_overrides[get_tasks_service] = lambda: TasksService(self.db)

        mock_permissions_service = unittest.mock.Mock()
        mock_permissions_service.user_has_permission.return_value = allowed
        app.dependency_overrides[get_permissions_service] = lambda: mock_permissions_service

        return TestClient(app)

    def test_mobile_summary_returns_attendance_and_tasks(self) -> None:
        client = self._build_test_client()
        response = client.get("/tasks/my-summary")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["employee"]["matricule"], "EMP-0001")
        self.assertEqual(data["attendance"]["status"], "present")
        self.assertEqual(data["task_stats"]["total"], 2)
        self.assertEqual(data["task_stats"]["open"], 1)
        self.assertEqual(data["task_stats"]["done"], 1)
        self.assertEqual(len(data["tasks"]), 2)

    def test_complete_task_marks_only_own_task_done(self) -> None:
        client = self._build_test_client()
        response = client.post("/tasks/1/complete")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "done")
        self.db.refresh(self.db.get(EmployeeTask, 1))
        self.assertEqual(self.db.get(EmployeeTask, 1).status, TaskStatusEnum.DONE.value)

    def test_summary_requires_tasks_permission(self) -> None:
        client = self._build_test_client(allowed=False)
        response = client.get("/tasks/my-summary")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
