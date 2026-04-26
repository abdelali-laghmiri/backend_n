from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_permissions_catalog_bootstrap.db"

from app.apps.employees.models import Employee
from app.apps.organization.models import JobTitle
from app.apps.permissions.catalog import (
    CANONICAL_JOB_TITLES,
    CANONICAL_PERMISSIONS,
    ROLE_PERMISSION_MATRIX,
)
from app.apps.permissions.models import JobTitlePermissionAssignment, Permission
from app.apps.permissions.service import PermissionsService
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.db.base import Base


class PermissionsCatalogTests(unittest.TestCase):
    def test_catalog_includes_required_company_roles(self) -> None:
        job_title_codes = {definition["code"] for definition in CANONICAL_JOB_TITLES}
        self.assertEqual(
            job_title_codes,
            {
                "SUPER_ADMIN",
                "RH_MANAGER",
                "HR_ASSISTANT",
                "ATTENDANCE_MANAGER",
                "FINANCE_PAYROLL",
                "DEPARTMENT_MANAGER",
                "TEAM_LEADER",
                "EMPLOYEE",
            },
        )

    def test_employee_role_keeps_core_self_service_permissions(self) -> None:
        employee_permissions = set(ROLE_PERMISSION_MATRIX["EMPLOYEE"])
        self.assertTrue(
            {
                "dashboard.view",
                "profile.view",
                "attendance.view",
                "requests.create",
                "requests.view",
                "announcements.view",
            }.issubset(employee_permissions)
        )

    def test_setup_service_uses_shared_catalog_defaults(self) -> None:
        self.assertEqual(SetupService.DEFAULT_JOB_TITLES, CANONICAL_JOB_TITLES)
        self.assertEqual(SetupService.DEFAULT_PERMISSIONS, CANONICAL_PERMISSIONS)
        self.assertEqual(SetupService.DEFAULT_JOB_TITLE_PERMISSION_CODES, ROLE_PERMISSION_MATRIX)


class PermissionsResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "permissions_catalog.db"
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
        self.permissions_service = PermissionsService(db=self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_super_admin_receives_full_permission_list(self) -> None:
        for definition in CANONICAL_PERMISSIONS:
            self.db.add(
                Permission(
                    code=definition["code"],
                    name=definition["name"],
                    description=definition["description"],
                    module=definition["module"],
                    is_active=True,
                )
            )
        super_admin = User(
            matricule="SA-TEST",
            password_hash="hash",
            first_name="System",
            last_name="Admin",
            email="sa-test@example.com",
            is_super_admin=True,
            is_active=True,
            must_change_password=False,
        )
        self.db.add(super_admin)
        self.db.commit()

        effective_permissions = self.permissions_service.resolve_effective_permissions(super_admin)
        expected_codes = sorted(definition["code"] for definition in CANONICAL_PERMISSIONS)

        self.assertTrue(effective_permissions.has_full_access)
        self.assertEqual(effective_permissions.permissions, expected_codes)

    def test_legacy_manage_requests_alias_maps_to_requests_manage(self) -> None:
        permission = Permission(
            code="requests.manage",
            name="Manage request configuration",
            description="Manage request types.",
            module="requests",
            is_active=True,
        )
        job_title = JobTitle(
            name="Department Manager",
            code="DEPARTMENT_MANAGER",
            description="Department manager role",
            hierarchical_level=4,
            is_active=True,
        )
        user = User(
            matricule="USR-001",
            password_hash="hash",
            first_name="Request",
            last_name="Manager",
            email="request-manager@example.com",
            is_super_admin=False,
            is_active=True,
            must_change_password=False,
        )
        self.db.add_all([permission, job_title, user])
        self.db.commit()
        self.db.refresh(permission)
        self.db.refresh(job_title)
        self.db.refresh(user)

        employee = Employee(
            user_id=user.id,
            matricule="EMP-001",
            first_name="Request",
            last_name="Manager",
            email="request-manager@example.com",
            phone=None,
            image=None,
            hire_date=date(2024, 1, 1),
            available_leave_balance_days=18,
            department_id=None,
            team_id=None,
            job_title_id=job_title.id,
            is_active=True,
        )
        assignment = JobTitlePermissionAssignment(
            job_title_id=job_title.id,
            permission_id=permission.id,
        )
        self.db.add_all([employee, assignment])
        self.db.commit()

        self.assertTrue(self.permissions_service.user_has_permission(user, "manage_requests"))
        self.assertFalse(self.permissions_service.user_has_permission(user, "create_requests"))


if __name__ == "__main__":
    unittest.main()
