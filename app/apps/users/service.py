from __future__ import annotations

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.permissions.service import PermissionsService
from app.apps.users.models import User
from app.apps.users.schemas import UserCreateRequest, UserUpdateRequest
from app.core.security import PasswordManager, generate_temporary_password


class UsersNotFoundError(RuntimeError):
    """Raised when a user record cannot be found."""


class UsersConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents user changes."""


class UsersValidationError(RuntimeError):
    """Raised when user payload validation fails at service level."""


class UsersService:
    """Service layer for user management operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.permissions_service = PermissionsService(db=db)

    def list_users(
        self,
        *,
        q: str | None,
        include_inactive: bool,
        limit: int,
    ) -> list[User]:
        """List users with optional search and active-state filtering."""

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
            raise UsersNotFoundError("User not found.")

        return user

    def get_linked_employee_by_user_id(self, user_id: int) -> Employee | None:
        """Return the employee profile linked to a user account, if one exists."""

        return self.db.execute(
            select(Employee).where(Employee.user_id == user_id).limit(1)
        ).scalar_one_or_none()

    def create_user(self, payload: UserCreateRequest) -> User:
        """Create one internal user account."""

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
        payload: UserUpdateRequest,
        *,
        current_admin: User,
    ) -> User:
        """Update one internal user account and its linked employee role fields."""

        user = self.get_user(user_id)
        linked_employee = self.get_linked_employee_by_user_id(user.id)
        changes = payload.model_dump(exclude_unset=True)

        if user.id == current_admin.id:
            if changes.get("is_active") is False:
                raise UsersValidationError(
                    "You cannot deactivate the currently authenticated super admin."
                )
            if changes.get("is_super_admin") is False:
                raise UsersValidationError(
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

        password = changes.get("password")
        if password:
            user.password_hash = PasswordManager.hash_password(password)
            user.must_change_password = changes.get("must_change_password", False)

        self.db.add(user)

        if linked_employee is not None:
            linked_employee.matricule = final_matricule
            linked_employee.first_name = final_first_name
            linked_employee.last_name = final_last_name
            linked_employee.email = final_email
            linked_employee.is_active = final_is_active

            if "department_id" in changes:
                self._ensure_department_exists(changes["department_id"])
                linked_employee.department_id = changes["department_id"]
            if "team_id" in changes:
                self._ensure_team_exists(changes["team_id"])
                linked_employee.team_id = changes["team_id"]
            if "job_title_id" in changes:
                self._ensure_job_title_exists(changes["job_title_id"])
                linked_employee.job_title_id = changes["job_title_id"]

            self.db.add(linked_employee)
        elif any(
            field in changes for field in ("department_id", "team_id", "job_title_id")
        ):
            raise UsersValidationError(
                "Role or organization fields can only be updated for users linked to an employee profile."
            )

        return self._commit_and_refresh(
            user,
            conflict_message="Failed to update the user account.",
        )

    def set_user_active(
        self,
        user_id: int,
        *,
        is_active: bool,
        current_admin: User,
    ) -> User:
        """Activate or deactivate one user account."""

        payload = UserUpdateRequest(is_active=is_active)
        return self.update_user(user_id, payload, current_admin=current_admin)

    def reset_user_password(
        self,
        user_id: int,
        *,
        current_admin: User,
    ) -> tuple[User, str]:
        """Generate a one-time temporary password and require password change."""

        user = self.get_user(user_id)
        temporary_password = generate_temporary_password()
        user.password_hash = PasswordManager.hash_password(temporary_password)
        user.must_change_password = True

        if user.id == current_admin.id:
            user.is_super_admin = True
            user.is_active = True

        self.db.add(user)
        refreshed_user = self._commit_and_refresh(
            user,
            conflict_message="Failed to reset the user password.",
        )
        return refreshed_user, temporary_password

    def get_effective_permissions_snapshot(self, user_id: int) -> dict[str, object]:
        """Return the effective permission state for one target user account."""

        user = self.get_user(user_id)
        linked_employee = self.get_linked_employee_by_user_id(user.id)
        effective_permissions = self.permissions_service.resolve_effective_permissions(user)

        return {
            "user_id": user.id,
            "has_full_access": effective_permissions.has_full_access,
            "permissions": effective_permissions.permissions,
            "linked_employee_job_title_id": (
                linked_employee.job_title_id if linked_employee is not None else None
            ),
        }

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
            raise UsersConflictError(
                "An existing user account already uses this matricule or email."
            )

        employee_statement = select(Employee).where(
            or_(Employee.matricule == matricule, Employee.email == email)
        )
        if current_employee_id is not None:
            employee_statement = employee_statement.where(Employee.id != current_employee_id)

        existing_employee = self.db.execute(employee_statement.limit(1)).scalar_one_or_none()
        if existing_employee is not None:
            raise UsersConflictError(
                "An employee profile already uses this matricule or email."
            )

    def _ensure_department_exists(self, department_id: int | None) -> None:
        if department_id is None:
            return

        if self.db.get(Department, department_id) is None:
            raise UsersValidationError("Department not found.")

    def _ensure_team_exists(self, team_id: int | None) -> None:
        if team_id is None:
            return

        if self.db.get(Team, team_id) is None:
            raise UsersValidationError("Team not found.")

    def _ensure_job_title_exists(self, job_title_id: int | None) -> None:
        if job_title_id is None:
            return

        if self.db.get(JobTitle, job_title_id) is None:
            raise UsersValidationError("Job title not found.")

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit changes and refresh one SQLAlchemy model instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise UsersConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
