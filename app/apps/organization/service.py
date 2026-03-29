from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
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


@dataclass(slots=True)
class _HierarchyPersonRecord:
    """In-memory hierarchy projection for one user/person node."""

    user: User
    employee: Employee | None
    job_title: JobTitle | None
    department: Department | None
    team: Team | None

    @property
    def full_name(self) -> str:
        """Return the display name for the person."""

        first_name = (
            self.employee.first_name if self.employee is not None else self.user.first_name
        )
        last_name = (
            self.employee.last_name if self.employee is not None else self.user.last_name
        )
        full_name = " ".join(
            part.strip() for part in (first_name, last_name) if part and part.strip()
        )
        return full_name or self.user.matricule

    @property
    def hierarchical_level(self) -> int:
        """Return the job-title hierarchy level used for stable sorting."""

        if self.job_title is None:
            return 0

        return self.job_title.hierarchical_level


@dataclass(slots=True)
class _HierarchySnapshot:
    """Cached active organization records used for tree construction."""

    records_by_user_id: dict[int, _HierarchyPersonRecord]
    departments_by_id: dict[int, Department]
    teams_by_id: dict[int, Team]
    department_ids_by_manager_user_id: dict[int, list[int]]
    team_ids_by_leader_user_id: dict[int, list[int]]


class OrganizationService:
    """Service layer for organization structure management."""

    RH_MANAGER_JOB_TITLE_CODE = "RH_MANAGER"

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

    def get_current_user_hierarchy(self, current_user: User) -> dict[str, object]:
        """Return the hierarchy tree relevant to the current authenticated user."""

        snapshot = self._load_active_hierarchy_snapshot()
        root_record = self._get_current_user_record(current_user, snapshot)

        if current_user.is_super_admin or self._is_rh_manager(root_record):
            child_nodes = [
                node
                for node in self._build_company_roots(snapshot)
                if node["user_id"] != current_user.id
            ]
        elif self._get_managed_departments(current_user.id, snapshot):
            child_nodes = self._build_department_manager_children(
                current_user.id,
                snapshot,
            )
        elif self._get_led_teams(current_user.id, snapshot):
            child_nodes = self._build_team_leader_children(current_user.id, snapshot)
        else:
            child_nodes = []

        return {"root": self._serialize_person_node(root_record, child_nodes)}

    def get_company_hierarchy(self) -> dict[str, object]:
        """Return the full company organigram forest."""

        snapshot = self._load_active_hierarchy_snapshot()
        return {"roots": self._build_company_roots(snapshot)}

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

    def _load_active_hierarchy_snapshot(self) -> _HierarchySnapshot:
        """Load the active organization records needed for hierarchy rendering."""

        departments = list(
            self.db.execute(
                select(Department)
                .where(Department.is_active.is_(True))
                .order_by(Department.name.asc(), Department.id.asc())
            )
            .scalars()
            .all()
        )
        teams = list(
            self.db.execute(
                select(Team)
                .where(Team.is_active.is_(True))
                .order_by(Team.name.asc(), Team.id.asc())
            )
            .scalars()
            .all()
        )
        job_titles = list(
            self.db.execute(
                select(JobTitle)
                .where(JobTitle.is_active.is_(True))
                .order_by(
                    JobTitle.hierarchical_level.desc(),
                    JobTitle.name.asc(),
                    JobTitle.id.asc(),
                )
            )
            .scalars()
            .all()
        )

        departments_by_id = {department.id: department for department in departments}
        teams_by_id = {team.id: team for team in teams}
        job_titles_by_id = {job_title.id: job_title for job_title in job_titles}

        department_ids_by_manager_user_id: dict[int, list[int]] = defaultdict(list)
        for department in departments:
            if department.manager_user_id is not None:
                department_ids_by_manager_user_id[department.manager_user_id].append(
                    department.id
                )

        team_ids_by_leader_user_id: dict[int, list[int]] = defaultdict(list)
        for team in teams:
            if team.leader_user_id is not None:
                team_ids_by_leader_user_id[team.leader_user_id].append(team.id)

        employee_rows = self.db.execute(
            select(Employee, User)
            .join(User, User.id == Employee.user_id)
            .where(
                Employee.is_active.is_(True),
                User.is_active.is_(True),
            )
            .order_by(
                Employee.last_name.asc(),
                Employee.first_name.asc(),
                Employee.id.asc(),
            )
        ).all()

        records_by_user_id: dict[int, _HierarchyPersonRecord] = {}
        for employee, user in employee_rows:
            team = teams_by_id.get(employee.team_id) if employee.team_id is not None else None
            department = (
                departments_by_id.get(employee.department_id)
                if employee.department_id is not None
                else None
            )
            if department is None and team is not None:
                department = departments_by_id.get(team.department_id)

            records_by_user_id[user.id] = _HierarchyPersonRecord(
                user=user,
                employee=employee,
                job_title=job_titles_by_id.get(employee.job_title_id),
                department=department,
                team=team,
            )

        return _HierarchySnapshot(
            records_by_user_id=records_by_user_id,
            departments_by_id=departments_by_id,
            teams_by_id=teams_by_id,
            department_ids_by_manager_user_id=dict(department_ids_by_manager_user_id),
            team_ids_by_leader_user_id=dict(team_ids_by_leader_user_id),
        )

    def _get_current_user_record(
        self,
        current_user: User,
        snapshot: _HierarchySnapshot,
    ) -> _HierarchyPersonRecord:
        """Return the projected current-user node, even without an employee profile."""

        record = snapshot.records_by_user_id.get(current_user.id)
        if record is not None:
            return record

        return _HierarchyPersonRecord(
            user=current_user,
            employee=None,
            job_title=None,
            department=None,
            team=None,
        )

    def _is_rh_manager(self, record: _HierarchyPersonRecord) -> bool:
        """Return whether the projected person is an RH manager."""

        if record.job_title is None:
            return False

        return record.job_title.code == self.RH_MANAGER_JOB_TITLE_CODE

    def _get_managed_departments(
        self,
        user_id: int,
        snapshot: _HierarchySnapshot,
    ) -> list[Department]:
        """Return active departments managed by the provided user."""

        department_ids = snapshot.department_ids_by_manager_user_id.get(user_id, [])
        departments = [
            snapshot.departments_by_id[department_id]
            for department_id in department_ids
            if department_id in snapshot.departments_by_id
        ]
        return sorted(departments, key=lambda item: (item.name.casefold(), item.id))

    def _get_led_teams(
        self,
        user_id: int,
        snapshot: _HierarchySnapshot,
    ) -> list[Team]:
        """Return active teams led by the provided user."""

        team_ids = snapshot.team_ids_by_leader_user_id.get(user_id, [])
        teams = [
            snapshot.teams_by_id[team_id]
            for team_id in team_ids
            if team_id in snapshot.teams_by_id
        ]
        return sorted(teams, key=lambda item: (item.name.casefold(), item.id))

    def _build_company_roots(self, snapshot: _HierarchySnapshot) -> list[dict[str, object]]:
        """Build the company-wide hierarchy forest."""

        if not snapshot.records_by_user_id:
            return []

        records_by_level: dict[int, list[_HierarchyPersonRecord]] = defaultdict(list)
        for record in snapshot.records_by_user_id.values():
            records_by_level[record.hierarchical_level].append(record)

        for level_records in records_by_level.values():
            level_records.sort(key=self._person_sort_key)

        highest_level = max(records_by_level)
        root_user_ids = [record.user.id for record in records_by_level[highest_level]]
        children_by_user_id: dict[int, list[int]] = defaultdict(list)

        # Only the highest level becomes a root. Everyone else is attached to the
        # nearest available higher level so the rendered tree always descends.
        for level in sorted(records_by_level.keys(), reverse=True):
            if level == highest_level:
                continue

            for record in records_by_level[level]:
                parent_user_id = self._resolve_company_parent_user_id(
                    record,
                    snapshot,
                    records_by_level,
                )
                if parent_user_id is None or parent_user_id == record.user.id:
                    continue

                children_by_user_id[parent_user_id].append(record.user.id)

        return [
            self._build_company_tree_node(user_id, children_by_user_id, snapshot, set())
            for user_id in root_user_ids
        ]

    def _resolve_company_parent_user_id(
        self,
        record: _HierarchyPersonRecord,
        snapshot: _HierarchySnapshot,
        records_by_level: dict[int, list[_HierarchyPersonRecord]],
    ) -> int | None:
        """Resolve a valid higher-level parent, preferring the immediate next level."""

        candidate_levels = sorted(
            level for level in records_by_level if level > record.hierarchical_level
        )
        if not candidate_levels:
            return None

        strict_parent_level = record.hierarchical_level + 1
        target_parent_level = (
            strict_parent_level
            if strict_parent_level in records_by_level
            else candidate_levels[0]
        )
        candidates = [
            candidate
            for candidate in records_by_level[target_parent_level]
            if candidate.user.id != record.user.id
        ]
        if not candidates:
            return None

        best_parent = min(
            candidates,
            key=lambda candidate: self._company_parent_candidate_sort_key(
                record,
                candidate,
                snapshot,
            ),
        )
        return best_parent.user.id

    def _company_parent_candidate_sort_key(
        self,
        child: _HierarchyPersonRecord,
        candidate: _HierarchyPersonRecord,
        snapshot: _HierarchySnapshot,
    ) -> tuple[int, int, int, int, int, int, str, int]:
        """Rank valid same-level parent candidates using organization context."""

        is_child_team_leader = int(
            child.team is not None and child.team.leader_user_id == candidate.user.id
        )
        is_child_department_manager = int(
            child.department is not None
            and child.department.manager_user_id == candidate.user.id
        )
        is_same_team = int(
            child.team is not None
            and candidate.team is not None
            and child.team.id == candidate.team.id
        )
        is_same_department = int(
            child.department is not None
            and candidate.department is not None
            and child.department.id == candidate.department.id
        )
        manages_department = int(
            bool(snapshot.department_ids_by_manager_user_id.get(candidate.user.id))
        )
        leads_team = int(bool(snapshot.team_ids_by_leader_user_id.get(candidate.user.id)))

        return (
            -is_child_team_leader,
            -is_child_department_manager,
            -is_same_team,
            -is_same_department,
            -manages_department,
            -leads_team,
            candidate.full_name.casefold(),
            candidate.user.id,
        )

    def _build_company_tree_node(
        self,
        user_id: int,
        children_by_user_id: dict[int, list[int]],
        snapshot: _HierarchySnapshot,
        ancestry: set[int],
    ) -> dict[str, object]:
        """Build one recursive company node while guarding against cycles."""

        record = snapshot.records_by_user_id[user_id]
        next_ancestry = set(ancestry)
        next_ancestry.add(user_id)

        child_user_ids = sorted(
            set(children_by_user_id.get(user_id, [])),
            key=lambda child_id: self._person_sort_key(snapshot.records_by_user_id[child_id]),
        )
        child_nodes = [
            self._build_company_tree_node(child_id, children_by_user_id, snapshot, next_ancestry)
            for child_id in child_user_ids
            if child_id not in next_ancestry
        ]
        return self._serialize_person_node(record, child_nodes)

    def _build_department_manager_children(
        self,
        user_id: int,
        snapshot: _HierarchySnapshot,
    ) -> list[dict[str, object]]:
        """Build the department-manager view rooted at the current user."""

        managed_departments = self._get_managed_departments(user_id, snapshot)
        if not managed_departments:
            return []

        managed_department_ids = {department.id for department in managed_departments}
        leader_team_ids_by_user_id: dict[int, list[int]] = defaultdict(list)
        unmanaged_team_ids: set[int] = set()

        for team in self._get_department_teams(managed_department_ids, snapshot):
            leader_user_id = team.leader_user_id
            if (
                leader_user_id is None
                or leader_user_id == user_id
                or leader_user_id not in snapshot.records_by_user_id
            ):
                unmanaged_team_ids.add(team.id)
                continue

            leader_team_ids_by_user_id[leader_user_id].append(team.id)

        child_nodes: list[dict[str, object]] = []

        for leader_user_id in sorted(
            leader_team_ids_by_user_id,
            key=lambda item: self._person_sort_key(snapshot.records_by_user_id[item]),
        ):
            leader_record = snapshot.records_by_user_id[leader_user_id]
            seen_member_ids: set[int] = set()
            leader_children: list[dict[str, object]] = []

            for team_id in leader_team_ids_by_user_id[leader_user_id]:
                for member_record in self._get_team_member_records(
                    team_id,
                    snapshot,
                    exclude_user_ids={user_id, leader_user_id},
                ):
                    if member_record.user.id in seen_member_ids:
                        continue

                    seen_member_ids.add(member_record.user.id)
                    leader_children.append(self._serialize_person_node(member_record, []))

            child_nodes.append(self._serialize_person_node(leader_record, leader_children))

        direct_records: list[_HierarchyPersonRecord] = []
        for record in snapshot.records_by_user_id.values():
            if record.user.id == user_id or record.department is None:
                continue
            if record.department.id not in managed_department_ids:
                continue

            if record.team is None or record.team.id in unmanaged_team_ids:
                direct_records.append(record)

        direct_records.sort(key=self._person_sort_key)
        child_nodes.extend(
            self._serialize_person_node(record, []) for record in direct_records
        )

        return child_nodes

    def _build_team_leader_children(
        self,
        user_id: int,
        snapshot: _HierarchySnapshot,
    ) -> list[dict[str, object]]:
        """Build the team-leader view rooted at the current user."""

        led_teams = self._get_led_teams(user_id, snapshot)
        if not led_teams:
            return []

        seen_member_ids: set[int] = set()
        member_records: list[_HierarchyPersonRecord] = []

        for team in led_teams:
            for record in self._get_team_member_records(
                team.id,
                snapshot,
                exclude_user_ids={user_id},
            ):
                if record.user.id in seen_member_ids:
                    continue

                seen_member_ids.add(record.user.id)
                member_records.append(record)

        member_records.sort(key=self._person_sort_key)
        return [self._serialize_person_node(record, []) for record in member_records]

    def _get_department_teams(
        self,
        department_ids: set[int],
        snapshot: _HierarchySnapshot,
    ) -> list[Team]:
        """Return active teams belonging to the provided departments."""

        teams = [
            team
            for team in snapshot.teams_by_id.values()
            if team.department_id in department_ids
        ]
        return sorted(teams, key=lambda item: (item.name.casefold(), item.id))

    def _get_team_member_records(
        self,
        team_id: int,
        snapshot: _HierarchySnapshot,
        *,
        exclude_user_ids: set[int] | None = None,
    ) -> list[_HierarchyPersonRecord]:
        """Return active employee nodes belonging to the provided team."""

        excluded_user_ids = exclude_user_ids or set()
        records = [
            record
            for record in snapshot.records_by_user_id.values()
            if record.team is not None
            and record.team.id == team_id
            and record.user.id not in excluded_user_ids
        ]
        return sorted(records, key=self._person_sort_key)

    def _person_sort_key(self, record: _HierarchyPersonRecord) -> tuple[int, str, int]:
        """Return a stable display sort key for hierarchy nodes."""

        return (-record.hierarchical_level, record.full_name.casefold(), record.user.id)

    def _serialize_person_node(
        self,
        record: _HierarchyPersonRecord,
        children: list[dict[str, object]],
    ) -> dict[str, object]:
        """Serialize one hierarchy node to the public response shape."""

        return {
            "user_id": record.user.id,
            "full_name": record.full_name,
            "image": record.employee.image if record.employee is not None else None,
            "job_title": record.job_title.name if record.job_title is not None else None,
            "department": record.department.name if record.department is not None else None,
            "team": record.team.name if record.team is not None else None,
            "children": children,
        }

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit the current transaction and refresh the target instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise OrganizationConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
