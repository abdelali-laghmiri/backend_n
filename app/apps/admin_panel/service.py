from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.admin_panel.schemas import AdminUserCreateRequest, AdminUserUpdateRequest
from app.apps.attendance.models import (
    AttendanceDailySummary,
    AttendanceMonthlyReport,
    AttendanceStatusEnum,
)
from app.apps.attendance.schemas import AttendanceMonthlyReportGenerateRequest
from app.apps.attendance.service import AttendanceService
from app.apps.auth.service import AuthenticationError, AuthService, InactiveUserError
from app.apps.dashboard.service import DashboardService
from app.apps.employees.models import Employee
from app.apps.employees.schemas import EmployeeCreateRequest, EmployeeUpdateRequest
from app.apps.employees.service import EmployeesService
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.organization.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    JobTitleCreateRequest,
    JobTitleUpdateRequest,
    TeamCreateRequest,
    TeamUpdateRequest,
)
from app.apps.organization.service import OrganizationService, OrganizationValidationError
from app.apps.permissions.models import JobTitlePermissionAssignment, Permission
from app.apps.permissions.schemas import (
    JobTitlePermissionAssignmentRequest,
    PermissionCreateRequest,
    PermissionUpdateRequest,
)
from app.apps.permissions.service import PermissionsService
from app.apps.performance.models import TeamDailyPerformance, TeamObjective
from app.apps.performance.schemas import (
    TeamDailyPerformanceCreateRequest,
    TeamObjectiveCreateRequest,
    TeamObjectiveUpdateRequest,
)
from app.apps.performance.service import PerformanceService
from app.apps.requests.models import (
    RequestStatusEnum,
    RequestType,
    RequestTypeField,
    RequestWorkflowStep,
    WorkflowRequest,
)
from app.apps.requests.schemas import (
    RequestTypeCreateRequest,
    RequestTypeFieldCreateRequest,
    RequestTypeFieldUpdateRequest,
    RequestTypeUpdateRequest,
    RequestWorkflowStepCreateRequest,
    RequestWorkflowStepUpdateRequest,
)
from app.apps.requests.service import RequestsService
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.core.config import Settings
from app.core.security import JWTManager, PasswordManager, TokenValidationError


class AdminPanelError(RuntimeError):
    """Base admin panel error."""


class AdminPanelAuthenticationError(AdminPanelError):
    """Raised when the admin panel authentication state is invalid."""


class AdminPanelValidationError(AdminPanelError):
    """Raised when an admin panel form submission is invalid."""


class AdminPanelConflictError(AdminPanelError):
    """Raised when an admin panel action conflicts with current data."""


class AdminPanelNotFoundError(AdminPanelError):
    """Raised when an admin panel record cannot be found."""


class AdminPanelService:
    """Service layer backing the internal super admin dashboard."""

    ADMIN_COOKIE_NAME = "admin_panel_access_token"
    LOGIN_CSRF_SUBJECT = "admin-login"
    CSRF_KIND = "admin-csrf"
    ADMIN_PANEL_CLAIM = "admin_panel"

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.auth_service = AuthService(db=db, settings=settings)
        self.dashboard_service = DashboardService(db=db)
        self.employees_service = EmployeesService(db=db)
        self.organization_service = OrganizationService(db=db)
        self.permissions_service = PermissionsService(db=db)
        self.requests_service = RequestsService(db=db)
        self.attendance_service = AttendanceService(db=db)
        self.performance_service = PerformanceService(db=db)
        self.setup_service = SetupService(db=db, settings=settings)

    def authenticate_super_admin(self, *, matricule: str, password: str) -> User:
        """Authenticate an admin-panel user and require super admin access."""

        try:
            user = self.auth_service.authenticate_user(
                matricule=matricule,
                password=password,
            )
        except (AuthenticationError, InactiveUserError) as exc:
            raise AdminPanelAuthenticationError(str(exc)) from exc

        if not user.is_super_admin:
            raise AdminPanelAuthenticationError(
                "Only super admin accounts can access the internal dashboard."
            )

        return user

    def create_admin_access_token_for_user(self, user: User) -> tuple[str, int]:
        """Create the signed admin cookie token."""

        expires_delta = timedelta(minutes=self.settings.access_token_expire_minutes)
        expires_in = int(expires_delta.total_seconds())
        token = JWTManager.create_access_token(
            subject=str(user.id),
            secret_key=self.settings.secret_key.get_secret_value(),
            expires_delta=expires_delta,
            algorithm=self.settings.jwt_algorithm,
            extra_claims={
                "matricule": user.matricule,
                "panel": self.ADMIN_PANEL_CLAIM,
            },
        )
        return token, expires_in

    def resolve_admin_user_from_token(self, token: str | None) -> User | None:
        """Resolve the authenticated super admin from the signed cookie token."""

        if token is None:
            return None

        try:
            payload = JWTManager.decode_token(
                token=token,
                secret_key=self.settings.secret_key.get_secret_value(),
                algorithm=self.settings.jwt_algorithm,
            )
        except TokenValidationError:
            return None

        if payload.get("panel") != self.ADMIN_PANEL_CLAIM:
            return None

        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            return None

        user = self.db.get(User, user_id)
        if user is None or not user.is_active or not user.is_super_admin:
            return None

        return user

    def create_login_csrf_token(self) -> str:
        """Create the CSRF token used by the login form."""

        return self._create_csrf_token(subject=self.LOGIN_CSRF_SUBJECT)

    def create_csrf_token_for_user(self, user: User) -> str:
        """Create a CSRF token bound to the current super admin."""

        return self._create_csrf_token(subject=str(user.id))

    def validate_login_csrf_token(self, token: str | None) -> None:
        """Validate the login CSRF token."""

        self._validate_csrf_token(token=token, subject=self.LOGIN_CSRF_SUBJECT)

    def validate_csrf_token_for_user(self, token: str | None, user: User) -> None:
        """Validate a CSRF token bound to a specific super admin."""

        self._validate_csrf_token(token=token, subject=str(user.id))

    def get_overview(self, current_user: User) -> dict[str, Any]:
        """Return the data shown on the admin landing page."""

        today = date.today()
        overview = self.dashboard_service.get_overview(
            current_user,
            target_date=today,
            team_id=None,
            department_id=None,
        )
        requests_summary = self.dashboard_service.get_requests_summary(
            current_user,
            date_from=today - timedelta(days=6),
            date_to=today,
            team_id=None,
            department_id=None,
            recent_limit=6,
        )
        performance_summary = self.dashboard_service.get_performance_summary(
            current_user,
            target_date=today,
            team_id=None,
            department_id=None,
        )
        current_month_reports = self.db.execute(
            select(
                func.count(AttendanceMonthlyReport.id),
                func.coalesce(func.sum(AttendanceMonthlyReport.total_worked_minutes), 0),
            ).where(
                AttendanceMonthlyReport.report_year == today.year,
                AttendanceMonthlyReport.report_month == today.month,
            )
        ).one()

        return {
            "today": today,
            "overview": overview,
            "requests_summary": requests_summary,
            "performance_summary": performance_summary,
            "job_titles_count": int(
                self.db.execute(select(func.count(JobTitle.id))).scalar_one() or 0
            ),
            "current_month_reports_count": int(current_month_reports[0] or 0),
            "current_month_worked_minutes": int(current_month_reports[1] or 0),
        }

    def get_installation_snapshot(self) -> dict[str, Any]:
        """Return the persisted installation snapshot for layout badges and wizard routes."""

        return self.setup_service.get_installation_snapshot()

    def list_users(
        self,
        *,
        q: str | None,
        include_inactive: bool,
        limit: int,
    ) -> list[User]:
        """List internal users with simple filters."""

        statement: Select[tuple[User]] = select(User)
        if not include_inactive:
            statement = statement.where(User.is_active.is_(True))

        if q is not None and q.strip():
            search_term = f"%{q.strip()}%"
            statement = statement.where(
                or_(
                    User.matricule.ilike(search_term),
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                    User.email.ilike(search_term),
                )
            )

        statement = statement.order_by(User.created_at.desc(), User.id.desc()).limit(limit)
        return list(self.db.execute(statement).scalars().all())

    def get_user(self, user_id: int) -> User:
        """Return one user by id."""

        user = self.db.get(User, user_id)
        if user is None:
            raise AdminPanelNotFoundError("User not found.")

        return user

    def create_user(self, payload: AdminUserCreateRequest) -> User:
        """Create an internal user account."""

        self._ensure_unique_user_identity(payload.matricule, payload.email)
        user = User(
            matricule=payload.matricule,
            password_hash=PasswordManager.hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            is_super_admin=payload.is_super_admin,
            is_active=payload.is_active,
            must_change_password=payload.must_change_password,
        )
        self.db.add(user)
        return self._commit_and_refresh(
            user,
            conflict_message="Failed to create the user account.",
        )

    def update_user(
        self,
        user_id: int,
        payload: AdminUserUpdateRequest,
        *,
        current_admin: User,
    ) -> User:
        """Update an internal user account and synchronize linked employee data."""

        user = self.get_user(user_id)
        linked_employee = self.get_linked_employee_by_user_id(user.id)
        changes = payload.model_dump(exclude_unset=True)

        if user.id == current_admin.id:
            if changes.get("is_active") is False:
                raise AdminPanelValidationError(
                    "You cannot deactivate the currently authenticated super admin."
                )
            if changes.get("is_super_admin") is False:
                raise AdminPanelValidationError(
                    "You cannot remove your own super admin access."
                )

        final_matricule = changes.get("matricule", user.matricule)
        final_first_name = changes.get("first_name", user.first_name)
        final_last_name = changes.get("last_name", user.last_name)
        final_email = changes.get("email", user.email)
        final_is_active = changes.get("is_active", user.is_active)

        self._ensure_unique_user_identity(
            final_matricule,
            final_email,
            current_user_id=user.id,
            current_employee_id=linked_employee.id if linked_employee is not None else None,
        )

        user.matricule = final_matricule
        user.first_name = final_first_name
        user.last_name = final_last_name
        user.email = final_email
        user.is_super_admin = changes.get("is_super_admin", user.is_super_admin)
        user.is_active = final_is_active
        user.must_change_password = changes.get(
            "must_change_password",
            user.must_change_password,
        )
        if changes.get("password"):
            user.password_hash = PasswordManager.hash_password(changes["password"])
            user.must_change_password = changes.get("must_change_password", False)

        self.db.add(user)

        if linked_employee is not None:
            linked_employee.matricule = final_matricule
            linked_employee.first_name = final_first_name
            linked_employee.last_name = final_last_name
            linked_employee.email = final_email
            linked_employee.is_active = final_is_active
            self.db.add(linked_employee)

        return self._commit_and_refresh(
            user,
            conflict_message="Failed to update the user account.",
        )

    def get_linked_employee_by_user_id(self, user_id: int) -> Employee | None:
        """Return the employee profile linked to a user account, if one exists."""

        return self.db.execute(
            select(Employee).where(Employee.user_id == user_id).limit(1)
        ).scalar_one_or_none()

    def list_departments(self, *, include_inactive: bool) -> list[Department]:
        """List departments."""

        return self.organization_service.list_departments(include_inactive=include_inactive)

    def get_department(self, department_id: int) -> Department:
        """Return a department by id."""

        return self.organization_service.get_department(department_id)

    def create_department(self, payload: DepartmentCreateRequest) -> Department:
        """Create a department."""

        return self.organization_service.create_department(payload)

    def update_department(
        self,
        department_id: int,
        payload: DepartmentUpdateRequest,
    ) -> Department:
        """Update a department."""

        return self.organization_service.update_department(department_id, payload)

    def set_department_active(self, department_id: int, *, is_active: bool) -> Department:
        """Activate or deactivate a department safely."""

        if not is_active:
            return self.organization_service.deactivate_department(department_id)

        department = self.organization_service.get_department(department_id)
        if department.is_active:
            return department

        if department.manager_user_id is not None:
            self._require_active_user_reference(
                department.manager_user_id,
                "Department manager",
            )

        department.is_active = True
        self.db.add(department)
        return self._commit_and_refresh(
            department,
            conflict_message="Failed to reactivate the department.",
        )

    def list_teams(self, *, include_inactive: bool) -> list[Team]:
        """List teams."""

        return self.organization_service.list_teams(include_inactive=include_inactive)

    def get_team(self, team_id: int) -> Team:
        """Return a team by id."""

        return self.organization_service.get_team(team_id)

    def create_team(self, payload: TeamCreateRequest) -> Team:
        """Create a team."""

        return self.organization_service.create_team(payload)

    def update_team(self, team_id: int, payload: TeamUpdateRequest) -> Team:
        """Update a team."""

        return self.organization_service.update_team(team_id, payload)

    def set_team_active(self, team_id: int, *, is_active: bool) -> Team:
        """Activate or deactivate a team safely."""

        if not is_active:
            return self.organization_service.deactivate_team(team_id)

        team = self.organization_service.get_team(team_id)
        if team.is_active:
            return team

        department = self.organization_service.get_department(team.department_id)
        if not department.is_active:
            raise OrganizationValidationError(
                "The team cannot be reactivated while its department is inactive."
            )

        if team.leader_user_id is not None:
            self._require_active_user_reference(team.leader_user_id, "Team leader")

        team.is_active = True
        self.db.add(team)
        return self._commit_and_refresh(
            team,
            conflict_message="Failed to reactivate the team.",
        )

    def list_job_titles(self, *, include_inactive: bool) -> list[JobTitle]:
        """List job titles."""

        return self.organization_service.list_job_titles(include_inactive=include_inactive)

    def get_job_title(self, job_title_id: int) -> JobTitle:
        """Return one job title by id."""

        return self.organization_service.get_job_title(job_title_id)

    def create_job_title(self, payload: JobTitleCreateRequest) -> JobTitle:
        """Create a job title."""

        return self.organization_service.create_job_title(payload)

    def update_job_title(
        self,
        job_title_id: int,
        payload: JobTitleUpdateRequest,
    ) -> JobTitle:
        """Update a job title."""

        return self.organization_service.update_job_title(job_title_id, payload)

    def set_job_title_active(self, job_title_id: int, *, is_active: bool) -> JobTitle:
        """Activate or deactivate a job title safely."""

        if not is_active:
            return self.organization_service.deactivate_job_title(job_title_id)

        job_title = self.organization_service.get_job_title(job_title_id)
        if job_title.is_active:
            return job_title

        job_title.is_active = True
        self.db.add(job_title)
        return self._commit_and_refresh(
            job_title,
            conflict_message="Failed to reactivate the job title.",
        )

    def list_employees(
        self,
        *,
        include_inactive: bool,
        q: str | None,
        department_id: int | None,
        team_id: int | None,
        job_title_id: int | None,
    ) -> list[Employee]:
        """List employees."""

        return self.employees_service.list_employees(
            include_inactive=include_inactive,
            q=q,
            department_id=department_id,
            team_id=team_id,
            job_title_id=job_title_id,
        )

    def get_employee(self, employee_id: int) -> Employee:
        """Return an employee by id."""

        return self.employees_service.get_employee(employee_id)

    def create_employee(
        self,
        payload: EmployeeCreateRequest,
    ) -> tuple[Employee, str]:
        """Create an employee and linked account."""

        return self.employees_service.create_employee(payload)

    def update_employee(
        self,
        employee_id: int,
        payload: EmployeeUpdateRequest,
    ) -> Employee:
        """Update an employee and linked account."""

        return self.employees_service.update_employee(employee_id, payload)

    def list_permissions(
        self,
        *,
        include_inactive: bool,
        module: str | None,
    ) -> list[Permission]:
        """List permissions."""

        return self.permissions_service.list_permissions(
            include_inactive=include_inactive,
            module=module,
        )

    def get_permission(self, permission_id: int) -> Permission:
        """Return one permission by id."""

        return self.permissions_service.get_permission(permission_id)

    def create_permission(self, payload: PermissionCreateRequest) -> Permission:
        """Create a permission."""

        return self.permissions_service.create_permission(payload)

    def update_permission(
        self,
        permission_id: int,
        payload: PermissionUpdateRequest,
    ) -> Permission:
        """Update a permission."""

        return self.permissions_service.update_permission(permission_id, payload)

    def replace_job_title_permissions(
        self,
        job_title_id: int,
        permission_ids: list[int],
    ):
        """Replace a job title permission assignment set."""

        payload = JobTitlePermissionAssignmentRequest(permission_ids=permission_ids)
        return self.permissions_service.assign_permissions_to_job_title(job_title_id, payload)

    def list_request_types(self, *, include_inactive: bool) -> list[RequestType]:
        """List request types."""

        return self.requests_service.list_request_types(include_inactive=include_inactive)

    def get_request_type(self, request_type_id: int) -> RequestType:
        """Return one request type by id."""

        return self.requests_service.get_request_type(request_type_id)

    def create_request_type(self, payload: RequestTypeCreateRequest) -> RequestType:
        """Create a request type."""

        return self.requests_service.create_request_type(payload)

    def update_request_type(
        self,
        request_type_id: int,
        payload: RequestTypeUpdateRequest,
    ) -> RequestType:
        """Update a request type."""

        return self.requests_service.update_request_type(request_type_id, payload)

    def list_request_fields(
        self,
        *,
        request_type_id: int | None,
        include_inactive: bool,
    ) -> list[RequestTypeField]:
        """List request fields, optionally filtered by request type."""

        if request_type_id is not None:
            return self.requests_service.list_request_fields(
                request_type_id,
                include_inactive=include_inactive,
            )

        statement: Select[tuple[RequestTypeField]] = select(RequestTypeField)
        if not include_inactive:
            statement = statement.where(RequestTypeField.is_active.is_(True))

        statement = statement.order_by(
            RequestTypeField.request_type_id.asc(),
            RequestTypeField.sort_order.asc(),
            RequestTypeField.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_request_field(self, request_field_id: int) -> RequestTypeField:
        """Return one request field by id."""

        return self.requests_service.get_request_field(request_field_id)

    def create_request_field(
        self,
        request_type_id: int,
        payload: RequestTypeFieldCreateRequest,
    ) -> RequestTypeField:
        """Create a request field."""

        return self.requests_service.create_request_field(request_type_id, payload)

    def update_request_field(
        self,
        request_field_id: int,
        payload: RequestTypeFieldUpdateRequest,
    ) -> RequestTypeField:
        """Update a request field."""

        return self.requests_service.update_request_field(request_field_id, payload)

    def list_workflow_steps(
        self,
        *,
        request_type_id: int | None,
        include_inactive: bool,
    ) -> list[RequestWorkflowStep]:
        """List workflow steps, optionally filtered by request type."""

        if request_type_id is not None:
            return self.requests_service.list_workflow_steps(
                request_type_id,
                include_inactive=include_inactive,
            )

        statement: Select[tuple[RequestWorkflowStep]] = select(RequestWorkflowStep)
        if not include_inactive:
            statement = statement.where(RequestWorkflowStep.is_active.is_(True))

        statement = statement.order_by(
            RequestWorkflowStep.request_type_id.asc(),
            RequestWorkflowStep.step_order.asc(),
            RequestWorkflowStep.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_workflow_step(self, step_id: int) -> RequestWorkflowStep:
        """Return one workflow step by id."""

        return self.requests_service.get_workflow_step(step_id)

    def create_workflow_step(
        self,
        request_type_id: int,
        payload: RequestWorkflowStepCreateRequest,
    ) -> RequestWorkflowStep:
        """Create a workflow step."""

        return self.requests_service.create_workflow_step(request_type_id, payload)

    def update_workflow_step(
        self,
        step_id: int,
        payload: RequestWorkflowStepUpdateRequest,
    ) -> RequestWorkflowStep:
        """Update a workflow step."""

        return self.requests_service.update_workflow_step(step_id, payload)

    def list_requests(
        self,
        *,
        status: RequestStatusEnum | None,
        request_type_id: int | None,
        employee_id: int | None,
        q: str | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> list[WorkflowRequest]:
        """List submitted requests for administrative inspection."""

        statement: Select[tuple[WorkflowRequest]] = (
            select(WorkflowRequest)
            .join(Employee, Employee.id == WorkflowRequest.requester_employee_id)
            .join(RequestType, RequestType.id == WorkflowRequest.request_type_id)
        )

        if status is not None:
            statement = statement.where(WorkflowRequest.status == status.value)

        if request_type_id is not None:
            statement = statement.where(WorkflowRequest.request_type_id == request_type_id)

        if employee_id is not None:
            statement = statement.where(WorkflowRequest.requester_employee_id == employee_id)

        if q is not None and q.strip():
            search_term = f"%{q.strip()}%"
            statement = statement.where(
                or_(
                    Employee.matricule.ilike(search_term),
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term),
                    RequestType.name.ilike(search_term),
                    RequestType.code.ilike(search_term),
                )
            )

        statement = statement.where(*self._build_datetime_range_filters(date_from, date_to))
        statement = statement.order_by(
            WorkflowRequest.submitted_at.desc(),
            WorkflowRequest.id.desc(),
        ).limit(limit)
        return list(self.db.execute(statement).scalars().all())

    def get_request_detail(self, request_id: int, current_user: User):
        """Return the detailed request payload for administrative inspection."""

        workflow_request = self.requests_service.get_request_for_user(request_id, current_user)
        return self.requests_service.build_request_detail(workflow_request)

    def list_daily_summaries(
        self,
        *,
        employee_id: int | None,
        matricule: str | None,
        team_id: int | None,
        department_id: int | None,
        status: AttendanceStatusEnum | None,
        date_from: date | None,
        date_to: date | None,
        include_inactive: bool,
        limit: int,
    ) -> list[AttendanceDailySummary]:
        """List attendance daily summaries with admin filters."""

        self._validate_date_range(date_from=date_from, date_to=date_to)
        statement: Select[tuple[AttendanceDailySummary]] = (
            select(AttendanceDailySummary)
            .join(Employee, Employee.id == AttendanceDailySummary.employee_id)
        )
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))

        if employee_id is not None:
            statement = statement.where(AttendanceDailySummary.employee_id == employee_id)

        if matricule is not None and matricule.strip():
            statement = statement.where(Employee.matricule == matricule.strip().upper())

        if team_id is not None:
            statement = statement.where(Employee.team_id == team_id)

        if department_id is not None:
            statement = statement.where(Employee.department_id == department_id)

        if status is not None:
            statement = statement.where(AttendanceDailySummary.status == status.value)

        if date_from is not None:
            statement = statement.where(AttendanceDailySummary.attendance_date >= date_from)

        if date_to is not None:
            statement = statement.where(AttendanceDailySummary.attendance_date <= date_to)

        statement = statement.order_by(
            AttendanceDailySummary.attendance_date.desc(),
            Employee.last_name.asc(),
            Employee.first_name.asc(),
            AttendanceDailySummary.id.desc(),
        ).limit(limit)
        return list(self.db.execute(statement).scalars().all())

    def get_daily_summary(self, summary_id: int) -> AttendanceDailySummary:
        """Return one daily summary by id."""

        summary = self.db.get(AttendanceDailySummary, summary_id)
        if summary is None:
            raise AdminPanelNotFoundError("Attendance daily summary not found.")

        return summary

    def list_monthly_reports(
        self,
        *,
        employee_id: int | None,
        team_id: int | None,
        department_id: int | None,
        year: int | None,
        month: int | None,
        include_inactive: bool,
        limit: int,
    ) -> list[AttendanceMonthlyReport]:
        """List attendance monthly reports with admin filters."""

        statement: Select[tuple[AttendanceMonthlyReport]] = (
            select(AttendanceMonthlyReport)
            .join(Employee, Employee.id == AttendanceMonthlyReport.employee_id)
        )
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))

        if employee_id is not None:
            statement = statement.where(AttendanceMonthlyReport.employee_id == employee_id)

        if team_id is not None:
            statement = statement.where(Employee.team_id == team_id)

        if department_id is not None:
            statement = statement.where(Employee.department_id == department_id)

        if year is not None:
            statement = statement.where(AttendanceMonthlyReport.report_year == year)

        if month is not None:
            statement = statement.where(AttendanceMonthlyReport.report_month == month)

        statement = statement.order_by(
            AttendanceMonthlyReport.report_year.desc(),
            AttendanceMonthlyReport.report_month.desc(),
            Employee.last_name.asc(),
            Employee.first_name.asc(),
            AttendanceMonthlyReport.id.desc(),
        ).limit(limit)
        return list(self.db.execute(statement).scalars().all())

    def get_monthly_report(self, report_id: int) -> AttendanceMonthlyReport:
        """Return one attendance monthly report by id."""

        report = self.db.get(AttendanceMonthlyReport, report_id)
        if report is None:
            raise AdminPanelNotFoundError("Attendance monthly report not found.")

        return report

    def generate_monthly_reports(
        self,
        payload: AttendanceMonthlyReportGenerateRequest,
    ) -> list[AttendanceMonthlyReport]:
        """Generate attendance monthly reports."""

        return self.attendance_service.generate_monthly_reports(payload)

    def list_team_objectives(
        self,
        *,
        team_id: int | None,
        include_inactive: bool,
    ) -> list[TeamObjective]:
        """List team objectives."""

        return self.performance_service.list_team_objectives(
            team_id=team_id,
            include_inactive=include_inactive,
        )

    def get_team_objective(self, objective_id: int) -> TeamObjective:
        """Return one team objective by id."""

        return self.performance_service.get_team_objective(objective_id)

    def create_team_objective(
        self,
        payload: TeamObjectiveCreateRequest,
    ) -> TeamObjective:
        """Create a team objective."""

        return self.performance_service.create_team_objective(payload)

    def update_team_objective(
        self,
        objective_id: int,
        payload: TeamObjectiveUpdateRequest,
    ) -> TeamObjective:
        """Update a team objective."""

        return self.performance_service.update_team_objective(objective_id, payload)

    def list_daily_performances(
        self,
        *,
        team_id: int | None,
        department_id: int | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> list[TeamDailyPerformance]:
        """List daily performance records with admin filters."""

        self._validate_date_range(date_from=date_from, date_to=date_to)
        statement: Select[tuple[TeamDailyPerformance]] = (
            select(TeamDailyPerformance)
            .join(Team, Team.id == TeamDailyPerformance.team_id)
        )

        if team_id is not None:
            statement = statement.where(TeamDailyPerformance.team_id == team_id)

        if department_id is not None:
            statement = statement.where(Team.department_id == department_id)

        if date_from is not None:
            statement = statement.where(TeamDailyPerformance.performance_date >= date_from)

        if date_to is not None:
            statement = statement.where(TeamDailyPerformance.performance_date <= date_to)

        statement = statement.order_by(
            TeamDailyPerformance.performance_date.desc(),
            Team.name.asc(),
            TeamDailyPerformance.id.desc(),
        ).limit(limit)
        return list(self.db.execute(statement).scalars().all())

    def get_daily_performance_by_id(self, performance_id: int) -> TeamDailyPerformance:
        """Return one daily performance record by id."""

        performance = self.db.get(TeamDailyPerformance, performance_id)
        if performance is None:
            raise AdminPanelNotFoundError("Performance record not found.")

        return performance

    def submit_daily_performance(
        self,
        current_user: User,
        payload: TeamDailyPerformanceCreateRequest,
    ) -> TeamDailyPerformance:
        """Submit one daily performance record as super admin."""

        return self.performance_service.submit_daily_performance(current_user, payload)

    def get_job_title_permissions(self, job_title_id: int) -> list[Permission]:
        """Return permissions assigned to one job title."""

        return self.permissions_service.get_permissions_for_job_title(job_title_id)

    def get_department_teams(self, department_id: int) -> list[Team]:
        """Return teams belonging to a department."""

        return list(
            self.db.execute(
                select(Team)
                .where(Team.department_id == department_id)
                .order_by(Team.name.asc(), Team.id.asc())
            ).scalars().all()
        )

    def get_department_employees(self, department_id: int) -> list[Employee]:
        """Return employees assigned to a department."""

        return list(
            self.db.execute(
                select(Employee)
                .where(Employee.department_id == department_id)
                .order_by(Employee.last_name.asc(), Employee.first_name.asc(), Employee.id.asc())
            ).scalars().all()
        )

    def get_team_employees(self, team_id: int) -> list[Employee]:
        """Return employees assigned to a team."""

        return list(
            self.db.execute(
                select(Employee)
                .where(Employee.team_id == team_id)
                .order_by(Employee.last_name.asc(), Employee.first_name.asc(), Employee.id.asc())
            ).scalars().all()
        )

    def get_job_title_employees(self, job_title_id: int) -> list[Employee]:
        """Return employees assigned to a job title."""

        return list(
            self.db.execute(
                select(Employee)
                .where(Employee.job_title_id == job_title_id)
                .order_by(Employee.last_name.asc(), Employee.first_name.asc(), Employee.id.asc())
            ).scalars().all()
        )

    def get_permission_job_titles(self, permission_id: int) -> list[JobTitle]:
        """Return job titles assigned to one permission."""

        return list(
            self.db.execute(
                select(JobTitle)
                .join(
                    JobTitlePermissionAssignment,
                    JobTitlePermissionAssignment.job_title_id == JobTitle.id,
                )
                .where(JobTitlePermissionAssignment.permission_id == permission_id)
                .order_by(JobTitle.name.asc(), JobTitle.id.asc())
            ).scalars().all()
        )

    def get_request_type_fields(self, request_type_id: int) -> list[RequestTypeField]:
        """Return the fields configured for a request type."""

        return list(
            self.db.execute(
                select(RequestTypeField)
                .where(RequestTypeField.request_type_id == request_type_id)
                .order_by(RequestTypeField.sort_order.asc(), RequestTypeField.id.asc())
            ).scalars().all()
        )

    def get_request_type_steps(self, request_type_id: int) -> list[RequestWorkflowStep]:
        """Return the workflow steps configured for a request type."""

        return list(
            self.db.execute(
                select(RequestWorkflowStep)
                .where(RequestWorkflowStep.request_type_id == request_type_id)
                .order_by(RequestWorkflowStep.step_order.asc(), RequestWorkflowStep.id.asc())
            ).scalars().all()
        )

    def get_recent_employee_attendance(
        self,
        employee_id: int,
        *,
        limit: int = 10,
    ) -> list[AttendanceDailySummary]:
        """Return recent attendance daily summaries for one employee."""

        return list(
            self.db.execute(
                select(AttendanceDailySummary)
                .where(AttendanceDailySummary.employee_id == employee_id)
                .order_by(
                    AttendanceDailySummary.attendance_date.desc(),
                    AttendanceDailySummary.id.desc(),
                )
                .limit(limit)
            ).scalars().all()
        )

    def get_recent_employee_requests(
        self,
        employee_id: int,
        *,
        limit: int = 10,
    ) -> list[WorkflowRequest]:
        """Return recent requests submitted by one employee."""

        return list(
            self.db.execute(
                select(WorkflowRequest)
                .where(WorkflowRequest.requester_employee_id == employee_id)
                .order_by(WorkflowRequest.submitted_at.desc(), WorkflowRequest.id.desc())
                .limit(limit)
            ).scalars().all()
        )

    def get_recent_team_performances(
        self,
        team_id: int,
        *,
        limit: int = 10,
    ) -> list[TeamDailyPerformance]:
        """Return recent performance records for one team."""

        return list(
            self.db.execute(
                select(TeamDailyPerformance)
                .where(TeamDailyPerformance.team_id == team_id)
                .order_by(
                    TeamDailyPerformance.performance_date.desc(),
                    TeamDailyPerformance.id.desc(),
                )
                .limit(limit)
            ).scalars().all()
        )

    def list_lookup_users(self, *, include_inactive: bool = False) -> list[User]:
        """Return users for select inputs."""

        statement: Select[tuple[User]] = select(User)
        if not include_inactive:
            statement = statement.where(User.is_active.is_(True))

        statement = statement.order_by(
            User.first_name.asc(),
            User.last_name.asc(),
            User.matricule.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def list_lookup_departments(self, *, include_inactive: bool = False) -> list[Department]:
        """Return departments for select inputs."""

        return self.organization_service.list_departments(include_inactive=include_inactive)

    def list_lookup_teams(self, *, include_inactive: bool = False) -> list[Team]:
        """Return teams for select inputs."""

        return self.organization_service.list_teams(include_inactive=include_inactive)

    def list_lookup_job_titles(self, *, include_inactive: bool = False) -> list[JobTitle]:
        """Return job titles for select inputs."""

        return self.organization_service.list_job_titles(include_inactive=include_inactive)

    def list_lookup_permissions(self, *, include_inactive: bool = True) -> list[Permission]:
        """Return permissions for multiselect inputs."""

        return self.permissions_service.list_permissions(include_inactive=include_inactive)

    def list_lookup_request_types(self, *, include_inactive: bool = True) -> list[RequestType]:
        """Return request types for select inputs."""

        return self.requests_service.list_request_types(include_inactive=include_inactive)

    def build_employee_name(self, employee: Employee) -> str:
        """Build a readable employee full name."""

        return f"{employee.first_name} {employee.last_name}"

    def build_user_name(self, user: User) -> str:
        """Build a readable user full name."""

        return f"{user.first_name} {user.last_name}"

    def _create_csrf_token(self, *, subject: str) -> str:
        """Create a short-lived signed CSRF token."""

        return JWTManager.create_access_token(
            subject=subject,
            secret_key=self.settings.secret_key.get_secret_value(),
            expires_delta=timedelta(minutes=30),
            algorithm=self.settings.jwt_algorithm,
            extra_claims={"kind": self.CSRF_KIND},
        )

    def _validate_csrf_token(self, *, token: str | None, subject: str) -> None:
        """Validate a signed CSRF token."""

        if token is None:
            raise AdminPanelAuthenticationError("Missing form security token.")

        try:
            payload = JWTManager.decode_token(
                token=token,
                secret_key=self.settings.secret_key.get_secret_value(),
                algorithm=self.settings.jwt_algorithm,
            )
        except TokenValidationError as exc:
            raise AdminPanelAuthenticationError("Invalid or expired form security token.") from exc

        if payload.get("kind") != self.CSRF_KIND or payload.get("sub") != subject:
            raise AdminPanelAuthenticationError("Invalid form security token.")

    def _ensure_unique_user_identity(
        self,
        matricule: str,
        email: str,
        *,
        current_user_id: int | None = None,
        current_employee_id: int | None = None,
    ) -> None:
        """Ensure user identity fields stay unique across users and employees."""

        user_statement = select(User).where(
            or_(User.matricule == matricule, User.email == email)
        )
        if current_user_id is not None:
            user_statement = user_statement.where(User.id != current_user_id)

        existing_user = self.db.execute(user_statement.limit(1)).scalar_one_or_none()
        if existing_user is not None:
            raise AdminPanelConflictError(
                "An existing user account already uses this matricule or email."
            )

        employee_statement = select(Employee).where(
            or_(Employee.matricule == matricule, Employee.email == email)
        )
        if current_employee_id is not None:
            employee_statement = employee_statement.where(Employee.id != current_employee_id)

        existing_employee = self.db.execute(employee_statement.limit(1)).scalar_one_or_none()
        if existing_employee is not None:
            raise AdminPanelConflictError(
                "An employee profile already uses this matricule or email."
            )

    def _require_active_user_reference(self, user_id: int, label: str) -> User:
        """Require a referenced user to exist and remain active."""

        user = self.db.get(User, user_id)
        if user is None:
            raise AdminPanelValidationError(f"{label} must reference an existing user.")

        if not user.is_active:
            raise AdminPanelValidationError(f"{label} must reference an active user.")

        return user

    def _validate_date_range(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> None:
        """Validate a date range."""

        if date_from is not None and date_to is not None and date_from > date_to:
            raise AdminPanelValidationError("date_from cannot be after date_to.")

    def _build_datetime_range_filters(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> list[Any]:
        """Build UTC datetime filters for request submission dates."""

        self._validate_date_range(date_from=date_from, date_to=date_to)
        filters: list[Any] = []
        if date_from is not None:
            filters.append(
                WorkflowRequest.submitted_at
                >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            )
        if date_to is not None:
            filters.append(
                WorkflowRequest.submitted_at
                < datetime.combine(
                    date_to + timedelta(days=1),
                    time.min,
                    tzinfo=timezone.utc,
                )
            )

        return filters

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit the current transaction and refresh the target instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AdminPanelConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
