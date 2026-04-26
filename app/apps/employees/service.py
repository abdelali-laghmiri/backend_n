from __future__ import annotations

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
from app.apps.employees.schemas import EmployeeCreateRequest, EmployeeUpdateRequest
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.users.models import User
from app.core.security import PasswordManager, generate_temporary_password


class EmployeesConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class EmployeesNotFoundError(RuntimeError):
    """Raised when an employee-related record cannot be found."""


class EmployeesValidationError(RuntimeError):
    """Raised when an employee request is invalid."""


class EmployeesService:
    """Service layer for employee and linked user-account management."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_employee(self, payload: EmployeeCreateRequest) -> tuple[Employee, str]:
        """Create an employee and its linked authentication account."""

        self._ensure_unique_user_identity(payload.matricule, payload.email)
        self._ensure_unique_employee_identity(payload.matricule, payload.email)
        department_id, team_id = self._resolve_department_and_team(
            department_id=payload.department_id,
            team_id=payload.team_id,
            department_explicit=payload.department_id is not None,
        )
        self._validate_job_title(payload.job_title_id)

        temporary_password = generate_temporary_password()
        user = User(
            matricule=payload.matricule,
            password_hash=PasswordManager.hash_password(temporary_password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email).lower(),
            is_super_admin=False,
            is_active=True,
            must_change_password=True,
        )
        self.db.add(user)

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise EmployeesConflictError(
                "Failed to create the linked user account."
            ) from exc

        employee = Employee(
            user_id=user.id,
            matricule=payload.matricule,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email).lower(),
            phone=payload.phone,
            image=payload.image,
            hire_date=payload.hire_date,
            contract_type=payload.contract_type,
            external_company_name=payload.external_company_name,
            available_leave_balance_days=payload.available_leave_balance_days,
            department_id=department_id,
            team_id=team_id,
            job_title_id=payload.job_title_id,
            is_active=True,
        )
        self.db.add(employee)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise EmployeesConflictError("Failed to create the employee profile.") from exc

        self.db.refresh(employee)
        return employee, temporary_password

    def list_employees(
        self,
        *,
        include_inactive: bool = False,
        q: str | None = None,
        department_id: int | None = None,
        team_id: int | None = None,
        job_title_id: int | None = None,
    ) -> list[Employee]:
        """List employees with optional basic filters."""

        statement: Select[tuple[Employee]] = select(Employee)
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))

        if q is not None and q.strip():
            search_term = f"%{q.strip()}%"
            statement = statement.where(
                or_(
                    Employee.matricule.ilike(search_term),
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term),
                    Employee.email.ilike(search_term),
                    Employee.phone.ilike(search_term),
                )
            )

        if department_id is not None:
            statement = statement.where(Employee.department_id == department_id)

        if team_id is not None:
            statement = statement.where(Employee.team_id == team_id)

        if job_title_id is not None:
            statement = statement.where(Employee.job_title_id == job_title_id)

        statement = statement.order_by(
            Employee.last_name.asc(),
            Employee.first_name.asc(),
            Employee.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_employee(self, employee_id: int) -> Employee:
        """Return an employee by id."""

        employee = self.db.get(Employee, employee_id)
        if employee is None:
            raise EmployeesNotFoundError("Employee not found.")

        return employee

    def update_employee(
        self,
        employee_id: int,
        payload: EmployeeUpdateRequest,
    ) -> Employee:
        """Update an employee and keep the linked user account synchronized."""

        employee = self.get_employee(employee_id)
        user = self._get_linked_user(employee.user_id)
        changes = payload.model_dump(exclude_unset=True)
        self._validate_required_update_fields(changes)

        final_matricule = changes.get("matricule", employee.matricule)
        final_first_name = changes.get("first_name", employee.first_name)
        final_last_name = changes.get("last_name", employee.last_name)
        final_email = str(changes.get("email", employee.email)).lower()
        final_phone = changes.get("phone", employee.phone)
        final_image = changes.get("image", employee.image)
        final_hire_date = changes.get("hire_date", employee.hire_date)
        final_contract_type = changes.get(
            "contract_type", employee.contract_type
        )
        final_external_company_name = changes.get(
            "external_company_name", employee.external_company_name
        )
        final_available_leave_balance_days = changes.get(
            "available_leave_balance_days",
            employee.available_leave_balance_days,
        )
        final_job_title_id = changes.get("job_title_id", employee.job_title_id)
        final_is_active = changes.get("is_active", employee.is_active)

        self._ensure_unique_user_identity(
            final_matricule,
            final_email,
            current_user_id=user.id,
        )
        self._ensure_unique_employee_identity(
            final_matricule,
            final_email,
            current_employee_id=employee.id,
        )
        department_id, team_id = self._resolve_department_and_team(
            department_id=changes.get("department_id", employee.department_id),
            team_id=changes.get("team_id", employee.team_id),
            department_explicit="department_id" in changes,
        )
        self._validate_job_title(final_job_title_id)

        user.matricule = final_matricule
        user.first_name = final_first_name
        user.last_name = final_last_name
        user.email = final_email
        user.is_active = final_is_active

        employee.matricule = final_matricule
        employee.first_name = final_first_name
        employee.last_name = final_last_name
        employee.email = final_email
        employee.phone = final_phone
        employee.image = final_image
        employee.hire_date = final_hire_date
        employee.contract_type = final_contract_type
        employee.external_company_name = final_external_company_name
        employee.available_leave_balance_days = final_available_leave_balance_days
        employee.department_id = department_id
        employee.team_id = team_id
        employee.job_title_id = final_job_title_id
        employee.is_active = final_is_active

        self.db.add(user)
        self.db.add(employee)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise EmployeesConflictError("Failed to update the employee.") from exc

        self.db.refresh(employee)
        return employee

    def _validate_required_update_fields(self, changes: dict[str, object]) -> None:
        """Reject null updates for required employee fields."""

        required_fields = {
            "matricule": "Matricule",
            "first_name": "First name",
            "last_name": "Last name",
            "email": "Email",
            "hire_date": "Hire date",
            "contract_type": "Contract type",
            "available_leave_balance_days": "Available leave balance days",
            "job_title_id": "Job title",
        }
        for field_name, label in required_fields.items():
            if field_name in changes and changes[field_name] is None:
                raise EmployeesValidationError(f"{label} cannot be null.")

        if changes.get("contract_type") == "EXTERNAL":
            external_company = changes.get("external_company_name")
            if not external_company or not str(external_company).strip():
                raise EmployeesValidationError(
                    "External company name is required when contract type is EXTERNAL."
                )

    def _resolve_department_and_team(
        self,
        *,
        department_id: int | None,
        team_id: int | None,
        department_explicit: bool,
    ) -> tuple[int | None, int | None]:
        """Resolve organization assignments and enforce consistency rules."""

        final_department_id = department_id
        final_team_id = team_id

        if final_team_id is not None:
            team = self._validate_team(final_team_id)
            if final_department_id is None or not department_explicit:
                final_department_id = team.department_id
            elif team.department_id != final_department_id:
                raise EmployeesValidationError(
                    "The selected team does not belong to the selected department."
                )

        if final_department_id is not None:
            self._validate_department(final_department_id)

        return final_department_id, final_team_id

    def _validate_department(self, department_id: int) -> Department:
        """Validate that the referenced department exists and is active."""

        department = self.db.get(Department, department_id)
        if department is None:
            raise EmployeesValidationError("Department must reference an existing record.")

        if not department.is_active:
            raise EmployeesValidationError("Department must reference an active record.")

        return department

    def _validate_team(self, team_id: int) -> Team:
        """Validate that the referenced team exists and is active."""

        team = self.db.get(Team, team_id)
        if team is None:
            raise EmployeesValidationError("Team must reference an existing record.")

        if not team.is_active:
            raise EmployeesValidationError("Team must reference an active record.")

        return team

    def _validate_job_title(self, job_title_id: int) -> JobTitle:
        """Validate that the referenced job title exists and is active."""

        job_title = self.db.get(JobTitle, job_title_id)
        if job_title is None:
            raise EmployeesValidationError("Job title must reference an existing record.")

        if not job_title.is_active:
            raise EmployeesValidationError("Job title must reference an active record.")

        return job_title

    def _get_linked_user(self, user_id: int) -> User:
        """Return the linked user account for an employee."""

        user = self.db.get(User, user_id)
        if user is None:
            raise EmployeesNotFoundError("Linked user account not found.")

        return user

    def _ensure_unique_user_identity(
        self,
        matricule: str,
        email: str,
        *,
        current_user_id: int | None = None,
    ) -> None:
        """Validate linked user identity uniqueness."""

        user_statement = select(User).where(
            or_(User.matricule == matricule, User.email == email)
        )
        if current_user_id is not None:
            user_statement = user_statement.where(User.id != current_user_id)

        existing_user = self.db.execute(user_statement.limit(1)).scalar_one_or_none()
        if existing_user is not None:
            raise EmployeesConflictError(
                "An existing user account already uses this matricule or email."
            )

    def _ensure_unique_employee_identity(
        self,
        matricule: str,
        email: str,
        *,
        current_employee_id: int | None = None,
    ) -> None:
        """Validate employee identity uniqueness."""

        employee_statement = select(Employee).where(
            or_(Employee.matricule == matricule, Employee.email == email)
        )
        if current_employee_id is not None:
            employee_statement = employee_statement.where(Employee.id != current_employee_id)

        existing_employee = self.db.execute(
            employee_statement.limit(1)
        ).scalar_one_or_none()
        if existing_employee is not None:
            raise EmployeesConflictError(
                "An existing employee profile already uses this matricule or email."
            )
