from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.attendance.models import (
    AttendanceDailySummary,
    AttendanceMonthlyReport,
    AttendanceRawScanEvent,
    AttendanceReaderTypeEnum,
    AttendanceStatusEnum,
)
from app.apps.attendance.schemas import (
    AttendanceDailySummaryResponse,
    AttendanceMonthlyReportGenerateRequest,
    AttendanceMonthlyReportResponse,
    AttendanceRawScanEventResponse,
    AttendanceScanIngestRequest,
    AttendanceScanIngestResponse,
)
from app.apps.employees.models import Employee


class AttendanceConflictError(RuntimeError):
    """Raised when a unique or state conflict prevents the operation."""


class AttendanceNotFoundError(RuntimeError):
    """Raised when an attendance-related record cannot be found."""


class AttendanceValidationError(RuntimeError):
    """Raised when an attendance payload or operation is invalid."""


class AttendanceService:
    """Service layer for attendance ingestion, summaries, and reports."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ingest_scan_event(
        self,
        payload: AttendanceScanIngestRequest,
    ) -> tuple[AttendanceRawScanEvent, AttendanceDailySummary]:
        """Persist a raw scan event and update the employee daily summary."""

        employee = self._get_active_employee_by_matricule(payload.matricule)
        attendance_date = payload.scanned_at.date()
        stored_scanned_at = payload.scanned_at.astimezone(timezone.utc)
        daily_summary = self._get_or_create_daily_summary(employee.id, attendance_date)

        raw_event = AttendanceRawScanEvent(
            employee_id=employee.id,
            user_id=employee.user_id,
            reader_type=payload.reader_type.value,
            scanned_at=stored_scanned_at,
            source=payload.source,
        )
        self.db.add(raw_event)

        self._apply_scan_to_daily_summary(
            daily_summary=daily_summary,
            reader_type=payload.reader_type,
            scanned_at=stored_scanned_at,
        )
        self.db.add(daily_summary)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AttendanceConflictError(
                "Failed to ingest the attendance scan event."
            ) from exc

        self.db.refresh(raw_event)
        self.db.refresh(daily_summary)
        return raw_event, daily_summary

    def list_daily_summaries(
        self,
        *,
        employee_id: int | None = None,
        matricule: str | None = None,
        status: AttendanceStatusEnum | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        include_inactive: bool = False,
    ) -> list[AttendanceDailySummary]:
        """List daily attendance summaries with optional filters."""

        self._validate_date_range(date_from=date_from, date_to=date_to)
        normalized_matricule = (
            matricule.strip().upper()
            if matricule is not None and matricule.strip()
            else None
        )
        statement: Select[tuple[AttendanceDailySummary]] = (
            select(AttendanceDailySummary)
            .join(Employee, Employee.id == AttendanceDailySummary.employee_id)
        )
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))

        if employee_id is not None:
            statement = statement.where(AttendanceDailySummary.employee_id == employee_id)

        if normalized_matricule is not None:
            statement = statement.where(Employee.matricule == normalized_matricule)

        if status is not None:
            statement = statement.where(AttendanceDailySummary.status == status.value)

        if date_from is not None:
            statement = statement.where(AttendanceDailySummary.attendance_date >= date_from)

        if date_to is not None:
            statement = statement.where(AttendanceDailySummary.attendance_date <= date_to)

        statement = statement.order_by(
            AttendanceDailySummary.attendance_date.desc(),
            AttendanceDailySummary.employee_id.asc(),
            AttendanceDailySummary.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_employee_daily_summaries(
        self,
        employee_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[AttendanceDailySummary]:
        """Return daily attendance summaries for a single employee."""

        self._get_employee(employee_id)
        return self.list_daily_summaries(
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
            include_inactive=True,
        )

    def generate_monthly_reports(
        self,
        payload: AttendanceMonthlyReportGenerateRequest,
    ) -> list[AttendanceMonthlyReport]:
        """Generate or refresh monthly attendance reports from daily summaries."""

        employees = self._resolve_report_target_employees(
            employee_id=payload.employee_id,
            include_inactive=payload.include_inactive,
        )
        if not employees:
            return []

        period_start, period_end = self._get_month_date_range(
            payload.report_year,
            payload.report_month,
        )
        employee_ids = [employee.id for employee in employees]

        summaries = list(
            self.db.execute(
                select(AttendanceDailySummary).where(
                    AttendanceDailySummary.employee_id.in_(employee_ids),
                    AttendanceDailySummary.attendance_date >= period_start,
                    AttendanceDailySummary.attendance_date <= period_end,
                )
            )
            .scalars()
            .all()
        )
        summaries_by_employee_id: dict[int, list[AttendanceDailySummary]] = {}
        for summary in summaries:
            summaries_by_employee_id.setdefault(summary.employee_id, []).append(summary)

        existing_reports = list(
            self.db.execute(
                select(AttendanceMonthlyReport).where(
                    AttendanceMonthlyReport.employee_id.in_(employee_ids),
                    AttendanceMonthlyReport.report_year == payload.report_year,
                    AttendanceMonthlyReport.report_month == payload.report_month,
                )
            )
            .scalars()
            .all()
        )
        existing_reports_by_employee_id = {
            report.employee_id: report for report in existing_reports
        }

        generated_reports: list[AttendanceMonthlyReport] = []
        for employee in employees:
            employee_summaries = summaries_by_employee_id.get(employee.id, [])
            report = existing_reports_by_employee_id.get(employee.id)
            if report is None:
                report = AttendanceMonthlyReport(
                    employee_id=employee.id,
                    report_year=payload.report_year,
                    report_month=payload.report_month,
                )

            aggregates = self._aggregate_monthly_totals(employee_summaries)
            report.total_worked_days = aggregates["total_worked_days"]
            report.total_worked_minutes = aggregates["total_worked_minutes"]
            report.total_present_days = aggregates["total_present_days"]
            report.total_absence_days = aggregates["total_absence_days"]
            report.total_leave_days = aggregates["total_leave_days"]
            self.db.add(report)
            generated_reports.append(report)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AttendanceConflictError(
                "Failed to generate the monthly attendance reports."
            ) from exc

        for report in generated_reports:
            self.db.refresh(report)

        generated_reports.sort(
            key=lambda report: (report.report_year, report.report_month, report.employee_id)
        )
        return generated_reports

    def list_monthly_reports(
        self,
        *,
        employee_id: int | None = None,
        year: int | None = None,
        month: int | None = None,
        include_inactive: bool = False,
    ) -> list[AttendanceMonthlyReport]:
        """List generated monthly attendance reports."""

        statement: Select[tuple[AttendanceMonthlyReport]] = (
            select(AttendanceMonthlyReport)
            .join(Employee, Employee.id == AttendanceMonthlyReport.employee_id)
        )
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))

        if employee_id is not None:
            statement = statement.where(AttendanceMonthlyReport.employee_id == employee_id)

        if year is not None:
            statement = statement.where(AttendanceMonthlyReport.report_year == year)

        if month is not None:
            statement = statement.where(AttendanceMonthlyReport.report_month == month)

        statement = statement.order_by(
            AttendanceMonthlyReport.report_year.desc(),
            AttendanceMonthlyReport.report_month.desc(),
            AttendanceMonthlyReport.employee_id.asc(),
            AttendanceMonthlyReport.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def get_monthly_report(
        self,
        employee_id: int,
        report_year: int,
        report_month: int,
    ) -> AttendanceMonthlyReport:
        """Return one generated monthly report for an employee and period."""

        self._get_employee(employee_id)
        report = self.db.execute(
            select(AttendanceMonthlyReport).where(
                AttendanceMonthlyReport.employee_id == employee_id,
                AttendanceMonthlyReport.report_year == report_year,
                AttendanceMonthlyReport.report_month == report_month,
            )
        ).scalar_one_or_none()
        if report is None:
            raise AttendanceNotFoundError("Monthly attendance report not found.")

        return report

    def build_scan_ingest_response(
        self,
        raw_event: AttendanceRawScanEvent,
        daily_summary: AttendanceDailySummary,
    ) -> AttendanceScanIngestResponse:
        """Build the API response for a scan ingestion result."""

        employee = self._get_employee(daily_summary.employee_id)
        return AttendanceScanIngestResponse(
            raw_event=self._build_raw_scan_event_response(raw_event, employee),
            daily_summary=self._build_daily_summary_response(daily_summary, employee),
        )

    def build_daily_summary_responses(
        self,
        summaries: list[AttendanceDailySummary],
    ) -> list[AttendanceDailySummaryResponse]:
        """Build daily summary response payloads with employee context."""

        employees_by_id = self._get_employees_by_ids(
            {summary.employee_id for summary in summaries}
        )
        return [
            self._build_daily_summary_response(summary, employees_by_id[summary.employee_id])
            for summary in summaries
        ]

    def build_monthly_report_responses(
        self,
        reports: list[AttendanceMonthlyReport],
    ) -> list[AttendanceMonthlyReportResponse]:
        """Build monthly report response payloads with employee context."""

        employees_by_id = self._get_employees_by_ids(
            {report.employee_id for report in reports}
        )
        return [
            self._build_monthly_report_response(report, employees_by_id[report.employee_id])
            for report in reports
        ]

    def build_monthly_report_response(
        self,
        report: AttendanceMonthlyReport,
    ) -> AttendanceMonthlyReportResponse:
        """Build one monthly report response payload."""

        employee = self._get_employee(report.employee_id)
        return self._build_monthly_report_response(report, employee)

    def _build_raw_scan_event_response(
        self,
        raw_event: AttendanceRawScanEvent,
        employee: Employee,
    ) -> AttendanceRawScanEventResponse:
        """Build a raw scan event response payload."""

        return AttendanceRawScanEventResponse(
            id=raw_event.id,
            employee_id=raw_event.employee_id,
            user_id=raw_event.user_id,
            employee_matricule=employee.matricule,
            employee_name=self._build_employee_name(employee),
            reader_type=AttendanceReaderTypeEnum(raw_event.reader_type),
            scanned_at=raw_event.scanned_at,
            source=raw_event.source,
            created_at=raw_event.created_at,
        )

    def _build_daily_summary_response(
        self,
        summary: AttendanceDailySummary,
        employee: Employee,
    ) -> AttendanceDailySummaryResponse:
        """Build a daily summary response payload."""

        return AttendanceDailySummaryResponse(
            id=summary.id,
            employee_id=summary.employee_id,
            employee_matricule=employee.matricule,
            employee_name=self._build_employee_name(employee),
            attendance_date=summary.attendance_date,
            first_check_in_at=summary.first_check_in_at,
            last_check_out_at=summary.last_check_out_at,
            worked_duration_minutes=summary.worked_duration_minutes,
            status=AttendanceStatusEnum(summary.status),
            linked_request_id=summary.linked_request_id,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )

    def _build_monthly_report_response(
        self,
        report: AttendanceMonthlyReport,
        employee: Employee,
    ) -> AttendanceMonthlyReportResponse:
        """Build a monthly report response payload."""

        return AttendanceMonthlyReportResponse(
            id=report.id,
            employee_id=report.employee_id,
            employee_matricule=employee.matricule,
            employee_name=self._build_employee_name(employee),
            report_year=report.report_year,
            report_month=report.report_month,
            total_worked_days=report.total_worked_days,
            total_worked_minutes=report.total_worked_minutes,
            total_present_days=report.total_present_days,
            total_absence_days=report.total_absence_days,
            total_leave_days=report.total_leave_days,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )

    def _resolve_report_target_employees(
        self,
        *,
        employee_id: int | None,
        include_inactive: bool,
    ) -> list[Employee]:
        """Resolve employees targeted by a monthly report generation request."""

        if employee_id is not None:
            employee = self._get_employee(employee_id)
            if not include_inactive and not employee.is_active:
                raise AttendanceValidationError(
                    "Inactive employees require include_inactive=true."
                )

            return [employee]

        statement: Select[tuple[Employee]] = select(Employee)
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))

        statement = statement.order_by(
            Employee.last_name.asc(),
            Employee.first_name.asc(),
            Employee.id.asc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def _get_month_date_range(
        self,
        report_year: int,
        report_month: int,
    ) -> tuple[date, date]:
        """Return the first and last dates of a target month."""

        last_day = monthrange(report_year, report_month)[1]
        return (
            date(report_year, report_month, 1),
            date(report_year, report_month, last_day),
        )

    def _aggregate_monthly_totals(
        self,
        summaries: list[AttendanceDailySummary],
    ) -> dict[str, int]:
        """Aggregate monthly totals from day-level attendance summaries."""

        total_worked_days = sum(
            1
            for summary in summaries
            if summary.worked_duration_minutes is not None
        )
        total_worked_minutes = sum(
            summary.worked_duration_minutes or 0 for summary in summaries
        )
        total_present_days = sum(
            1 for summary in summaries if summary.status == AttendanceStatusEnum.PRESENT.value
        )
        total_absence_days = sum(
            1 for summary in summaries if summary.status == AttendanceStatusEnum.ABSENT.value
        )
        total_leave_days = sum(
            1 for summary in summaries if summary.status == AttendanceStatusEnum.LEAVE.value
        )
        return {
            "total_worked_days": total_worked_days,
            "total_worked_minutes": total_worked_minutes,
            "total_present_days": total_present_days,
            "total_absence_days": total_absence_days,
            "total_leave_days": total_leave_days,
        }

    def _get_or_create_daily_summary(
        self,
        employee_id: int,
        attendance_date: date,
    ) -> AttendanceDailySummary:
        """Return the day summary for an employee or create a new blank one."""

        summary = self.db.execute(
            select(AttendanceDailySummary).where(
                AttendanceDailySummary.employee_id == employee_id,
                AttendanceDailySummary.attendance_date == attendance_date,
            )
        ).scalar_one_or_none()
        if summary is not None:
            return summary

        summary = AttendanceDailySummary(
            employee_id=employee_id,
            attendance_date=attendance_date,
            first_check_in_at=None,
            last_check_out_at=None,
            worked_duration_minutes=None,
            status=AttendanceStatusEnum.ABSENT.value,
            linked_request_id=None,
        )
        self.db.add(summary)
        return summary

    def _apply_scan_to_daily_summary(
        self,
        *,
        daily_summary: AttendanceDailySummary,
        reader_type: AttendanceReaderTypeEnum,
        scanned_at: datetime,
    ) -> None:
        """Apply one IN or OUT scan event to a daily summary."""

        if reader_type == AttendanceReaderTypeEnum.IN:
            if (
                daily_summary.first_check_in_at is None
                or scanned_at < daily_summary.first_check_in_at
            ):
                daily_summary.first_check_in_at = scanned_at
        elif reader_type == AttendanceReaderTypeEnum.OUT:
            if (
                daily_summary.last_check_out_at is None
                or scanned_at > daily_summary.last_check_out_at
            ):
                daily_summary.last_check_out_at = scanned_at
        else:
            raise AttendanceValidationError("Unsupported attendance reader type.")

        daily_summary.worked_duration_minutes = self._compute_worked_duration_minutes(
            first_check_in_at=daily_summary.first_check_in_at,
            last_check_out_at=daily_summary.last_check_out_at,
        )
        daily_summary.status = self._derive_daily_summary_status(daily_summary).value

    def _compute_worked_duration_minutes(
        self,
        *,
        first_check_in_at: datetime | None,
        last_check_out_at: datetime | None,
    ) -> int | None:
        """Compute the worked duration in minutes when both scans are coherent."""

        if first_check_in_at is None or last_check_out_at is None:
            return None

        if last_check_out_at < first_check_in_at:
            return None

        duration_seconds = (last_check_out_at - first_check_in_at).total_seconds()
        return int(duration_seconds // 60)

    def _derive_daily_summary_status(
        self,
        daily_summary: AttendanceDailySummary,
    ) -> AttendanceStatusEnum:
        """Derive the practical attendance status from summary scan fields."""

        if daily_summary.first_check_in_at is not None or daily_summary.last_check_out_at is not None:
            if (
                daily_summary.first_check_in_at is not None
                and daily_summary.last_check_out_at is not None
                and daily_summary.worked_duration_minutes is not None
            ):
                return AttendanceStatusEnum.PRESENT

            return AttendanceStatusEnum.INCOMPLETE

        if daily_summary.status == AttendanceStatusEnum.LEAVE.value:
            return AttendanceStatusEnum.LEAVE

        return AttendanceStatusEnum.ABSENT

    def _get_employee(self, employee_id: int) -> Employee:
        """Return an employee by id."""

        employee = self.db.get(Employee, employee_id)
        if employee is None:
            raise AttendanceNotFoundError("Employee not found.")

        return employee

    def _get_active_employee_by_matricule(self, matricule: str) -> Employee:
        """Return an active employee resolved by matricule."""

        employee = self.db.execute(
            select(Employee)
            .where(
                Employee.matricule == matricule,
                Employee.is_active.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if employee is None:
            raise AttendanceNotFoundError(
                "Active employee not found for the provided matricule."
            )

        return employee

    def _get_employees_by_ids(self, employee_ids: set[int]) -> dict[int, Employee]:
        """Load employees in bulk by id."""

        if not employee_ids:
            return {}

        employees = list(
            self.db.execute(select(Employee).where(Employee.id.in_(employee_ids)))
            .scalars()
            .all()
        )
        return {employee.id: employee for employee in employees}

    def _validate_date_range(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> None:
        """Reject invalid date-range filters."""

        if date_from is not None and date_to is not None and date_from > date_to:
            raise AttendanceValidationError("date_from cannot be after date_to.")

    def _build_employee_name(self, employee: Employee) -> str:
        """Build a readable employee full name."""

        return f"{employee.first_name} {employee.last_name}"
