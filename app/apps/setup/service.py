from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
from app.apps.employees.schemas import EmployeeCreateRequest, EmployeeUpdateRequest
from app.apps.employees.service import (
    EmployeesConflictError,
    EmployeesNotFoundError,
    EmployeesService,
    EmployeesValidationError,
)
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.organization.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    JobTitleCreateRequest,
    JobTitleUpdateRequest,
    TeamCreateRequest,
    TeamUpdateRequest,
)
from app.apps.organization.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationService,
    OrganizationValidationError,
)
from app.apps.permissions.models import Permission
from app.apps.permissions.schemas import (
    JobTitlePermissionAssignmentRequest,
    PermissionCreateRequest,
    PermissionUpdateRequest,
)
from app.apps.permissions.service import (
    PermissionsConflictError,
    PermissionsNotFoundError,
    PermissionsService,
    PermissionsValidationError,
)
from app.apps.setup.models import InstallationState, utcnow
from app.apps.users.models import User
from app.core.config import Settings
from app.core.security import PasswordManager


class SetupAlreadyInitializedError(RuntimeError):
    """Raised when a locked setup action is attempted after completion."""


class SetupConfigurationError(RuntimeError):
    """Raised when required bootstrap configuration is missing."""


class SetupInitializationError(RuntimeError):
    """Raised when initialization cannot complete safely."""


class SetupValidationError(RuntimeError):
    """Raised when wizard input or required setup data is invalid."""


class SetupService:
    """Service layer for bootstrap setup and the first-installation wizard."""

    INSTALLATION_STATE_ID = 1
    DEFAULT_INITIAL_LEAVE_BALANCE_DAYS = 18

    DEFAULT_JOB_TITLES = (
        {
            "key": "rh_manager",
            "code": "RH_MANAGER",
            "name": "RH Manager",
            "description": "Operational HR manager for requests, attendance, and employee administration.",
            "hierarchical_level": 4,
        },
        {
            "key": "department_manager",
            "code": "DEPARTMENT_MANAGER",
            "name": "Department Manager",
            "description": "Department-level manager for approvals and reporting.",
            "hierarchical_level": 3,
        },
        {
            "key": "team_leader",
            "code": "TEAM_LEADER",
            "name": "Team Leader",
            "description": "Team-level manager responsible for daily supervision and team performance entry.",
            "hierarchical_level": 2,
        },
        {
            "key": "employee",
            "code": "EMPLOYEE",
            "name": "Employee",
            "description": "Standard employee profile for request submission.",
            "hierarchical_level": 1,
        },
    )

    DEFAULT_PERMISSIONS = (
        {
            "code": "organization.read",
            "name": "Read organization",
            "description": "View departments, teams, and job titles.",
            "module": "organization",
        },
        {
            "code": "organization.read_hierarchy",
            "name": "Read organization hierarchy",
            "description": "View hierarchy trees for the current user and the full company organigram.",
            "module": "organization",
        },
        {
            "code": "organization.create",
            "name": "Create organization records",
            "description": "Create departments, teams, and job titles.",
            "module": "organization",
        },
        {
            "code": "organization.update",
            "name": "Update organization records",
            "description": "Update departments, teams, and job titles.",
            "module": "organization",
        },
        {
            "code": "organization.deactivate",
            "name": "Deactivate organization records",
            "description": "Deactivate departments, teams, and job titles.",
            "module": "organization",
        },
        {
            "code": "employees.read",
            "name": "Read employees",
            "description": "View employee profiles.",
            "module": "employees",
        },
        {
            "code": "employees.create",
            "name": "Create employees",
            "description": "Create employee profiles and linked accounts.",
            "module": "employees",
        },
        {
            "code": "employees.update",
            "name": "Update employees",
            "description": "Update employee profiles and linked accounts.",
            "module": "employees",
        },
        {
            "code": "permissions.read",
            "name": "Read permissions",
            "description": "View permission catalog entries and job-title assignments.",
            "module": "permissions",
        },
        {
            "code": "permissions.create",
            "name": "Create permissions",
            "description": "Create new permission catalog entries.",
            "module": "permissions",
        },
        {
            "code": "permissions.update",
            "name": "Update permissions",
            "description": "Update permission catalog entries.",
            "module": "permissions",
        },
        {
            "code": "permissions.assign",
            "name": "Assign permissions",
            "description": "Replace permission sets assigned to job titles.",
            "module": "permissions",
        },
        {
            "code": "announcements.read",
            "name": "Read announcements",
            "description": "Read company-wide announcements visible to the current user.",
            "module": "announcements",
        },
        {
            "code": "announcements.create",
            "name": "Create announcements",
            "description": "Create company-wide announcements.",
            "module": "announcements",
        },
        {
            "code": "announcements.update",
            "name": "Update announcements",
            "description": "Update company-wide announcements and their attachments.",
            "module": "announcements",
        },
        {
            "code": "announcements.delete",
            "name": "Delete announcements",
            "description": "Delete company-wide announcements by deactivating them.",
            "module": "announcements",
        },
        {
            "code": "requests.read",
            "name": "Read requests",
            "description": "Read request records visible to the current user.",
            "module": "requests",
        },
        {
            "code": "requests.create",
            "name": "Create requests",
            "description": "Submit new workflow requests.",
            "module": "requests",
        },
        {
            "code": "requests.approve",
            "name": "Approve requests",
            "description": "Approve or reject the current request step.",
            "module": "requests",
        },
        {
            "code": "requests.read_my_approvals",
            "name": "Read my approval history",
            "description": "Read request approval or rejection actions personally performed by the current user.",
            "module": "requests",
        },
        {
            "code": "requests.manage",
            "name": "Manage request configuration",
            "description": "Manage request types, request fields, and workflow steps.",
            "module": "requests",
        },
        {
            "code": "requests.read_all",
            "name": "Read all requests",
            "description": "Read all requests without visibility restrictions.",
            "module": "requests",
        },
        {
            "code": "attendance.read",
            "name": "Read attendance",
            "description": "Read attendance daily summaries and monthly reports.",
            "module": "attendance",
        },
        {
            "code": "attendance.ingest",
            "name": "Ingest attendance events",
            "description": "Submit external attendance scan events.",
            "module": "attendance",
        },
        {
            "code": "attendance.nfc.assign_card",
            "name": "Assign NFC cards",
            "description": "Attach NFC cards to employees for attendance identification.",
            "module": "attendance",
        },
        {
            "code": "attendance.reports.generate",
            "name": "Generate attendance reports",
            "description": "Generate monthly attendance reports from daily summaries.",
            "module": "attendance",
        },
        {
            "code": "performance.read",
            "name": "Read performance",
            "description": "Read team performance records.",
            "module": "performance",
        },
        {
            "code": "performance.create",
            "name": "Create performance records",
            "description": "Submit daily team performance records.",
            "module": "performance",
        },
        {
            "code": "performance.manage",
            "name": "Manage performance objectives",
            "description": "Manage team performance objectives and view all team performance.",
            "module": "performance",
        },
        {
            "code": "dashboard.read",
            "name": "Read dashboard",
            "description": "Access dashboard and reporting endpoints within the permitted scope.",
            "module": "dashboard",
        },
        {
            "code": "dashboard.manage",
            "name": "Manage dashboard scope",
            "description": "Access dashboard data without scope restrictions.",
            "module": "dashboard",
        },
        {
            "code": "admin_panel.access",
            "name": "Access admin panel",
            "description": "Reserved permission entry for the internal control panel catalog.",
            "module": "admin_panel",
        },
    )

    DEFAULT_JOB_TITLE_PERMISSION_CODES: dict[str, list[str]] = {
        "RH_MANAGER": [
            "organization.read",
            "organization.read_hierarchy",
            "organization.create",
            "organization.update",
            "employees.read",
            "employees.create",
            "employees.update",
            "permissions.read",
            "permissions.assign",
            "announcements.read",
            "announcements.create",
            "announcements.update",
            "announcements.delete",
            "requests.read",
            "requests.create",
            "requests.approve",
            "requests.read_my_approvals",
            "requests.manage",
            "requests.read_all",
            "attendance.read",
            "attendance.ingest",
            "attendance.nfc.assign_card",
            "attendance.reports.generate",
            "performance.read",
            "performance.manage",
            "dashboard.read",
        ],
        "DEPARTMENT_MANAGER": [
            "organization.read",
            "organization.read_hierarchy",
            "employees.read",
            "announcements.read",
            "announcements.create",
            "announcements.update",
            "announcements.delete",
            "requests.read",
            "requests.approve",
            "requests.read_my_approvals",
            "attendance.read",
            "performance.read",
            "dashboard.read",
        ],
        "TEAM_LEADER": [
            "organization.read_hierarchy",
            "announcements.read",
            "requests.read",
            "requests.create",
            "requests.approve",
            "requests.read_my_approvals",
            "attendance.read",
            "performance.create",
            "performance.read",
            "dashboard.read",
        ],
        "EMPLOYEE": [
            "announcements.read",
            "requests.create",
            "requests.read",
        ],
    }

    OPERATIONAL_ROLE_CONFIGS = (
        {
            "key": "rh_manager",
            "label": "RH Manager",
            "job_title_code": "RH_MANAGER",
            "team_index": None,
            "sets_department_manager": False,
        },
        {
            "key": "department_manager",
            "label": "Department Manager",
            "job_title_code": "DEPARTMENT_MANAGER",
            "team_index": None,
            "sets_department_manager": True,
        },
        {
            "key": "team_leader_one",
            "label": "Team Leader 1",
            "job_title_code": "TEAM_LEADER",
            "team_index": 0,
            "sets_department_manager": False,
        },
        {
            "key": "team_leader_two",
            "label": "Team Leader 2",
            "job_title_code": "TEAM_LEADER",
            "team_index": 1,
            "sets_department_manager": False,
        },
    )

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.employees_service = EmployeesService(db=db)
        self.organization_service = OrganizationService(db=db)
        self.permissions_service = PermissionsService(db=db)

    def get_status(self) -> dict[str, Any]:
        """Return the persistent installation state summary."""

        initialized = self.is_initialized()
        bootstrap_super_admin_exists = self.get_super_admin() is not None
        installation_state = self.get_installation_state()

        if initialized:
            detail = "System installation is complete and locked."
        elif bootstrap_super_admin_exists:
            detail = (
                "Bootstrap super admin is ready. Finish the admin setup wizard to make the system operational."
            )
        else:
            detail = (
                "System is not initialized. Create the bootstrap super admin, then finish the admin setup wizard."
            )

        return {
            "initialized": initialized,
            "bootstrap_super_admin_exists": bootstrap_super_admin_exists,
            "setup_wizard_required": not initialized,
            "initialized_at": (
                installation_state.initialized_at if installation_state is not None else None
            ),
            "detail": detail,
        }

    def is_initialized(self) -> bool:
        """Return whether the installation has been completed successfully."""

        installation_state = self.get_installation_state()
        return bool(installation_state is not None and installation_state.is_initialized)

    def get_installation_state(self) -> InstallationState | None:
        """Return the persistent installation state row if it exists."""

        statement = (
            select(InstallationState)
            .order_by(InstallationState.id.asc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def ensure_installation_state(self) -> InstallationState:
        """Return the installation state row, creating the default draft row if needed."""

        installation_state = self.get_installation_state()
        if installation_state is not None:
            if installation_state.wizard_state is None:
                installation_state.wizard_state = {}
                self.db.add(installation_state)
                self.db.commit()
                self.db.refresh(installation_state)
            return installation_state

        installation_state = InstallationState(
            id=self.INSTALLATION_STATE_ID,
            is_initialized=False,
            wizard_state={},
        )
        self.db.add(installation_state)
        self.db.commit()
        self.db.refresh(installation_state)
        return installation_state

    def get_super_admin(self) -> User | None:
        """Return the first super admin account if it exists."""

        statement = (
            select(User)
            .where(User.is_super_admin.is_(True))
            .order_by(User.id.asc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def initialize_system(self) -> User:
        """Create the bootstrap super admin account exactly once."""

        existing_super_admin = self.get_super_admin()
        if existing_super_admin is not None:
            raise SetupAlreadyInitializedError(
                "Bootstrap super admin already exists. Continue with the admin setup wizard."
            )

        try:
            bootstrap_values = self.settings.get_super_admin_bootstrap()
        except ValueError as exc:
            raise SetupConfigurationError(str(exc)) from exc

        super_admin = User(
            matricule=bootstrap_values["matricule"],
            password_hash=PasswordManager.hash_password(bootstrap_values["password"]),
            first_name=bootstrap_values["first_name"],
            last_name=bootstrap_values["last_name"],
            email=bootstrap_values["email"],
            is_super_admin=True,
            is_active=True,
            must_change_password=True,
        )
        self.db.add(super_admin)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if self.get_super_admin() is not None:
                raise SetupAlreadyInitializedError(
                    "Bootstrap super admin already exists. Continue with the admin setup wizard."
                ) from exc
            raise SetupInitializationError(
                "Failed to create the bootstrap super admin account."
            ) from exc

        self.db.refresh(super_admin)
        self.ensure_installation_state()
        return super_admin

    def get_installation_snapshot(self) -> dict[str, Any]:
        """Return a frontend-friendly snapshot used by the admin panel."""

        status = self.get_status()
        wizard_state = self.get_wizard_state()
        return {
            **status,
            "last_completed_step": int(wizard_state.get("last_completed_step", 0) or 0),
            "next_step": self.get_next_wizard_step_number(),
            "review_summary": self.get_review_summary(),
        }

    def get_next_wizard_step_number(self) -> int:
        """Return the next setup-wizard step to continue with."""

        if self.is_initialized():
            return 7

        wizard_state = self.get_wizard_state()
        last_completed_step = int(wizard_state.get("last_completed_step", 0) or 0)
        return max(1, min(last_completed_step + 1, 7))

    def get_wizard_state(self) -> dict[str, Any]:
        """Return a detached copy of the persisted wizard draft state."""

        installation_state = self.ensure_installation_state()
        return deepcopy(installation_state.wizard_state or {})

    def save_readiness_step(self) -> None:
        """Mark the readiness step as acknowledged."""

        self._ensure_wizard_writable()
        wizard_state = self.get_wizard_state()
        wizard_state["last_completed_step"] = max(
            int(wizard_state.get("last_completed_step", 0) or 0),
            1,
        )
        self._persist_wizard_state(wizard_state)

    def save_organization_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create or update the initial department and two teams."""

        self._ensure_wizard_writable()

        if payload["team_one_code"] == payload["team_two_code"]:
            raise SetupValidationError("Team codes must be unique.")

        if payload["team_one_name"].casefold() == payload["team_two_name"].casefold():
            raise SetupValidationError("Team names must be unique.")

        wizard_state = self.get_wizard_state()
        organization_state = wizard_state.get("organization", {})

        department = self._upsert_department(
            existing_department_id=organization_state.get("department_id"),
            payload=DepartmentCreateRequest(
                name=payload["department_name"],
                code=payload["department_code"],
                description=payload.get("department_description"),
                manager_user_id=None,
            ),
        )
        team_one = self._upsert_team(
            existing_team_id=self._get_team_id_at_index(organization_state, 0),
            payload=TeamCreateRequest(
                name=payload["team_one_name"],
                code=payload["team_one_code"],
                description=payload.get("team_one_description"),
                department_id=department.id,
                leader_user_id=None,
            ),
        )
        team_two = self._upsert_team(
            existing_team_id=self._get_team_id_at_index(organization_state, 1),
            payload=TeamCreateRequest(
                name=payload["team_two_name"],
                code=payload["team_two_code"],
                description=payload.get("team_two_description"),
                department_id=department.id,
                leader_user_id=None,
            ),
        )

        wizard_state["organization"] = {
            "department_id": department.id,
            "team_ids": [team_one.id, team_two.id],
        }
        wizard_state["last_completed_step"] = max(
            int(wizard_state.get("last_completed_step", 0) or 0),
            2,
        )
        self._persist_wizard_state(wizard_state)
        return self.get_organization_summary()

    def save_job_titles_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create or update the initial job-title catalog."""

        self._ensure_wizard_writable()

        wizard_state = self.get_wizard_state()
        job_title_state = wizard_state.get("job_titles", {})
        job_title_ids_by_code: dict[str, int] = {}

        for definition in self.DEFAULT_JOB_TITLES:
            code = definition["code"]
            title_key = definition["key"]
            request_payload = JobTitleCreateRequest(
                name=payload.get(f"{title_key}_name", definition["name"]),
                code=code,
                description=payload.get(
                    f"{title_key}_description",
                    definition["description"],
                ),
                hierarchical_level=payload.get(
                    f"{title_key}_hierarchical_level",
                    definition["hierarchical_level"],
                ),
            )
            job_title = self._upsert_job_title(
                existing_job_title_id=job_title_state.get("codes", {}).get(code),
                payload=request_payload,
            )
            job_title_ids_by_code[code] = job_title.id

        wizard_state["job_titles"] = {"codes": job_title_ids_by_code}
        wizard_state["last_completed_step"] = max(
            int(wizard_state.get("last_completed_step", 0) or 0),
            3,
        )
        self._persist_wizard_state(wizard_state)
        return self.get_job_titles_summary()

    def ensure_permission_catalog(self) -> dict[str, Any]:
        """Create or refresh the initial permission catalog."""

        self._ensure_wizard_writable()

        wizard_state = self.get_wizard_state()
        permission_ids_by_code: dict[str, int] = {}
        stored_permission_ids = wizard_state.get("permissions", {}).get("codes", {})

        for definition in self.DEFAULT_PERMISSIONS:
            permission = self._upsert_permission(
                existing_permission_id=stored_permission_ids.get(definition["code"]),
                payload=PermissionCreateRequest(**definition),
            )
            permission_ids_by_code[permission.code] = permission.id

        wizard_state["permissions"] = {"codes": permission_ids_by_code}
        wizard_state["last_completed_step"] = max(
            int(wizard_state.get("last_completed_step", 0) or 0),
            4,
        )
        self._persist_wizard_state(wizard_state)
        return self.get_permissions_summary()

    def ensure_job_title_permission_assignments(self) -> dict[str, Any]:
        """Replace the initial permission mappings for the seeded job titles."""

        self._ensure_wizard_writable()

        permissions_by_code = self._get_required_permissions_by_code()
        job_titles_by_code = self._get_required_job_titles_by_code()
        assignment_snapshot: dict[str, list[str]] = {}

        for job_title_code, permission_codes in self.DEFAULT_JOB_TITLE_PERMISSION_CODES.items():
            permission_ids = [permissions_by_code[item].id for item in permission_codes]
            self.permissions_service.assign_permissions_to_job_title(
                job_titles_by_code[job_title_code].id,
                JobTitlePermissionAssignmentRequest(permission_ids=permission_ids),
            )
            assignment_snapshot[job_title_code] = list(permission_codes)

        wizard_state = self.get_wizard_state()
        wizard_state["job_title_permissions"] = assignment_snapshot
        wizard_state["last_completed_step"] = max(
            int(wizard_state.get("last_completed_step", 0) or 0),
            5,
        )
        self._persist_wizard_state(wizard_state)
        return self.get_job_title_permission_summary()

    def save_operational_users_step(
        self,
        payload: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Create or update the initial operational employees and linked users."""

        self._ensure_wizard_writable()

        department = self._get_required_department()
        teams = self._get_required_teams()
        job_titles_by_code = self._get_required_job_titles_by_code()
        self._validate_operational_user_payload(payload)

        wizard_state = self.get_wizard_state()
        operational_state = wizard_state.get("operational_users", {})
        role_entries: dict[str, dict[str, int]] = {}

        for role_config in self.OPERATIONAL_ROLE_CONFIGS:
            role_key = role_config["key"]
            role_payload = payload[role_key]
            existing_employee_id = operational_state.get(role_key, {}).get("employee_id")
            team = (
                teams[role_config["team_index"]]
                if role_config["team_index"] is not None
                else None
            )
            employee = self._upsert_operational_employee(
                existing_employee_id=existing_employee_id,
                role_payload=role_payload,
                department=department,
                team=team,
                job_title_id=job_titles_by_code[role_config["job_title_code"]].id,
            )
            role_entries[role_key] = {
                "employee_id": employee.id,
                "user_id": employee.user_id,
            }

        self._sync_operational_leadership(
            department=department,
            teams=teams,
            role_entries=role_entries,
        )

        wizard_state["operational_users"] = role_entries
        wizard_state["last_completed_step"] = max(
            int(wizard_state.get("last_completed_step", 0) or 0),
            6,
        )
        self._persist_wizard_state(wizard_state)
        return self.get_operational_users_summary()

    def complete_installation(self, initialized_by_user: User) -> InstallationState:
        """Validate the minimum setup data and lock the installation state."""

        self._ensure_wizard_writable()
        review_summary = self.get_review_summary()
        missing_items = review_summary["missing_items"]
        if missing_items:
            raise SetupValidationError(
                "Installation cannot be completed yet. Missing requirements: "
                + ", ".join(missing_items)
                + "."
            )

        installation_state = self.ensure_installation_state()
        if installation_state.is_initialized:
            raise SetupAlreadyInitializedError(
                "Installation has already been completed and locked."
            )

        wizard_state = self.get_wizard_state()
        wizard_state["last_completed_step"] = 7
        installation_state.is_initialized = True
        installation_state.initialized_at = utcnow()
        installation_state.initialized_by_user_id = initialized_by_user.id
        installation_state.wizard_state = wizard_state
        self.db.add(installation_state)
        self.db.commit()
        self.db.refresh(installation_state)
        return installation_state

    def get_readiness_summary(self) -> dict[str, Any]:
        """Return the readiness data displayed on the first wizard step."""

        status = self.get_status()
        return {
            **status,
            "database_ready": True,
            "migrations_ready": True,
            "super_admin": self.get_super_admin(),
        }

    def get_organization_summary(self) -> dict[str, Any]:
        """Return the current organization draft summary."""

        wizard_state = self.get_wizard_state()
        organization_state = wizard_state.get("organization", {})
        department = self._get_department_from_state(organization_state.get("department_id"))
        teams = self._get_teams_from_state(organization_state.get("team_ids", []))
        return {"department": department, "teams": teams}

    def get_job_titles_summary(self) -> dict[str, Any]:
        """Return the current job-title setup summary."""

        job_titles = []
        for definition in self.DEFAULT_JOB_TITLES:
            job_title = self._get_job_title_by_code(definition["code"])
            if job_title is not None:
                job_titles.append(job_title)
        return {"job_titles": job_titles}

    def get_permissions_summary(self) -> dict[str, Any]:
        """Return the current permission-catalog summary."""

        permissions: list[Permission] = []
        for definition in self.DEFAULT_PERMISSIONS:
            permission = self._get_permission_by_code(definition["code"])
            if permission is not None:
                permissions.append(permission)
        return {
            "permissions": permissions,
            "expected_count": len(self.DEFAULT_PERMISSIONS),
        }

    def get_job_title_permission_summary(self) -> dict[str, Any]:
        """Return the current job-title permission-assignment summary."""

        assignments: dict[str, list[Permission]] = {}
        for definition in self.DEFAULT_JOB_TITLES:
            job_title = self._get_job_title_by_code(definition["code"])
            if job_title is None:
                assignments[definition["code"]] = []
                continue
            assignments[definition["code"]] = self.permissions_service.get_permissions_for_job_title(
                job_title.id
            )
        return {"assignments": assignments}

    def get_operational_users_summary(self) -> dict[str, Any]:
        """Return the current operational-user draft summary."""

        wizard_state = self.get_wizard_state()
        operational_state = wizard_state.get("operational_users", {})
        employees: list[dict[str, Any]] = []
        for role_config in self.OPERATIONAL_ROLE_CONFIGS:
            entry = operational_state.get(role_config["key"], {})
            employee = self._get_employee_from_state(entry.get("employee_id"))
            if employee is None:
                continue
            employees.append(self._build_operational_employee_summary(role_config, employee))
        return {"employees": employees}

    def get_review_summary(self) -> dict[str, Any]:
        """Return the final wizard review summary and completion readiness."""

        organization_summary = self.get_organization_summary()
        job_titles_summary = self.get_job_titles_summary()
        permissions_summary = self.get_permissions_summary()
        assignment_summary = self.get_job_title_permission_summary()
        operational_users_summary = self.get_operational_users_summary()

        missing_items: list[str] = []
        if organization_summary["department"] is None:
            missing_items.append("one department")
        if len(organization_summary["teams"]) < 2:
            missing_items.append("two teams linked to the department")
        if len(job_titles_summary["job_titles"]) < len(self.DEFAULT_JOB_TITLES):
            missing_items.append("required job titles")
        if len(permissions_summary["permissions"]) < len(self.DEFAULT_PERMISSIONS):
            missing_items.append("required permissions")
        for job_title_code, expected_permission_codes in self.DEFAULT_JOB_TITLE_PERMISSION_CODES.items():
            assigned_codes = {item.code for item in assignment_summary["assignments"].get(job_title_code, [])}
            if set(expected_permission_codes) - assigned_codes:
                missing_items.append(f"permission assignment for {job_title_code}")
        if len(operational_users_summary["employees"]) < len(self.OPERATIONAL_ROLE_CONFIGS):
            missing_items.append("four operational users")

        return {
            "organization": organization_summary,
            "job_titles": job_titles_summary,
            "permissions": permissions_summary,
            "job_title_permissions": assignment_summary,
            "operational_users": operational_users_summary,
            "missing_items": missing_items,
            "is_ready": not missing_items,
        }

    def _persist_wizard_state(self, wizard_state: dict[str, Any]) -> None:
        """Persist the setup wizard draft state."""

        installation_state = self.ensure_installation_state()
        installation_state.wizard_state = wizard_state
        self.db.add(installation_state)
        self.db.commit()
        self.db.refresh(installation_state)

    def _ensure_wizard_writable(self) -> None:
        """Reject wizard writes after installation completion."""

        if self.is_initialized():
            raise SetupAlreadyInitializedError(
                "Installation has already been completed and locked."
            )

    def _upsert_department(
        self,
        *,
        existing_department_id: int | None,
        payload: DepartmentCreateRequest,
    ) -> Department:
        """Create or update the wizard-managed department."""

        try:
            if existing_department_id is not None:
                return self.organization_service.update_department(
                    existing_department_id,
                    DepartmentUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        description=payload.description,
                    ),
                )

            existing_department = self.db.execute(
                select(Department).where(Department.code == payload.code).limit(1)
            ).scalar_one_or_none()
            if existing_department is not None:
                return self.organization_service.update_department(
                    existing_department.id,
                    DepartmentUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        description=payload.description,
                    ),
                )

            return self.organization_service.create_department(payload)
        except (
            OrganizationConflictError,
            OrganizationNotFoundError,
            OrganizationValidationError,
        ) as exc:
            raise SetupValidationError(str(exc)) from exc

    def _upsert_team(
        self,
        *,
        existing_team_id: int | None,
        payload: TeamCreateRequest,
    ) -> Team:
        """Create or update one wizard-managed team."""

        try:
            if existing_team_id is not None:
                return self.organization_service.update_team(
                    existing_team_id,
                    TeamUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        description=payload.description,
                        department_id=payload.department_id,
                    ),
                )

            existing_team = self.db.execute(
                select(Team).where(Team.code == payload.code).limit(1)
            ).scalar_one_or_none()
            if existing_team is not None:
                return self.organization_service.update_team(
                    existing_team.id,
                    TeamUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        description=payload.description,
                        department_id=payload.department_id,
                    ),
                )

            return self.organization_service.create_team(payload)
        except (
            OrganizationConflictError,
            OrganizationNotFoundError,
            OrganizationValidationError,
        ) as exc:
            raise SetupValidationError(str(exc)) from exc

    def _upsert_job_title(
        self,
        *,
        existing_job_title_id: int | None,
        payload: JobTitleCreateRequest,
    ) -> JobTitle:
        """Create or update one wizard-managed job title."""

        try:
            if existing_job_title_id is not None:
                return self.organization_service.update_job_title(
                    existing_job_title_id,
                    JobTitleUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        description=payload.description,
                        hierarchical_level=payload.hierarchical_level,
                    ),
                )

            existing_job_title = self.db.execute(
                select(JobTitle).where(JobTitle.code == payload.code).limit(1)
            ).scalar_one_or_none()
            if existing_job_title is not None:
                return self.organization_service.update_job_title(
                    existing_job_title.id,
                    JobTitleUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        description=payload.description,
                        hierarchical_level=payload.hierarchical_level,
                    ),
                )

            return self.organization_service.create_job_title(payload)
        except (
            OrganizationConflictError,
            OrganizationNotFoundError,
            OrganizationValidationError,
        ) as exc:
            raise SetupValidationError(str(exc)) from exc

    def _upsert_permission(
        self,
        *,
        existing_permission_id: int | None,
        payload: PermissionCreateRequest,
    ) -> Permission:
        """Create or update one wizard-managed permission entry."""

        try:
            if existing_permission_id is not None:
                return self.permissions_service.update_permission(
                    existing_permission_id,
                    PermissionUpdateRequest(
                        code=payload.code,
                        name=payload.name,
                        description=payload.description,
                        module=payload.module,
                        is_active=True,
                    ),
                )

            existing_permission = self.db.execute(
                select(Permission).where(Permission.code == payload.code).limit(1)
            ).scalar_one_or_none()
            if existing_permission is not None:
                return self.permissions_service.update_permission(
                    existing_permission.id,
                    PermissionUpdateRequest(
                        code=payload.code,
                        name=payload.name,
                        description=payload.description,
                        module=payload.module,
                        is_active=True,
                    ),
                )

            return self.permissions_service.create_permission(payload)
        except (
            PermissionsConflictError,
            PermissionsNotFoundError,
            PermissionsValidationError,
        ) as exc:
            raise SetupValidationError(str(exc)) from exc

    def _validate_operational_user_payload(
        self,
        payload: dict[str, dict[str, Any]],
    ) -> None:
        """Validate uniqueness and presence for operational user input."""

        seen_matricules: set[str] = set()
        seen_emails: set[str] = set()

        for role_config in self.OPERATIONAL_ROLE_CONFIGS:
            role_key = role_config["key"]
            role_payload = payload.get(role_key)
            if role_payload is None:
                raise SetupValidationError(f"Missing payload for {role_config['label']}.")

            matricule = str(role_payload["matricule"]).strip().upper()
            email = str(role_payload["email"]).strip().lower()
            if matricule in seen_matricules:
                raise SetupValidationError("Operational user matricules must be unique.")
            if email in seen_emails:
                raise SetupValidationError("Operational user emails must be unique.")

            seen_matricules.add(matricule)
            seen_emails.add(email)

    def _upsert_operational_employee(
        self,
        *,
        existing_employee_id: int | None,
        role_payload: dict[str, Any],
        department: Department,
        team: Team | None,
        job_title_id: int,
    ) -> Employee:
        """Create or update one operational employee and normalize the linked user account."""

        try:
            if existing_employee_id is not None:
                employee = self.employees_service.update_employee(
                    existing_employee_id,
                    EmployeeUpdateRequest(
                        matricule=role_payload["matricule"],
                        first_name=role_payload["first_name"],
                        last_name=role_payload["last_name"],
                        email=role_payload["email"],
                        phone=None,
                        hire_date=role_payload["hire_date"],
                        available_leave_balance_days=self.DEFAULT_INITIAL_LEAVE_BALANCE_DAYS,
                        department_id=department.id,
                        team_id=team.id if team is not None else None,
                        job_title_id=job_title_id,
                        is_active=True,
                    ),
                )
            else:
                employee, _ = self.employees_service.create_employee(
                    EmployeeCreateRequest(
                        matricule=role_payload["matricule"],
                        first_name=role_payload["first_name"],
                        last_name=role_payload["last_name"],
                        email=role_payload["email"],
                        phone=None,
                        hire_date=role_payload["hire_date"],
                        available_leave_balance_days=self.DEFAULT_INITIAL_LEAVE_BALANCE_DAYS,
                        department_id=department.id,
                        team_id=team.id if team is not None else None,
                        job_title_id=job_title_id,
                    )
                )
        except (
            EmployeesConflictError,
            EmployeesNotFoundError,
            EmployeesValidationError,
        ) as exc:
            raise SetupValidationError(str(exc)) from exc

        user = self.db.get(User, employee.user_id)
        if user is None:
            raise SetupInitializationError("Linked user account not found during setup.")

        password = role_payload.get("password")
        if password:
            user.password_hash = PasswordManager.hash_password(password)

        user.is_active = True
        user.is_super_admin = False
        user.must_change_password = True
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        self.db.refresh(employee)
        return employee

    def _sync_operational_leadership(
        self,
        *,
        department: Department,
        teams: list[Team],
        role_entries: dict[str, dict[str, int]],
    ) -> None:
        """Assign the created users as department manager and team leaders."""

        department.manager_user_id = role_entries["department_manager"]["user_id"]
        teams[0].leader_user_id = role_entries["team_leader_one"]["user_id"]
        teams[1].leader_user_id = role_entries["team_leader_two"]["user_id"]

        self.db.add(department)
        self.db.add(teams[0])
        self.db.add(teams[1])
        self.db.commit()
        self.db.refresh(department)
        self.db.refresh(teams[0])
        self.db.refresh(teams[1])

    def _get_required_department(self) -> Department:
        """Return the configured setup department or fail with a wizard-specific error."""

        department = self.get_organization_summary()["department"]
        if department is None:
            raise SetupValidationError(
                "Complete the organization step before creating operational users."
            )
        return department

    def _get_required_teams(self) -> list[Team]:
        """Return the configured setup teams or fail if the organization step is incomplete."""

        teams = self.get_organization_summary()["teams"]
        if len(teams) < 2:
            raise SetupValidationError(
                "Complete the organization step before creating operational users."
            )
        return teams[:2]

    def _get_required_job_titles_by_code(self) -> dict[str, JobTitle]:
        """Return the seeded job titles keyed by code or fail if the catalog is incomplete."""

        job_titles: dict[str, JobTitle] = {}
        for definition in self.DEFAULT_JOB_TITLES:
            job_title = self._get_job_title_by_code(definition["code"])
            if job_title is None:
                raise SetupValidationError("Complete the job titles step before continuing.")
            job_titles[job_title.code] = job_title
        return job_titles

    def _get_required_permissions_by_code(self) -> dict[str, Permission]:
        """Return the seeded permissions keyed by code or fail if the catalog is incomplete."""

        permissions: dict[str, Permission] = {}
        for definition in self.DEFAULT_PERMISSIONS:
            permission = self._get_permission_by_code(definition["code"])
            if permission is None:
                raise SetupValidationError(
                    "Complete the permission catalog step before continuing."
                )
            permissions[permission.code] = permission
        return permissions

    def _get_department_from_state(self, department_id: int | None) -> Department | None:
        """Resolve a department from the wizard state."""

        if department_id is None:
            return None
        return self.db.get(Department, department_id)

    def _get_teams_from_state(self, team_ids: list[int]) -> list[Team]:
        """Resolve wizard-managed teams while preserving the stored order."""

        teams: list[Team] = []
        for team_id in team_ids:
            team = self.db.get(Team, team_id)
            if team is not None:
                teams.append(team)
        return teams

    def _get_team_id_at_index(
        self,
        organization_state: dict[str, Any],
        index: int,
    ) -> int | None:
        """Return the stored team id at the requested index."""

        team_ids = organization_state.get("team_ids", [])
        if len(team_ids) <= index:
            return None
        return team_ids[index]

    def _get_job_title_by_code(self, code: str) -> JobTitle | None:
        """Return a job title by its unique code."""

        return self.db.execute(
            select(JobTitle).where(JobTitle.code == code).limit(1)
        ).scalar_one_or_none()

    def _get_permission_by_code(self, code: str) -> Permission | None:
        """Return a permission by its unique code."""

        return self.db.execute(
            select(Permission).where(Permission.code == code).limit(1)
        ).scalar_one_or_none()

    def _get_employee_from_state(self, employee_id: int | None) -> Employee | None:
        """Resolve an employee id stored in the wizard state."""

        if employee_id is None:
            return None
        return self.db.get(Employee, employee_id)

    def _build_operational_employee_summary(
        self,
        role_config: dict[str, Any],
        employee: Employee,
    ) -> dict[str, Any]:
        """Build the summary payload displayed on review and user steps."""

        user = self.db.get(User, employee.user_id)
        job_title = self.db.get(JobTitle, employee.job_title_id)
        department = (
            self.db.get(Department, employee.department_id)
            if employee.department_id is not None
            else None
        )
        team = self.db.get(Team, employee.team_id) if employee.team_id is not None else None
        return {
            "role_label": role_config["label"],
            "employee": employee,
            "user": user,
            "job_title": job_title,
            "department": department,
            "team": team,
        }
