from __future__ import annotations

from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.organization.models import Team
from app.apps.permissions.service import PermissionsService
from app.apps.performance.models import TeamDailyPerformance, TeamObjective
from app.apps.performance.schemas import (
    TeamDailyPerformanceCreateRequest,
    TeamDailyPerformanceResponse,
    TeamObjectiveCreateRequest,
    TeamObjectiveResponse,
    TeamObjectiveUpdateRequest,
)
from app.apps.users.models import User


class PerformanceConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class PerformanceNotFoundError(RuntimeError):
    """Raised when a performance-related record cannot be found."""


class PerformanceValidationError(RuntimeError):
    """Raised when a performance payload or operation is invalid."""


class PerformanceAuthorizationError(RuntimeError):
    """Raised when a user is not allowed to access a performance resource."""


class PerformanceService:
    """Service layer for team objectives and team-based daily performance."""

    PERFORMANCE_READ_PERMISSION = "performance.read"
    PERFORMANCE_MANAGE_PERMISSION = "performance.manage"

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_team_objective(
        self,
        payload: TeamObjectiveCreateRequest,
    ) -> TeamObjective:
        """Create a team objective and optionally make it the active one."""

        self._get_team(payload.team_id, active_only=True)
        if payload.is_active:
            self._deactivate_other_active_objectives(payload.team_id)

        objective = TeamObjective(
            team_id=payload.team_id,
            objective_value=payload.objective_value,
            objective_type=payload.objective_type,
            is_active=payload.is_active,
        )
        self.db.add(objective)
        return self._commit_and_refresh(
            objective,
            conflict_message="Failed to create the team objective.",
        )

    def update_team_objective(
        self,
        objective_id: int,
        payload: TeamObjectiveUpdateRequest,
    ) -> TeamObjective:
        """Update a team objective."""

        objective = self.get_team_objective(objective_id)
        changes = payload.model_dump(exclude_unset=True)

        if changes.get("is_active") is True:
            self._deactivate_other_active_objectives(
                objective.team_id,
                excluded_objective_id=objective.id,
            )

        for field_name, value in changes.items():
            setattr(objective, field_name, value)

        self.db.add(objective)
        return self._commit_and_refresh(
            objective,
            conflict_message="Failed to update the team objective.",
        )

    def list_team_objectives(
        self,
        *,
        team_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[TeamObjective]:
        """List team objectives with optional filters."""

        statement: Select[tuple[TeamObjective]] = select(TeamObjective)
        if team_id is not None:
            self._get_team(team_id, active_only=False)
            statement = statement.where(TeamObjective.team_id == team_id)

        if not include_inactive:
            statement = statement.where(TeamObjective.is_active.is_(True))

        statement = statement.order_by(
            TeamObjective.team_id.asc(),
            TeamObjective.is_active.desc(),
            TeamObjective.created_at.desc(),
            TeamObjective.id.desc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_team_objective(self, objective_id: int) -> TeamObjective:
        """Return one team objective by id."""

        objective = self.db.get(TeamObjective, objective_id)
        if objective is None:
            raise PerformanceNotFoundError("Team objective not found.")

        return objective

    def get_active_objective_for_team(self, team_id: int) -> TeamObjective:
        """Return the one active objective configured for a team."""

        self._get_team(team_id, active_only=False)
        objectives = list(
            self.db.execute(
                select(TeamObjective)
                .where(
                    TeamObjective.team_id == team_id,
                    TeamObjective.is_active.is_(True),
                )
                .order_by(TeamObjective.created_at.desc(), TeamObjective.id.desc())
            )
            .scalars()
            .all()
        )
        if not objectives:
            raise PerformanceNotFoundError("No active objective exists for this team.")

        if len(objectives) > 1:
            raise PerformanceValidationError(
                "More than one active objective exists for this team."
            )

        return objectives[0]

    def submit_daily_performance(
        self,
        current_user: User,
        payload: TeamDailyPerformanceCreateRequest,
    ) -> TeamDailyPerformance:
        """Submit the achieved value for one team and one day."""

        team = self._get_team(payload.team_id, active_only=True)
        self._authorize_team_submission(team, current_user)
        objective = self.get_active_objective_for_team(team.id)
        self._ensure_unique_daily_performance(team.id, payload.performance_date)

        daily_performance = TeamDailyPerformance(
            team_id=team.id,
            performance_date=payload.performance_date,
            objective_value=objective.objective_value,
            achieved_value=payload.achieved_value,
            performance_percentage=self.calculate_performance_percentage(
                achieved_value=payload.achieved_value,
                objective_value=objective.objective_value,
            ),
            created_by_user_id=current_user.id,
        )
        self.db.add(daily_performance)
        return self._commit_and_refresh(
            daily_performance,
            conflict_message="Failed to submit daily team performance.",
        )

    def list_daily_performances(
        self,
        current_user: User,
        *,
        team_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[TeamDailyPerformance]:
        """List daily performance records visible to the current user."""

        self._validate_date_range(date_from=date_from, date_to=date_to)
        statement: Select[tuple[TeamDailyPerformance]] = select(TeamDailyPerformance)

        if team_id is not None:
            team = self._get_team(team_id, active_only=False)
            self._authorize_team_read(team, current_user)
            statement = statement.where(TeamDailyPerformance.team_id == team_id)
        elif not self._user_has_full_read_access(current_user):
            leader_team_ids = self._get_leader_team_ids(current_user.id)
            if not leader_team_ids:
                return []

            statement = statement.where(TeamDailyPerformance.team_id.in_(leader_team_ids))

        if date_from is not None:
            statement = statement.where(TeamDailyPerformance.performance_date >= date_from)

        if date_to is not None:
            statement = statement.where(TeamDailyPerformance.performance_date <= date_to)

        statement = statement.order_by(
            TeamDailyPerformance.performance_date.desc(),
            TeamDailyPerformance.team_id.asc(),
            TeamDailyPerformance.id.desc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_daily_performance(
        self,
        current_user: User,
        *,
        team_id: int,
        performance_date: date,
    ) -> TeamDailyPerformance:
        """Return one team daily performance record."""

        team = self._get_team(team_id, active_only=False)
        self._authorize_team_read(team, current_user)

        performance = self.db.execute(
            select(TeamDailyPerformance).where(
                TeamDailyPerformance.team_id == team_id,
                TeamDailyPerformance.performance_date == performance_date,
            )
        ).scalar_one_or_none()
        if performance is None:
            raise PerformanceNotFoundError("Daily team performance not found.")

        return performance

    def build_team_objective_responses(
        self,
        objectives: list[TeamObjective],
    ) -> list[TeamObjectiveResponse]:
        """Build objective responses with team context."""

        teams_by_id = self._get_teams_by_ids({objective.team_id for objective in objectives})
        return [
            self._build_team_objective_response(objective, teams_by_id[objective.team_id])
            for objective in objectives
        ]

    def build_team_objective_response(
        self,
        objective: TeamObjective,
    ) -> TeamObjectiveResponse:
        """Build one objective response with team context."""

        team = self._get_team(objective.team_id, active_only=False)
        return self._build_team_objective_response(objective, team)

    def build_daily_performance_responses(
        self,
        performances: list[TeamDailyPerformance],
    ) -> list[TeamDailyPerformanceResponse]:
        """Build daily performance responses with team and creator context."""

        teams_by_id = self._get_teams_by_ids({performance.team_id for performance in performances})
        users_by_id = self._get_users_by_ids(
            {performance.created_by_user_id for performance in performances}
        )
        return [
            self._build_daily_performance_response(
                performance,
                teams_by_id[performance.team_id],
                users_by_id[performance.created_by_user_id],
            )
            for performance in performances
        ]

    def build_daily_performance_response(
        self,
        performance: TeamDailyPerformance,
    ) -> TeamDailyPerformanceResponse:
        """Build one daily performance response with related context."""

        team = self._get_team(performance.team_id, active_only=False)
        user = self._get_user(performance.created_by_user_id)
        return self._build_daily_performance_response(performance, team, user)

    def calculate_performance_percentage(
        self,
        *,
        achieved_value: float,
        objective_value: float,
    ) -> float:
        """Return the achieved percentage stored on a 0-100 scale."""

        if objective_value <= 0:
            raise PerformanceValidationError("objective_value must be greater than zero.")

        if achieved_value < 0:
            raise PerformanceValidationError("achieved_value must be non-negative.")

        return round((achieved_value / objective_value) * 100, 2)

    def _build_team_objective_response(
        self,
        objective: TeamObjective,
        team: Team,
    ) -> TeamObjectiveResponse:
        """Build an objective response payload."""

        return TeamObjectiveResponse(
            id=objective.id,
            team_id=objective.team_id,
            team_code=team.code,
            team_name=team.name,
            objective_value=objective.objective_value,
            objective_type=objective.objective_type,
            is_active=objective.is_active,
            created_at=objective.created_at,
            updated_at=objective.updated_at,
        )

    def _build_daily_performance_response(
        self,
        performance: TeamDailyPerformance,
        team: Team,
        created_by_user: User,
    ) -> TeamDailyPerformanceResponse:
        """Build a daily performance response payload."""

        return TeamDailyPerformanceResponse(
            id=performance.id,
            team_id=performance.team_id,
            team_code=team.code,
            team_name=team.name,
            performance_date=performance.performance_date,
            objective_value=performance.objective_value,
            achieved_value=performance.achieved_value,
            performance_percentage=performance.performance_percentage,
            created_by_user_id=created_by_user.id,
            created_by_matricule=created_by_user.matricule,
            created_by_name=f"{created_by_user.first_name} {created_by_user.last_name}",
            created_at=performance.created_at,
            updated_at=performance.updated_at,
        )

    def _get_team(self, team_id: int, *, active_only: bool) -> Team:
        """Return a team and optionally require it to be active."""

        team = self.db.get(Team, team_id)
        if team is None:
            raise PerformanceNotFoundError("Team not found.")

        if active_only and not team.is_active:
            raise PerformanceValidationError("Team must be active.")

        return team

    def _get_teams_by_ids(self, team_ids: set[int]) -> dict[int, Team]:
        """Load teams in bulk by id."""

        if not team_ids:
            return {}

        teams = list(self.db.execute(select(Team).where(Team.id.in_(team_ids))).scalars().all())
        return {team.id: team for team in teams}

    def _get_user(self, user_id: int) -> User:
        """Return a user by id."""

        user = self.db.get(User, user_id)
        if user is None:
            raise PerformanceNotFoundError("User not found.")

        return user

    def _get_users_by_ids(self, user_ids: set[int]) -> dict[int, User]:
        """Load users in bulk by id."""

        if not user_ids:
            return {}

        users = list(self.db.execute(select(User).where(User.id.in_(user_ids))).scalars().all())
        return {user.id: user for user in users}

    def _authorize_team_submission(self, team: Team, current_user: User) -> None:
        """Require the current user to be the team leader or super admin."""

        if current_user.is_super_admin:
            return

        if team.leader_user_id is None:
            raise PerformanceValidationError("This team does not have a configured leader.")

        if team.leader_user_id != current_user.id:
            raise PerformanceAuthorizationError(
                "Only the configured team leader can submit performance for this team."
            )

    def _authorize_team_read(self, team: Team, current_user: User) -> None:
        """Authorize read access to a team performance scope."""

        if self._user_has_full_read_access(current_user):
            return

        if team.leader_user_id == current_user.id:
            return

        raise PerformanceAuthorizationError(
            "You are not allowed to access performance data for this team."
        )

    def _user_has_full_read_access(self, current_user: User) -> bool:
        """Return whether the current user can read performance for all teams."""

        if current_user.is_super_admin:
            return True

        permissions_service = PermissionsService(self.db)
        return permissions_service.user_has_permission(
            current_user,
            self.PERFORMANCE_MANAGE_PERMISSION,
        )

    def _get_leader_team_ids(self, user_id: int) -> set[int]:
        """Return the team ids led by the provided user."""

        return set(
            self.db.execute(
                select(Team.id).where(Team.leader_user_id == user_id)
            ).scalars().all()
        )

    def _deactivate_other_active_objectives(
        self,
        team_id: int,
        *,
        excluded_objective_id: int | None = None,
    ) -> None:
        """Deactivate any other active objective configured for the same team."""

        statement = select(TeamObjective).where(
            TeamObjective.team_id == team_id,
            TeamObjective.is_active.is_(True),
        )
        if excluded_objective_id is not None:
            statement = statement.where(TeamObjective.id != excluded_objective_id)

        active_objectives = list(self.db.execute(statement).scalars().all())
        for objective in active_objectives:
            objective.is_active = False
            self.db.add(objective)

    def _ensure_unique_daily_performance(
        self,
        team_id: int,
        performance_date: date,
    ) -> None:
        """Reject duplicate daily performance records for the same team and day."""

        existing_record = self.db.execute(
            select(TeamDailyPerformance).where(
                TeamDailyPerformance.team_id == team_id,
                TeamDailyPerformance.performance_date == performance_date,
            )
        ).scalar_one_or_none()
        if existing_record is not None:
            raise PerformanceConflictError(
                "A daily performance record already exists for this team and date."
            )

    def _validate_date_range(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> None:
        """Reject invalid performance date ranges."""

        if date_from is not None and date_to is not None and date_from > date_to:
            raise PerformanceValidationError("date_from cannot be after date_to.")

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        """Commit the current transaction and refresh the target instance."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PerformanceConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
