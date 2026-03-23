from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.organization.models import Department, JobTitle, Team
from app.apps.organization.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    JobTitleCreateRequest,
    JobTitleUpdateRequest,
    TeamCreateRequest,
    TeamUpdateRequest,
)
from app.apps.users.models import User


class OrganizationConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class OrganizationNotFoundError(RuntimeError):
    """Raised when an organization record cannot be found."""


class OrganizationValidationError(RuntimeError):
    """Raised when an organization request is invalid."""


class OrganizationService:
    """Service layer for organization structure management."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_department(self, payload: DepartmentCreateRequest) -> Department:
        """Create a department."""

        self._ensure_unique_code(
            Department,
            payload.code,
            "Department code already exists.",
        )
        self._validate_user_reference(
            payload.manager_user_id,
            "Department manager",
        )

        department = Department(
            name=payload.name,
            code=payload.code,
            description=payload.description,
            manager_user_id=payload.manager_user_id,
            is_active=True,
        )
        self.db.add(department)
        return self._commit_and_refresh(
            department,
            conflict_message="Failed to create the department.",
        )

    def list_departments(self, *, include_inactive: bool = False) -> list[Department]:
        """List departments."""

        statement: Select[tuple[Department]] = select(Department)
        if not include_inactive:
            statement = statement.where(Department.is_active.is_(True))

        statement = statement.order_by(Department.name.asc(), Department.id.asc())
        return list(self.db.execute(statement).scalars().all())

    def get_department(self, department_id: int) -> Department:
        """Return a department by id."""

        department = self.db.get(Department, department_id)
        if department is None:
            raise OrganizationNotFoundError("Department not found.")

        return department

    def update_department(
        self,
        department_id: int,
        payload: DepartmentUpdateRequest,
    ) -> Department:
        """Update a department."""

        department = self.get_department(department_id)
        changes = payload.model_dump(exclude_unset=True)

        if "code" in changes:
            self._ensure_unique_code(
                Department,
                changes["code"],
                "Department code already exists.",
                current_id=department.id,
            )

        if "manager_user_id" in changes:
            self._validate_user_reference(
                changes["manager_user_id"],
                "Department manager",
            )

        for field_name, value in changes.items():
            setattr(department, field_name, value)

        self.db.add(department)
        return self._commit_and_refresh(
            department,
            conflict_message="Failed to update the department.",
        )

    def deactivate_department(self, department_id: int) -> Department:
        """Deactivate a department if it has no active teams."""

        department = self.get_department(department_id)
        if not department.is_active:
            return department

        active_team = self.db.execute(
            select(Team)
            .where(Team.department_id == department.id, Team.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if active_team is not None:
            raise OrganizationConflictError(
                "Deactivate or move active teams before deactivating this department."
            )

        department.is_active = False
        self.db.add(department)
        return self._commit_and_refresh(
            department,
            conflict_message="Failed to deactivate the department.",
        )

    def create_team(self, payload: TeamCreateRequest) -> Team:
        """Create a team."""

        self._ensure_unique_code(
            Team,
            payload.code,
            "Team code already exists.",
        )
        self._validate_department_reference(payload.department_id)
        self._validate_user_reference(payload.leader_user_id, "Team leader")

        team = Team(
            name=payload.name,
            code=payload.code,
            description=payload.description,
            department_id=payload.department_id,
            leader_user_id=payload.leader_user_id,
            is_active=True,
        )
        self.db.add(team)
        return self._commit_and_refresh(
            team,
            conflict_message="Failed to create the team.",
        )

    def list_teams(self, *, include_inactive: bool = False) -> list[Team]:
        """List teams."""

        statement: Select[tuple[Team]] = select(Team)
        if not include_inactive:
            statement = statement.where(Team.is_active.is_(True))

        statement = statement.order_by(Team.name.asc(), Team.id.asc())
        return list(self.db.execute(statement).scalars().all())

    def get_team(self, team_id: int) -> Team:
        """Return a team by id."""

        team = self.db.get(Team, team_id)
        if team is None:
            raise OrganizationNotFoundError("Team not found.")

        return team

    def update_team(self, team_id: int, payload: TeamUpdateRequest) -> Team:
        """Update a team."""

        team = self.get_team(team_id)
        changes = payload.model_dump(exclude_unset=True)

        if "code" in changes:
            self._ensure_unique_code(
                Team,
                changes["code"],
                "Team code already exists.",
                current_id=team.id,
            )

        if "department_id" in changes:
            self._validate_department_reference(changes["department_id"])

        if "leader_user_id" in changes:
            self._validate_user_reference(changes["leader_user_id"], "Team leader")

        for field_name, value in changes.items():
            setattr(team, field_name, value)

        self.db.add(team)
        return self._commit_and_refresh(
            team,
            conflict_message="Failed to update the team.",
        )

    def deactivate_team(self, team_id: int) -> Team:
        """Deactivate a team."""

        team = self.get_team(team_id)
        if not team.is_active:
            return team

        team.is_active = False
        self.db.add(team)
        return self._commit_and_refresh(
            team,
            conflict_message="Failed to deactivate the team.",
        )

    def create_job_title(self, payload: JobTitleCreateRequest) -> JobTitle:
        """Create a job title."""

        self._ensure_unique_code(
            JobTitle,
            payload.code,
            "Job title code already exists.",
        )

        job_title = JobTitle(
            name=payload.name,
            code=payload.code,
            description=payload.description,
            hierarchical_level=payload.hierarchical_level,
            is_active=True,
        )
        self.db.add(job_title)
        return self._commit_and_refresh(
            job_title,
            conflict_message="Failed to create the job title.",
        )

    def list_job_titles(self, *, include_inactive: bool = False) -> list[JobTitle]:
        """List job titles."""

        statement: Select[tuple[JobTitle]] = select(JobTitle)
        if not include_inactive:
            statement = statement.where(JobTitle.is_active.is_(True))

        statement = statement.order_by(
            JobTitle.hierarchical_level.asc(),
            JobTitle.name.asc(),
            JobTitle.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_job_title(self, job_title_id: int) -> JobTitle:
        """Return a job title by id."""

        job_title = self.db.get(JobTitle, job_title_id)
        if job_title is None:
            raise OrganizationNotFoundError("Job title not found.")

        return job_title

    def update_job_title(
        self,
        job_title_id: int,
        payload: JobTitleUpdateRequest,
    ) -> JobTitle:
        """Update a job title."""

        job_title = self.get_job_title(job_title_id)
        changes = payload.model_dump(exclude_unset=True)

        if "code" in changes:
            self._ensure_unique_code(
                JobTitle,
                changes["code"],
                "Job title code already exists.",
                current_id=job_title.id,
            )

        for field_name, value in changes.items():
            setattr(job_title, field_name, value)

        self.db.add(job_title)
        return self._commit_and_refresh(
            job_title,
            conflict_message="Failed to update the job title.",
        )

    def deactivate_job_title(self, job_title_id: int) -> JobTitle:
        """Deactivate a job title."""

        job_title = self.get_job_title(job_title_id)
        if not job_title.is_active:
            return job_title

        job_title.is_active = False
        self.db.add(job_title)
        return self._commit_and_refresh(
            job_title,
            conflict_message="Failed to deactivate the job title.",
        )

    def _validate_user_reference(
        self,
        user_id: int | None,
        label: str,
    ) -> User | None:
        """Validate that an optional user reference points to an active user."""

        if user_id is None:
            return None

        user = self.db.get(User, user_id)
        if user is None:
            raise OrganizationValidationError(f"{label} must reference an existing user.")

        if not user.is_active:
            raise OrganizationValidationError(f"{label} must reference an active user.")

        return user

    def _validate_department_reference(self, department_id: int) -> Department:
        """Validate that a team department reference points to an active department."""

        department = self.db.get(Department, department_id)
        if department is None:
            raise OrganizationValidationError(
                "Team must belong to an existing department."
            )

        if not department.is_active:
            raise OrganizationValidationError(
                "Team must belong to an active department."
            )

        return department

    def _ensure_unique_code(
        self,
        model,
        code: str,
        conflict_message: str,
        *,
        current_id: int | None = None,
    ) -> None:
        """Validate that a record code remains unique."""

        statement = select(model).where(model.code == code)
        if current_id is not None:
            statement = statement.where(model.id != current_id)

        existing_record = self.db.execute(statement.limit(1)).scalar_one_or_none()
        if existing_record is not None:
            raise OrganizationConflictError(conflict_message)

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit the current transaction and refresh the target instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise OrganizationConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
