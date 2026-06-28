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
    attendance_rate: float


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


class DashboardRequestTrendPointResponse(BaseModel):
    """Daily request count for sparkline/trend data."""

    trend_date: date
    request_count: int


class DashboardRequestsSummaryResponse(BaseModel):
    """Requests dashboard summary response."""

    total_requests: int
    status_counts: list[DashboardRequestsStatusCountResponse]
    requests_by_type: list[DashboardRequestsTypeCountResponse]
    recent_requests: list[DashboardRecentRequestResponse]
    request_trend: list[DashboardRequestTrendPointResponse]


class DashboardAttendanceDayPointResponse(BaseModel):
    """Daily attendance point used for chart-ready responses."""

    attendance_date: date
    present_count: int
    incomplete_count: int
    leave_count: int
    absent_count: int
    attendance_rate: float


class DashboardAttendanceTotalsResponse(BaseModel):
    """Attendance totals for a date range."""

    total_present: int
    total_incomplete: int
    total_leave: int
    total_absent: int
    attendance_rate: float


class DashboardAttendanceSummaryResponse(BaseModel):
    """Attendance dashboard summary response."""

    today: DashboardAttendanceOverviewResponse
    daily_stats: list[DashboardAttendanceDayPointResponse]
    totals: DashboardAttendanceTotalsResponse


class DashboardRecentAttendanceResponse(BaseModel):
    """Recent attendance item included in the clean attendance dashboard response."""

    attendance_id: int
    employee_id: int
    employee_matricule: str
    employee_name: str
    attendance_date: date
    status: str
    first_check_in_at: datetime | None
    last_check_out_at: datetime | None
    worked_duration_minutes: int | None


class AttendanceDashboardResponse(DashboardAttendanceSummaryResponse):
    """Clean attendance dashboard response with recent activity."""

    recent_activity: list[DashboardRecentAttendanceResponse]


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


class DashboardEmployeesByGenderResponse(BaseModel):
    """Employee count grouped by gender."""

    gender: str
    employee_count: int


class DashboardEmployeesByContractTypeResponse(BaseModel):
    """Employee count grouped by contract type."""

    contract_type: str
    employee_count: int


class DashboardEmployeesByJobTitleResponse(BaseModel):
    """Employee count grouped by job title."""

    job_title_id: int
    job_title_code: str
    job_title_name: str
    employee_count: int


class DashboardEmployeesSummaryResponse(BaseModel):
    """Employees dashboard summary response."""

    total_employees: int
    active_employees: int
    inactive_employees: int
    employees_by_department: list[DashboardEmployeesByDepartmentResponse]
    employees_by_team: list[DashboardEmployeesByTeamResponse]
    employees_by_gender: list[DashboardEmployeesByGenderResponse]
    employees_by_contract_type: list[DashboardEmployeesByContractTypeResponse]
    employees_by_job_title: list[DashboardEmployeesByJobTitleResponse]


class EmployeeStatsResponse(DashboardEmployeesSummaryResponse):
    """Clean employee dashboard stats response."""


class CompanyStatsResponse(BaseModel):
    """Company-wide dashboard statistics response."""

    total_employees: int
    active_employees: int
    inactive_employees: int
    total_departments: int
    active_departments: int
    total_teams: int
    active_teams: int
    total_job_titles: int
    active_job_titles: int
    pending_requests_count: int
    present_today: int
    absent_today: int
    incomplete_count: int
    on_leave_today: int
    attendance_rate_today: float
