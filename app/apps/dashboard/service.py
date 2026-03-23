from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.apps.attendance.models import AttendanceDailySummary, AttendanceStatusEnum
from app.apps.dashboard.schemas import (
    DashboardAttendanceDayPointResponse,
    DashboardAttendanceOverviewResponse,
    DashboardAttendanceSummaryResponse,
    DashboardAttendanceTotalsResponse,
    DashboardEmployeesByDepartmentResponse,
    DashboardEmployeesByTeamResponse,
    DashboardEmployeesSummaryResponse,
    DashboardOverviewResponse,
    DashboardPerformanceOverviewResponse,
    DashboardPerformanceSummaryResponse,
    DashboardRequestsStatusCountResponse,
    DashboardRequestsSummaryResponse,
    DashboardRequestsTypeCountResponse,
    DashboardRecentRequestResponse,
    DashboardTeamPerformanceResponse,
)
from app.apps.employees.models import Employee
from app.apps.organization.models import Department, Team
from app.apps.permissions.service import PermissionsService
from app.apps.performance.models import TeamDailyPerformance
from app.apps.requests.models import RequestStatusEnum, RequestType, WorkflowRequest
from app.apps.users.models import User


class DashboardValidationError(RuntimeError):
    """Raised when dashboard filters or parameters are invalid."""


class DashboardAuthorizationError(RuntimeError):
    """Raised when a user is not allowed to access a dashboard scope."""


@dataclass(frozen=True)
class DashboardScope:
    """Resolved user scope used to filter dashboard queries."""

    has_full_access: bool
    own_employee_id: int | None
    own_team_id: int | None
    own_department_id: int | None
    led_team_ids: set[int]
    led_department_ids: set[int]
    requested_team_id: int | None
    requested_department_id: int | None


class DashboardService:
    """Read-only aggregation service for dashboard and reporting endpoints."""

    DASHBOARD_READ_PERMISSION = "dashboard.read"
    DASHBOARD_MANAGE_PERMISSION = "dashboard.manage"

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_overview(
        self,
        current_user: User,
        *,
        target_date: date | None,
        team_id: int | None,
        department_id: int | None,
    ) -> DashboardOverviewResponse:
        """Return the high-level global dashboard overview."""

        resolved_date = target_date or self._today()
        scope = self._build_scope(
            current_user,
            team_id=team_id,
            department_id=department_id,
        )

        employee_counts = self._get_employee_counts(scope)
        total_departments = self._get_visible_department_count(scope)
        total_teams = self._get_visible_team_count(scope)
        request_status_counts = self._get_request_status_counts(
            current_user,
            scope,
            date_from=None,
            date_to=None,
        )

        return DashboardOverviewResponse(
            total_employees=employee_counts["total"],
            active_employees=employee_counts["active"],
            total_departments=total_departments,
            total_teams=total_teams,
            pending_requests_count=request_status_counts[RequestStatusEnum.IN_PROGRESS.value],
            approved_requests_count=request_status_counts[RequestStatusEnum.APPROVED.value],
            rejected_requests_count=request_status_counts[RequestStatusEnum.REJECTED.value],
            attendance_summary=self._build_attendance_overview(scope, resolved_date),
            performance_summary=self._build_performance_overview(scope, resolved_date),
        )

    def get_requests_summary(
        self,
        current_user: User,
        *,
        date_from: date | None,
        date_to: date | None,
        team_id: int | None,
        department_id: int | None,
        recent_limit: int,
    ) -> DashboardRequestsSummaryResponse:
        """Return request counts and recent request items."""

        self._validate_date_range(date_from=date_from, date_to=date_to)
        scope = self._build_scope(
            current_user,
            team_id=team_id,
            department_id=department_id,
        )
        requester_employee = aliased(Employee)
        query_conditions = self._build_employee_query_conditions(scope, requester_employee)
        visibility_condition = self._build_request_visibility_condition(
            scope,
            current_user,
            requester_employee,
        )
        datetime_filters = self._build_submitted_at_conditions(date_from, date_to)

        status_rows = list(
            self.db.execute(
                select(WorkflowRequest.status, func.count(WorkflowRequest.id))
                .select_from(WorkflowRequest)
                .join(
                    requester_employee,
                    requester_employee.id == WorkflowRequest.requester_employee_id,
                )
                .where(visibility_condition, *query_conditions, *datetime_filters)
                .group_by(WorkflowRequest.status)
            ).all()
        )
        status_counts = {
            RequestStatusEnum.IN_PROGRESS.value: 0,
            RequestStatusEnum.APPROVED.value: 0,
            RequestStatusEnum.REJECTED.value: 0,
        }
        for status, count in status_rows:
            status_counts[str(status)] = int(count)

        type_rows = list(
            self.db.execute(
                select(
                    RequestType.id,
                    RequestType.code,
                    RequestType.name,
                    func.count(WorkflowRequest.id),
                )
                .select_from(WorkflowRequest)
                .join(
                    requester_employee,
                    requester_employee.id == WorkflowRequest.requester_employee_id,
                )
                .join(RequestType, RequestType.id == WorkflowRequest.request_type_id)
                .where(visibility_condition, *query_conditions, *datetime_filters)
                .group_by(RequestType.id, RequestType.code, RequestType.name)
                .order_by(func.count(WorkflowRequest.id).desc(), RequestType.name.asc())
            ).all()
        )

        recent_rows = list(
            self.db.execute(
                select(
                    WorkflowRequest.id,
                    WorkflowRequest.status,
                    WorkflowRequest.submitted_at,
                    RequestType.id,
                    RequestType.code,
                    RequestType.name,
                    requester_employee.id,
                    requester_employee.matricule,
                    requester_employee.first_name,
                    requester_employee.last_name,
                )
                .select_from(WorkflowRequest)
                .join(
                    requester_employee,
                    requester_employee.id == WorkflowRequest.requester_employee_id,
                )
                .join(RequestType, RequestType.id == WorkflowRequest.request_type_id)
                .where(visibility_condition, *query_conditions, *datetime_filters)
                .order_by(WorkflowRequest.submitted_at.desc(), WorkflowRequest.id.desc())
                .limit(recent_limit)
            ).all()
        )

        return DashboardRequestsSummaryResponse(
            total_requests=sum(status_counts.values()),
            status_counts=[
                DashboardRequestsStatusCountResponse(
                    status=RequestStatusEnum.IN_PROGRESS.value,
                    count=status_counts[RequestStatusEnum.IN_PROGRESS.value],
                ),
                DashboardRequestsStatusCountResponse(
                    status=RequestStatusEnum.APPROVED.value,
                    count=status_counts[RequestStatusEnum.APPROVED.value],
                ),
                DashboardRequestsStatusCountResponse(
                    status=RequestStatusEnum.REJECTED.value,
                    count=status_counts[RequestStatusEnum.REJECTED.value],
                ),
            ],
            requests_by_type=[
                DashboardRequestsTypeCountResponse(
                    request_type_id=row[0],
                    request_type_code=row[1],
                    request_type_name=row[2],
                    count=int(row[3]),
                )
                for row in type_rows
            ],
            recent_requests=[
                DashboardRecentRequestResponse(
                    request_id=row[0],
                    status=row[1],
                    submitted_at=row[2],
                    request_type_id=row[3],
                    request_type_code=row[4],
                    request_type_name=row[5],
                    requester_employee_id=row[6],
                    requester_matricule=row[7],
                    requester_name=f"{row[8]} {row[9]}",
                )
                for row in recent_rows
            ],
        )

    def get_attendance_summary(
        self,
        current_user: User,
        *,
        target_date: date | None,
        date_from: date | None,
        date_to: date | None,
        team_id: int | None,
        department_id: int | None,
    ) -> DashboardAttendanceSummaryResponse:
        """Return attendance dashboard aggregates."""

        resolved_target_date = target_date or self._today()
        resolved_date_to = date_to or resolved_target_date
        resolved_date_from = date_from or (resolved_date_to - timedelta(days=6))
        self._validate_date_range(date_from=resolved_date_from, date_to=resolved_date_to)

        scope = self._build_scope(
            current_user,
            team_id=team_id,
            department_id=department_id,
        )
        daily_points = self._build_attendance_daily_points(
            scope,
            date_from=resolved_date_from,
            date_to=resolved_date_to,
        )

        return DashboardAttendanceSummaryResponse(
            today=self._build_attendance_overview(scope, resolved_target_date),
            daily_stats=daily_points,
            totals=DashboardAttendanceTotalsResponse(
                total_present=sum(point.present_count for point in daily_points),
                total_incomplete=sum(point.incomplete_count for point in daily_points),
                total_leave=sum(point.leave_count for point in daily_points),
                total_absent=sum(point.absent_count for point in daily_points),
            ),
        )

    def get_performance_summary(
        self,
        current_user: User,
        *,
        target_date: date | None,
        team_id: int | None,
        department_id: int | None,
    ) -> DashboardPerformanceSummaryResponse:
        """Return team performance dashboard data for one date."""

        resolved_date = target_date or self._today()
        scope = self._build_scope(
            current_user,
            team_id=team_id,
            department_id=department_id,
        )
        self._authorize_performance_scope(scope)

        team_conditions = self._build_team_query_conditions(scope, Team)
        visibility_condition = self._build_performance_team_visibility_condition(scope, Team)
        rows = list(
            self.db.execute(
                select(
                    TeamDailyPerformance.team_id,
                    Team.code,
                    Team.name,
                    TeamDailyPerformance.performance_date,
                    TeamDailyPerformance.objective_value,
                    TeamDailyPerformance.achieved_value,
                    TeamDailyPerformance.performance_percentage,
                )
                .select_from(TeamDailyPerformance)
                .join(Team, Team.id == TeamDailyPerformance.team_id)
                .where(
                    TeamDailyPerformance.performance_date == resolved_date,
                    visibility_condition,
                    *team_conditions,
                )
                .order_by(
                    TeamDailyPerformance.performance_percentage.desc(),
                    Team.name.asc(),
                )
            ).all()
        )

        team_items = [
            DashboardTeamPerformanceResponse(
                team_id=row[0],
                team_code=row[1],
                team_name=row[2],
                performance_date=row[3],
                objective_value=float(row[4]),
                achieved_value=float(row[5]),
                performance_percentage=float(row[6]),
            )
            for row in rows
        ]
        average_performance = round(
            sum(item.performance_percentage for item in team_items) / len(team_items),
            2,
        ) if team_items else 0.0

        return DashboardPerformanceSummaryResponse(
            performance_date=resolved_date,
            teams_reporting_count=len(team_items),
            average_performance_percentage=average_performance,
            team_performances=team_items,
            best_performing_teams=team_items[:5],
            lowest_performing_teams=sorted(
                team_items,
                key=lambda item: (item.performance_percentage, item.team_name),
            )[:5],
        )

    def get_employees_summary(
        self,
        current_user: User,
        *,
        team_id: int | None,
        department_id: int | None,
    ) -> DashboardEmployeesSummaryResponse:
        """Return employees counts grouped by department and team."""

        scope = self._build_scope(
            current_user,
            team_id=team_id,
            department_id=department_id,
        )
        employee_counts = self._get_employee_counts(scope)
        employee_conditions = self._build_employee_scope_conditions(scope, Employee)

        department_rows = list(
            self.db.execute(
                select(
                    Department.id,
                    Department.code,
                    Department.name,
                    func.count(Employee.id),
                )
                .select_from(Employee)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(*employee_conditions)
                .group_by(Department.id, Department.code, Department.name)
                .order_by(func.count(Employee.id).desc(), Department.name.asc())
            ).all()
        )

        team_rows = list(
            self.db.execute(
                select(
                    Team.id,
                    Team.code,
                    Team.name,
                    Department.id,
                    Department.name,
                    func.count(Employee.id),
                )
                .select_from(Employee)
                .outerjoin(Team, Team.id == Employee.team_id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(*employee_conditions)
                .group_by(Team.id, Team.code, Team.name, Department.id, Department.name)
                .order_by(func.count(Employee.id).desc(), Team.name.asc())
            ).all()
        )

        return DashboardEmployeesSummaryResponse(
            total_employees=employee_counts["total"],
            active_employees=employee_counts["active"],
            inactive_employees=employee_counts["inactive"],
            employees_by_department=[
                DashboardEmployeesByDepartmentResponse(
                    department_id=row[0],
                    department_code=row[1],
                    department_name=row[2],
                    employee_count=int(row[3]),
                )
                for row in department_rows
            ],
            employees_by_team=[
                DashboardEmployeesByTeamResponse(
                    team_id=row[0],
                    team_code=row[1],
                    team_name=row[2],
                    department_id=row[3],
                    department_name=row[4],
                    employee_count=int(row[5]),
                )
                for row in team_rows
            ],
        )

    def _build_scope(
        self,
        current_user: User,
        *,
        team_id: int | None,
        department_id: int | None,
    ) -> DashboardScope:
        """Resolve the current user's dashboard read scope."""

        requested_team = self._get_team(team_id) if team_id is not None else None
        requested_department = (
            self._get_department(department_id) if department_id is not None else None
        )
        if (
            requested_team is not None
            and requested_department is not None
            and requested_team.department_id != requested_department.id
        ):
            raise DashboardValidationError(
                "The selected team does not belong to the selected department."
            )

        own_employee = self._get_employee_by_user_id(current_user.id)
        led_teams = self._get_teams_led_by_user_id(current_user.id)
        led_team_ids = {team.id for team in led_teams}
        led_department_ids = {team.department_id for team in led_teams}
        has_full_access = self._user_has_full_access(current_user)

        if not has_full_access and team_id is not None:
            allowed_team_ids = set(led_team_ids)
            if own_employee is not None and own_employee.team_id is not None:
                allowed_team_ids.add(own_employee.team_id)

            if team_id not in allowed_team_ids:
                raise DashboardAuthorizationError(
                    "You are not allowed to access dashboard data for this team."
                )

        if not has_full_access and department_id is not None:
            allowed_department_ids = set(led_department_ids)
            if own_employee is not None and own_employee.department_id is not None:
                allowed_department_ids.add(own_employee.department_id)

            if department_id not in allowed_department_ids:
                raise DashboardAuthorizationError(
                    "You are not allowed to access dashboard data for this department."
                )

        return DashboardScope(
            has_full_access=has_full_access,
            own_employee_id=own_employee.id if own_employee is not None else None,
            own_team_id=own_employee.team_id if own_employee is not None else None,
            own_department_id=(
                own_employee.department_id if own_employee is not None else None
            ),
            led_team_ids=led_team_ids,
            led_department_ids=led_department_ids,
            requested_team_id=team_id,
            requested_department_id=department_id,
        )

    def _build_attendance_overview(
        self,
        scope: DashboardScope,
        target_date: date,
    ) -> DashboardAttendanceOverviewResponse:
        """Build one attendance overview for a target date."""

        total_active_employees = self._count_visible_active_employees(scope)
        status_counts = self._get_attendance_status_counts_for_range(
            scope,
            date_from=target_date,
            date_to=target_date,
        ).get(target_date, {})

        present_count = status_counts.get(AttendanceStatusEnum.PRESENT.value, 0)
        incomplete_count = status_counts.get(AttendanceStatusEnum.INCOMPLETE.value, 0)
        leave_count = status_counts.get(AttendanceStatusEnum.LEAVE.value, 0)
        absent_count = max(
            total_active_employees - present_count - incomplete_count - leave_count,
            0,
        )
        return DashboardAttendanceOverviewResponse(
            attendance_date=target_date,
            total_active_employees=total_active_employees,
            present_count=present_count,
            incomplete_count=incomplete_count,
            leave_count=leave_count,
            absent_count=absent_count,
        )

    def _build_attendance_daily_points(
        self,
        scope: DashboardScope,
        *,
        date_from: date,
        date_to: date,
    ) -> list[DashboardAttendanceDayPointResponse]:
        """Build daily attendance points for a date range."""

        total_active_employees = self._count_visible_active_employees(scope)
        raw_counts = self._get_attendance_status_counts_for_range(
            scope,
            date_from=date_from,
            date_to=date_to,
        )

        points: list[DashboardAttendanceDayPointResponse] = []
        current_date = date_from
        while current_date <= date_to:
            counts = raw_counts.get(current_date, {})
            present_count = counts.get(AttendanceStatusEnum.PRESENT.value, 0)
            incomplete_count = counts.get(AttendanceStatusEnum.INCOMPLETE.value, 0)
            leave_count = counts.get(AttendanceStatusEnum.LEAVE.value, 0)
            absent_count = max(
                total_active_employees - present_count - incomplete_count - leave_count,
                0,
            )
            points.append(
                DashboardAttendanceDayPointResponse(
                    attendance_date=current_date,
                    present_count=present_count,
                    incomplete_count=incomplete_count,
                    leave_count=leave_count,
                    absent_count=absent_count,
                )
            )
            current_date += timedelta(days=1)

        return points

    def _build_performance_overview(
        self,
        scope: DashboardScope,
        target_date: date,
    ) -> DashboardPerformanceOverviewResponse:
        """Build one compact performance overview for a target date."""

        if not scope.has_full_access and not scope.led_team_ids:
            return DashboardPerformanceOverviewResponse(
                performance_date=target_date,
                teams_reporting_count=0,
                average_performance_percentage=0.0,
            )

        team_conditions = self._build_team_query_conditions(scope, Team)
        visibility_condition = self._build_performance_team_visibility_condition(
            scope,
            Team,
        )
        row = self.db.execute(
            select(
                func.count(TeamDailyPerformance.id),
                func.coalesce(
                    func.avg(TeamDailyPerformance.performance_percentage),
                    0.0,
                ),
            )
            .select_from(TeamDailyPerformance)
            .join(Team, Team.id == TeamDailyPerformance.team_id)
            .where(
                TeamDailyPerformance.performance_date == target_date,
                visibility_condition,
                *team_conditions,
            )
        ).one()
        return DashboardPerformanceOverviewResponse(
            performance_date=target_date,
            teams_reporting_count=int(row[0] or 0),
            average_performance_percentage=round(float(row[1] or 0.0), 2),
        )

    def _get_employee_counts(self, scope: DashboardScope) -> dict[str, int]:
        """Return employee totals for the visible scope."""

        row = self.db.execute(
            select(
                func.count(Employee.id),
                func.coalesce(
                    func.sum(case((Employee.is_active.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Employee.is_active.is_(False), 1), else_=0)),
                    0,
                ),
            )
            .select_from(Employee)
            .where(*self._build_employee_scope_conditions(scope, Employee))
        ).one()
        return {
            "total": int(row[0] or 0),
            "active": int(row[1] or 0),
            "inactive": int(row[2] or 0),
        }

    def _count_visible_active_employees(self, scope: DashboardScope) -> int:
        """Count active employees visible in the dashboard scope."""

        return int(
            self.db.execute(
                select(func.count(Employee.id))
                .select_from(Employee)
                .where(
                    *self._build_employee_scope_conditions(
                        scope,
                        Employee,
                        active_only=True,
                    )
                )
            ).scalar_one()
            or 0
        )

    def _get_visible_department_count(self, scope: DashboardScope) -> int:
        """Count departments visible in the dashboard scope."""

        if scope.has_full_access:
            conditions: list[Any] = []
            if scope.requested_department_id is not None:
                conditions.append(Department.id == scope.requested_department_id)
            elif scope.requested_team_id is not None:
                team = self._get_team(scope.requested_team_id)
                conditions.append(Department.id == team.department_id)

            return int(
                self.db.execute(
                    select(func.count(Department.id)).where(*conditions)
                ).scalar_one()
                or 0
            )

        visible_department_ids = set(scope.led_department_ids)
        if scope.own_department_id is not None:
            visible_department_ids.add(scope.own_department_id)

        if scope.requested_department_id is not None:
            visible_department_ids = {
                department_id
                for department_id in visible_department_ids
                if department_id == scope.requested_department_id
            }
        elif scope.requested_team_id is not None:
            team = self._get_team(scope.requested_team_id)
            visible_department_ids = {
                department_id
                for department_id in visible_department_ids
                if department_id == team.department_id
            }

        return len(visible_department_ids)

    def _get_visible_team_count(self, scope: DashboardScope) -> int:
        """Count teams visible in the dashboard scope."""

        if scope.has_full_access:
            return int(
                self.db.execute(
                    select(func.count(Team.id)).where(
                        *self._build_team_query_conditions(scope, Team)
                    )
                ).scalar_one()
                or 0
            )

        visible_team_ids = set(scope.led_team_ids)
        if scope.own_team_id is not None:
            visible_team_ids.add(scope.own_team_id)

        if scope.requested_team_id is not None:
            visible_team_ids = {
                team_id
                for team_id in visible_team_ids
                if team_id == scope.requested_team_id
            }
        if scope.requested_department_id is not None:
            visible_team_ids = {
                team_id
                for team_id in visible_team_ids
                if self._get_team(team_id).department_id == scope.requested_department_id
            }

        return len(visible_team_ids)

    def _get_request_status_counts(
        self,
        current_user: User,
        scope: DashboardScope,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, int]:
        """Return request counts grouped by status for the visible scope."""

        requester_employee = aliased(Employee)
        status_rows = list(
            self.db.execute(
                select(WorkflowRequest.status, func.count(WorkflowRequest.id))
                .select_from(WorkflowRequest)
                .join(
                    requester_employee,
                    requester_employee.id == WorkflowRequest.requester_employee_id,
                )
                .where(
                    self._build_request_visibility_condition(
                        scope,
                        current_user,
                        requester_employee,
                    ),
                    *self._build_employee_query_conditions(scope, requester_employee),
                    *self._build_submitted_at_conditions(date_from, date_to),
                )
                .group_by(WorkflowRequest.status)
            ).all()
        )
        counts = {
            RequestStatusEnum.IN_PROGRESS.value: 0,
            RequestStatusEnum.APPROVED.value: 0,
            RequestStatusEnum.REJECTED.value: 0,
        }
        for status, count in status_rows:
            counts[str(status)] = int(count)

        return counts

    def _get_attendance_status_counts_for_range(
        self,
        scope: DashboardScope,
        *,
        date_from: date,
        date_to: date,
    ) -> dict[date, dict[str, int]]:
        """Return attendance status counts grouped by day and status."""

        rows = list(
            self.db.execute(
                select(
                    AttendanceDailySummary.attendance_date,
                    AttendanceDailySummary.status,
                    func.count(AttendanceDailySummary.id),
                )
                .select_from(AttendanceDailySummary)
                .join(Employee, Employee.id == AttendanceDailySummary.employee_id)
                .where(
                    AttendanceDailySummary.attendance_date >= date_from,
                    AttendanceDailySummary.attendance_date <= date_to,
                    *self._build_employee_scope_conditions(
                        scope,
                        Employee,
                        active_only=True,
                    ),
                )
                .group_by(
                    AttendanceDailySummary.attendance_date,
                    AttendanceDailySummary.status,
                )
                .order_by(AttendanceDailySummary.attendance_date.asc())
            ).all()
        )

        counts_by_date: dict[date, dict[str, int]] = {}
        for attendance_date, status, count in rows:
            counts_by_date.setdefault(attendance_date, {})[str(status)] = int(count)

        return counts_by_date

    def _build_employee_scope_conditions(
        self,
        scope: DashboardScope,
        employee_entity,
        *,
        active_only: bool | None = None,
    ) -> list[Any]:
        """Build combined employee visibility and filter conditions."""

        conditions: list[Any] = []
        if not scope.has_full_access:
            conditions.append(
                self._build_employee_visibility_condition(scope, employee_entity)
            )

        conditions.extend(self._build_employee_query_conditions(scope, employee_entity))
        if active_only is True:
            conditions.append(employee_entity.is_active.is_(True))
        elif active_only is False:
            conditions.append(employee_entity.is_active.is_(False))

        return conditions

    def _build_employee_visibility_condition(self, scope: DashboardScope, employee_entity):
        """Build the employee visibility condition for limited-scope users."""

        if scope.has_full_access:
            return _sql_true()

        visibility_conditions: list[Any] = []
        if scope.led_team_ids:
            visibility_conditions.append(employee_entity.team_id.in_(scope.led_team_ids))
        if scope.own_employee_id is not None:
            visibility_conditions.append(employee_entity.id == scope.own_employee_id)

        if not visibility_conditions:
            return false()

        return or_(*visibility_conditions)

    def _build_employee_query_conditions(self, scope: DashboardScope, employee_entity) -> list[Any]:
        """Build employee query-filter conditions from request parameters."""

        conditions: list[Any] = []
        if scope.requested_team_id is not None:
            conditions.append(employee_entity.team_id == scope.requested_team_id)
        if scope.requested_department_id is not None:
            conditions.append(employee_entity.department_id == scope.requested_department_id)

        return conditions

    def _build_team_query_conditions(self, scope: DashboardScope, team_entity) -> list[Any]:
        """Build team query-filter conditions from request parameters."""

        conditions: list[Any] = []
        if scope.requested_team_id is not None:
            conditions.append(team_entity.id == scope.requested_team_id)
        if scope.requested_department_id is not None:
            conditions.append(team_entity.department_id == scope.requested_department_id)

        return conditions

    def _build_request_visibility_condition(
        self,
        scope: DashboardScope,
        current_user: User,
        requester_employee,
    ):
        """Build request visibility condition for dashboard request queries."""

        if scope.has_full_access:
            return _sql_true()

        access_conditions: list[Any] = [
            WorkflowRequest.requester_user_id == current_user.id,
            WorkflowRequest.current_approver_user_id == current_user.id,
            self._build_employee_visibility_condition(scope, requester_employee),
        ]
        return or_(*access_conditions)

    def _build_performance_team_visibility_condition(self, scope: DashboardScope, team_entity):
        """Build performance team visibility condition for limited-scope users."""

        if scope.has_full_access:
            return _sql_true()

        if not scope.led_team_ids:
            return false()

        return team_entity.id.in_(scope.led_team_ids)

    def _authorize_performance_scope(self, scope: DashboardScope) -> None:
        """Reject performance access outside the allowed leader/admin scope."""

        if scope.has_full_access:
            return

        if (
            scope.requested_team_id is not None
            and scope.requested_team_id not in scope.led_team_ids
        ):
            raise DashboardAuthorizationError(
                "You are not allowed to access performance data for this team."
            )

    def _build_submitted_at_conditions(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> list[Any]:
        """Build request datetime range conditions from date filters."""

        conditions: list[Any] = []
        if date_from is not None:
            start_at = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            conditions.append(WorkflowRequest.submitted_at >= start_at)

        if date_to is not None:
            end_at = datetime.combine(
                date_to + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
            conditions.append(WorkflowRequest.submitted_at < end_at)

        return conditions

    def _validate_date_range(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> None:
        """Reject invalid dashboard date ranges."""

        if date_from is not None and date_to is not None and date_from > date_to:
            raise DashboardValidationError("date_from cannot be after date_to.")

    def _user_has_full_access(self, current_user: User) -> bool:
        """Return whether the current user can read dashboard data globally."""

        if current_user.is_super_admin:
            return True

        permissions_service = PermissionsService(self.db)
        return (
            permissions_service.user_has_permission(
                current_user,
                self.DASHBOARD_READ_PERMISSION,
            )
            or permissions_service.user_has_permission(
                current_user,
                self.DASHBOARD_MANAGE_PERMISSION,
            )
        )

    def _get_employee_by_user_id(self, user_id: int) -> Employee | None:
        """Return the employee linked to a user, if one exists."""

        return self.db.execute(
            select(Employee).where(Employee.user_id == user_id).limit(1)
        ).scalar_one_or_none()

    def _get_teams_led_by_user_id(self, user_id: int) -> list[Team]:
        """Return teams currently led by the provided user."""

        return list(
            self.db.execute(select(Team).where(Team.leader_user_id == user_id))
            .scalars()
            .all()
        )

    def _get_team(self, team_id: int) -> Team:
        """Return a team by id."""

        team = self.db.get(Team, team_id)
        if team is None:
            raise DashboardValidationError("Team not found.")

        return team

    def _get_department(self, department_id: int) -> Department:
        """Return a department by id."""

        department = self.db.get(Department, department_id)
        if department is None:
            raise DashboardValidationError("Department not found.")

        return department

    def _today(self) -> date:
        """Return the current local business date."""

        return date.today()


def _sql_true():
    """Return a SQLAlchemy-compatible true literal."""

    return and_(True)
