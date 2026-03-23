from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.shared.responses import ModuleStatusResponse


class DashboardStatusResponse(ModuleStatusResponse):
    """Response schema for the dashboard module status endpoint."""

    module: Literal["dashboard"] = "dashboard"


class DashboardAttendanceOverviewResponse(BaseModel):
    """Compact attendance summary used by dashboard endpoints."""

    attendance_date: date
    total_active_employees: int
    present_count: int
    incomplete_count: int
    leave_count: int
    absent_count: int


class DashboardPerformanceOverviewResponse(BaseModel):
    """Compact performance summary used by dashboard endpoints."""

    performance_date: date
    teams_reporting_count: int
    average_performance_percentage: float


class DashboardOverviewResponse(BaseModel):
    """Global dashboard overview response."""

    total_employees: int
    active_employees: int
    total_departments: int
    total_teams: int
    pending_requests_count: int
    approved_requests_count: int
    rejected_requests_count: int
    attendance_summary: DashboardAttendanceOverviewResponse
    performance_summary: DashboardPerformanceOverviewResponse


class DashboardRequestsStatusCountResponse(BaseModel):
    """Request count grouped by status."""

    status: str
    count: int


class DashboardRequestsTypeCountResponse(BaseModel):
    """Request count grouped by request type."""

    request_type_id: int
    request_type_code: str
    request_type_name: str
    count: int


class DashboardRecentRequestResponse(BaseModel):
    """Recent request item included in dashboard summaries."""

    request_id: int
    request_type_id: int
    request_type_code: str
    request_type_name: str
    requester_employee_id: int
    requester_matricule: str
    requester_name: str
    status: str
    submitted_at: datetime


class DashboardRequestsSummaryResponse(BaseModel):
    """Requests dashboard summary response."""

    total_requests: int
    status_counts: list[DashboardRequestsStatusCountResponse]
    requests_by_type: list[DashboardRequestsTypeCountResponse]
    recent_requests: list[DashboardRecentRequestResponse]


class DashboardAttendanceDayPointResponse(BaseModel):
    """Daily attendance point used for chart-ready responses."""

    attendance_date: date
    present_count: int
    incomplete_count: int
    leave_count: int
    absent_count: int


class DashboardAttendanceTotalsResponse(BaseModel):
    """Attendance totals for a date range."""

    total_present: int
    total_incomplete: int
    total_leave: int
    total_absent: int


class DashboardAttendanceSummaryResponse(BaseModel):
    """Attendance dashboard summary response."""

    today: DashboardAttendanceOverviewResponse
    daily_stats: list[DashboardAttendanceDayPointResponse]
    totals: DashboardAttendanceTotalsResponse


class DashboardTeamPerformanceResponse(BaseModel):
    """Team performance item returned by the performance dashboard."""

    team_id: int
    team_code: str
    team_name: str
    performance_date: date
    objective_value: float
    achieved_value: float
    performance_percentage: float


class DashboardPerformanceSummaryResponse(BaseModel):
    """Performance dashboard summary response."""

    performance_date: date
    teams_reporting_count: int
    average_performance_percentage: float
    team_performances: list[DashboardTeamPerformanceResponse]
    best_performing_teams: list[DashboardTeamPerformanceResponse]
    lowest_performing_teams: list[DashboardTeamPerformanceResponse]


class DashboardEmployeesByDepartmentResponse(BaseModel):
    """Employee count grouped by department."""

    department_id: int | None
    department_code: str | None
    department_name: str | None
    employee_count: int


class DashboardEmployeesByTeamResponse(BaseModel):
    """Employee count grouped by team."""

    team_id: int | None
    team_code: str | None
    team_name: str | None
    department_id: int | None
    department_name: str | None
    employee_count: int


class DashboardEmployeesSummaryResponse(BaseModel):
    """Employees dashboard summary response."""

    total_employees: int
    active_employees: int
    inactive_employees: int
    employees_by_department: list[DashboardEmployeesByDepartmentResponse]
    employees_by_team: list[DashboardEmployeesByTeamResponse]
