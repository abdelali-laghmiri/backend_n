from __future__ import annotations

from sqlalchemy import Select, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
from app.apps.organization.models import JobTitle
from app.apps.permissions.models import JobTitlePermissionAssignment, Permission
from app.apps.permissions.schemas import (
    EffectivePermissionResponse,
    JobTitlePermissionAssignmentRequest,
    JobTitlePermissionAssignmentResponse,
    PermissionCreateRequest,
    PermissionUpdateRequest,
)
from app.apps.users.models import User


class PermissionsConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class PermissionsNotFoundError(RuntimeError):
    """Raised when a permission-related record cannot be found."""


class PermissionsValidationError(RuntimeError):
    """Raised when a permission request is invalid."""


class PermissionsService:
    """Service layer for permission catalog and authorization resolution."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_permission(self, payload: PermissionCreateRequest) -> Permission:
        """Create a permission catalog entry."""

        self._validate_code_matches_module(payload.code, payload.module)
        self._ensure_unique_code(payload.code)

        permission = Permission(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            module=payload.module,
            is_active=True,
        )
        self.db.add(permission)
        return self._commit_and_refresh(
            permission,
            conflict_message="Failed to create the permission.",
        )

    def list_permissions(
        self,
        *,
        include_inactive: bool = False,
        module: str | None = None,
    ) -> list[Permission]:
        """List permission catalog entries."""

        statement: Select[tuple[Permission]] = select(Permission)
        if not include_inactive:
            statement = statement.where(Permission.is_active.is_(True))

        if module is not None and module.strip():
            statement = statement.where(Permission.module == module.strip().lower())

        statement = statement.order_by(Permission.module.asc(), Permission.code.asc())
        return list(self.db.execute(statement).scalars().all())

    def get_permission(self, permission_id: int) -> Permission:
        """Return a permission by id."""

        permission = self.db.get(Permission, permission_id)
        if permission is None:
            raise PermissionsNotFoundError("Permission not found.")

        return permission

    def update_permission(
        self,
        permission_id: int,
        payload: PermissionUpdateRequest,
    ) -> Permission:
        """Update a permission catalog entry."""

        permission = self.get_permission(permission_id)
        changes = payload.model_dump(exclude_unset=True)

        final_code = changes.get("code", permission.code)
        final_module = changes.get("module", permission.module)
        self._validate_code_matches_module(final_code, final_module)

        if final_code != permission.code:
            self._ensure_unique_code(final_code, current_permission_id=permission.id)

        for field_name, value in changes.items():
            setattr(permission, field_name, value)

        self.db.add(permission)
        return self._commit_and_refresh(
            permission,
            conflict_message="Failed to update the permission.",
        )

    def assign_permissions_to_job_title(
        self,
        job_title_id: int,
        payload: JobTitlePermissionAssignmentRequest,
    ) -> JobTitlePermissionAssignmentResponse:
        """Replace the permissions assigned to a job title."""

        job_title = self._get_job_title(job_title_id)
        permissions = self._get_permissions_by_ids(payload.permission_ids)

        self.db.execute(
            delete(JobTitlePermissionAssignment).where(
                JobTitlePermissionAssignment.job_title_id == job_title_id
            )
        )

        for permission in permissions:
            assignment = JobTitlePermissionAssignment(
                job_title_id=job_title_id,
                permission_id=permission.id,
            )
            self.db.add(assignment)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PermissionsConflictError(
                "Failed to assign permissions to the job title."
            ) from exc

        return JobTitlePermissionAssignmentResponse(
            job_title_id=job_title.id,
            job_title_name=job_title.name,
            job_title_code=job_title.code,
            permissions=self.get_permissions_for_job_title(job_title.id),
        )

    def get_job_title_permission_assignment(
        self,
        job_title_id: int,
    ) -> JobTitlePermissionAssignmentResponse:
        """Return the permissions assigned to a job title."""

        job_title = self._get_job_title(job_title_id)
        return JobTitlePermissionAssignmentResponse(
            job_title_id=job_title.id,
            job_title_name=job_title.name,
            job_title_code=job_title.code,
            permissions=self.get_permissions_for_job_title(job_title.id),
        )

    def get_permissions_for_job_title(self, job_title_id: int) -> list[Permission]:
        """Return permission records assigned to a job title."""

        statement = (
            select(Permission)
            .join(
                JobTitlePermissionAssignment,
                JobTitlePermissionAssignment.permission_id == Permission.id,
            )
            .where(JobTitlePermissionAssignment.job_title_id == job_title_id)
            .order_by(Permission.module.asc(), Permission.code.asc())
        )
        return list(self.db.execute(statement).scalars().all())

    def resolve_effective_permissions(self, user: User) -> EffectivePermissionResponse:
        """Resolve the effective permissions for the authenticated user."""

        if user.is_super_admin:
            return EffectivePermissionResponse(has_full_access=True, permissions=[])

        employee = self.db.execute(
            select(Employee)
            .where(Employee.user_id == user.id, Employee.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if employee is None:
            return EffectivePermissionResponse(has_full_access=False, permissions=[])

        statement = (
            select(Permission.code)
            .join(
                JobTitlePermissionAssignment,
                JobTitlePermissionAssignment.permission_id == Permission.id,
            )
            .where(
                JobTitlePermissionAssignment.job_title_id == employee.job_title_id,
                Permission.is_active.is_(True),
            )
            .order_by(Permission.code.asc())
        )
        permission_codes = list(self.db.execute(statement).scalars().all())
        return EffectivePermissionResponse(
            has_full_access=False,
            permissions=permission_codes,
        )

    def user_has_permission(self, user: User, permission_code: str) -> bool:
        """Return whether the user effectively has the requested permission."""

        effective_permissions = self.resolve_effective_permissions(user)
        if effective_permissions.has_full_access:
            return True

        return permission_code in effective_permissions.permissions

    def _ensure_unique_code(
        self,
        code: str,
        *,
        current_permission_id: int | None = None,
    ) -> None:
        """Validate that a permission code remains unique."""

        statement = select(Permission).where(Permission.code == code)
        if current_permission_id is not None:
            statement = statement.where(Permission.id != current_permission_id)

        existing_permission = self.db.execute(statement.limit(1)).scalar_one_or_none()
        if existing_permission is not None:
            raise PermissionsConflictError("Permission code already exists.")

    def _validate_code_matches_module(self, code: str, module: str) -> None:
        """Ensure the permission code module prefix matches the declared module."""

        if not code.startswith(f"{module}."):
            raise PermissionsValidationError(
                "Permission code must start with the declared module prefix."
            )

    def _get_job_title(self, job_title_id: int) -> JobTitle:
        """Return a job title by id."""

        job_title = self.db.get(JobTitle, job_title_id)
        if job_title is None:
            raise PermissionsNotFoundError("Job title not found.")

        return job_title

    def _get_permissions_by_ids(self, permission_ids: list[int]) -> list[Permission]:
        """Return permissions for the provided ids and validate completeness."""

        if not permission_ids:
            return []

        statement = select(Permission).where(Permission.id.in_(permission_ids))
        permissions = list(self.db.execute(statement).scalars().all())
        if len(permissions) != len(permission_ids):
            found_ids = {permission.id for permission in permissions}
            missing_ids = sorted(set(permission_ids) - found_ids)
            missing_list = ", ".join(str(item) for item in missing_ids)
            raise PermissionsValidationError(
                f"Unknown permission ids: {missing_list}."
            )

        permissions_by_id = {permission.id: permission for permission in permissions}
        return [permissions_by_id[permission_id] for permission_id in permission_ids]

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit the transaction and refresh the target instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PermissionsConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
