from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.attendance.models import (
    AttendanceDailySummary,
    AttendanceEventTypeEnum,
    AttendanceMonthlyReport,
    AttendanceRawScanEvent,
    AttendanceReaderTypeEnum,
    AttendanceStatusEnum,
    NfcCard,
)
from app.apps.forgot_badge.models import TemporaryNfcAssignment
from app.apps.attendance.schemas import (
    AttendanceDailySummaryResponse,
    AttendanceNfcCardAssignRequest,
    AttendanceNfcCardResponse,
    AttendanceNfcScanIngestRequest,
    AttendanceMonthlyReportGenerateRequest,
    AttendanceMonthlyReportResponse,
    AttendanceRawScanEventResponse,
    AttendanceScanIngestRequest,
    AttendanceScanIngestResponse,
)
from app.apps.employees.models import Employee
from app.apps.forgot_badge.service import ForgotBadgeService


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
        return self._ingest_scan_for_employee(
            employee=employee,
            reader_type=payload.reader_type,
            scanned_at=payload.scanned_at,
            source=payload.source,
        )

    def ingest_nfc_scan_event(
        self,
        payload: AttendanceNfcScanIngestRequest,
    ) -> tuple[AttendanceRawScanEvent, AttendanceDailySummary]:
        """Persist an NFC-based raw scan event and update the employee daily summary."""

        nfc_card = self._get_nfc_card_by_uid(payload.nfc_uid)
        assignment_id = None
        is_temporary = False

        if nfc_card.is_active:
            permanent_employee = self.db.get(Employee, nfc_card.employee_id)
            if permanent_employee is not None and permanent_employee.is_active:
                employee = permanent_employee
            else:
                employee = self._resolve_temporary_employee(nfc_card, payload.scanned_at.date())
                if employee is not None:
                    is_temporary = True
                else:
                    raise AttendanceValidationError(
                        "The NFC card is linked to an inactive employee."
                    )
        else:
            employee = self._resolve_temporary_employee(nfc_card, payload.scanned_at.date())
            if employee is None:
                raise AttendanceValidationError(
                    "The NFC card is not active and has no temporary assignment for today."
                )
            is_temporary = True

        reader_type = self._map_attendance_type_to_reader_type(payload.attendance_type)
        result = self._ingest_scan_for_employee(
            employee=employee,
            reader_type=reader_type,
            scanned_at=payload.scanned_at,
            source=payload.source,
        )

        if is_temporary and reader_type == AttendanceReaderTypeEnum.IN:
            assignment = self._get_active_temporary_assignment_by_card(
                nfc_card.id, payload.scanned_at.date()
            )
            if assignment is not None:
                try:
                    forgot_service = ForgotBadgeService(self.db)
                    forgot_service.on_check_in_with_assignment_id(
                        assignment_id=assignment.id,
                        check_in_attendance_id=result[0].id,
                    )
                except Exception:
                    pass

        if is_temporary and reader_type == AttendanceReaderTypeEnum.OUT:
            assignment = self._get_active_temporary_assignment_by_card(
                nfc_card.id, payload.scanned_at.date()
            )
            if assignment is not None:
                try:
                    forgot_service = ForgotBadgeService(self.db)
                    forgot_service.on_check_out_with_assignment_id(
                        assignment_id=assignment.id,
                        check_out_attendance_id=result[0].id,
                    )
                except Exception:
                    pass

        return result

    def assign_nfc_card(
        self,
        payload: AttendanceNfcCardAssignRequest,
    ) -> NfcCard:
        """Attach one NFC card to one active employee."""

        employee = self._get_employee(payload.employee_id)
        if not employee.is_active:
            raise AttendanceValidationError(
                "Inactive employees cannot be assigned NFC cards."
            )

        normalized_nfc_uid = self._normalize_nfc_uid(payload.nfc_uid)
        existing_card = self._find_nfc_card_by_uid(normalized_nfc_uid)
        if existing_card is not None:
            if existing_card.employee_id != employee.id:
                raise AttendanceConflictError(
                    "This NFC card is already assigned to another employee."
                )

            if existing_card.is_active:
                return existing_card

            raise AttendanceValidationError(
                "This NFC card is already linked to the employee but is inactive."
            )

        existing_active_employee_card = self._get_active_nfc_card_for_employee(employee.id)
        if existing_active_employee_card is not None:
            raise AttendanceConflictError(
                "This employee already has an active NFC card."
            )

        nfc_card = NfcCard(
            employee_id=employee.id,
            nfc_uid=normalized_nfc_uid,
            is_active=True,
        )
        self.db.add(nfc_card)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AttendanceConflictError("Failed to assign the NFC card.") from exc

        self.db.refresh(nfc_card)
        return nfc_card

    def _ingest_scan_for_employee(
        self,
        *,
        employee: Employee,
        reader_type: AttendanceReaderTypeEnum,
        scanned_at: datetime,
        source: str,
    ) -> tuple[AttendanceRawScanEvent, AttendanceDailySummary]:
        """Persist a raw scan event and update the target employee daily summary."""

        attendance_date = scanned_at.date()
        stored_scanned_at = scanned_at.astimezone(timezone.utc)
        daily_summary = self._get_or_create_daily_summary(employee.id, attendance_date)

        raw_event = AttendanceRawScanEvent(
            employee_id=employee.id,
            user_id=employee.user_id,
            reader_type=reader_type.value,
            scanned_at=stored_scanned_at,
            source=source,
        )
        self.db.add(raw_event)

        self._apply_scan_to_daily_summary(
            daily_summary=daily_summary,
            reader_type=reader_type,
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
        raw_event.scanned_at = self._normalize_utc_datetime(raw_event.scanned_at)
        self._normalize_daily_summary_datetimes(daily_summary)
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

    def build_nfc_card_response(
        self,
        nfc_card: NfcCard,
    ) -> AttendanceNfcCardResponse:
        """Build the API response for an NFC card assignment result."""

        employee = self._get_employee(nfc_card.employee_id)
        return AttendanceNfcCardResponse(
            id=nfc_card.id,
            employee_id=nfc_card.employee_id,
            employee_matricule=employee.matricule,
            employee_name=self._build_employee_name(employee),
            nfc_uid=nfc_card.nfc_uid,
            is_active=nfc_card.is_active,
            created_at=nfc_card.created_at,
            updated_at=nfc_card.updated_at,
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
            scanned_at=self._normalize_utc_datetime(raw_event.scanned_at),
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
            first_check_in_at=self._normalize_utc_datetime(summary.first_check_in_at),
            last_check_out_at=self._normalize_utc_datetime(summary.last_check_out_at),
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

        normalized_scanned_at = self._normalize_utc_datetime(scanned_at)
        self._normalize_daily_summary_datetimes(daily_summary)

        if reader_type == AttendanceReaderTypeEnum.IN:
            if (
                daily_summary.first_check_in_at is None
                or normalized_scanned_at < daily_summary.first_check_in_at
            ):
                daily_summary.first_check_in_at = normalized_scanned_at
        elif reader_type == AttendanceReaderTypeEnum.OUT:
            if (
                daily_summary.last_check_out_at is None
                or normalized_scanned_at > daily_summary.last_check_out_at
            ):
                daily_summary.last_check_out_at = normalized_scanned_at
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

        first_check_in_at = self._normalize_utc_datetime(first_check_in_at)
        last_check_out_at = self._normalize_utc_datetime(last_check_out_at)
        if first_check_in_at is None or last_check_out_at is None:
            return None

        if last_check_out_at < first_check_in_at:
            return None

        duration_seconds = (last_check_out_at - first_check_in_at).total_seconds()
        return int(duration_seconds // 60)

    def _resolve_temporary_nfc_assignment(
        self,
        *,
        nfc_card_id: int,
        valid_for_date: date,
    ) -> tuple[int | None, int | None, int | None]:
        """Resolve active temporary NFC assignment and return (assignment_id, employee_id, is_temporary)."""

        try:
            forgot_service = ForgotBadgeService(self.db)
            employee = forgot_service.resolve_employee_by_temporary_card(
                nfc_card_id=nfc_card_id,
                valid_for_date=valid_for_date,
            )
            if employee is not None:
                assignment = forgot_service.get_active_temporary_assignment(
                    employee_id=employee.id,
                    valid_for_date=valid_for_date,
                )
                if assignment is not None:
                    return (assignment.id, employee.id, employee.id)
        except Exception:
            pass

        return (None, None, None)

    def _finalize_temporary_nfc_assignment(
        self,
        *,
        assignment_id: int | None,
        nfc_card_id: int,
        check_out_attendance_id: int | None,
    ) -> None:
        """Finalize temporary NFC assignment after CHECK_OUT."""

        if assignment_id is None:
            return

        try:
            forgot_service = ForgotBadgeService(self.db)
            forgot_service.on_check_out_with_assignment_id(
                assignment_id=assignment_id,
                check_out_attendance_id=check_out_attendance_id or 0,
            )
        except Exception:
            pass

    def _resolve_temporary_employee(
        self,
        nfc_card: NfcCard,
        valid_for_date: date,
    ) -> Employee | None:
        """Resolve employee from active temporary NFC assignment."""

        try:
            forgot_service = ForgotBadgeService(self.db)
            return forgot_service.resolve_employee_by_temporary_card(
                nfc_card_id=nfc_card.id,
                valid_for_date=valid_for_date,
            )
        except Exception:
            return None

    def _get_active_temporary_assignment_by_card(
        self,
        nfc_card_id: int,
        valid_for_date: date,
    ) -> TemporaryNfcAssignment | None:
        """Get active temporary assignment by card and date."""

        if "TemporaryNfcAssignment" not in dir():
            from app.apps.forgot_badge.models import TemporaryNfcAssignment

        return self.db.execute(
            select(TemporaryNfcAssignment)
            .where(
                TemporaryNfcAssignment.nfc_card_id == nfc_card_id,
                TemporaryNfcAssignment.valid_for_date == valid_for_date,
                TemporaryNfcAssignment.status == "ACTIVE",
            )
            .limit(1)
        ).scalar_one_or_none()

    def _derive_daily_summary_status(
        self,
        daily_summary: AttendanceDailySummary,
    ) -> AttendanceStatusEnum:
        """Derive the practical attendance status from summary scan fields."""

        if daily_summary.first_check_in_at is not None:
            return AttendanceStatusEnum.PRESENT

        if daily_summary.last_check_out_at is not None:
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

    def _get_active_employee_by_nfc_uid(self, nfc_uid: str) -> Employee:
        """Return the active employee linked to an active NFC card."""

        nfc_card = self._get_nfc_card_by_uid(nfc_uid)
        if not nfc_card.is_active:
            raise AttendanceValidationError("The NFC card linked to this scan is inactive.")

        employee = self.db.get(Employee, nfc_card.employee_id)
        if employee is None:
            raise AttendanceValidationError(
                "The NFC card is linked to a missing employee record."
            )

        if not employee.is_active:
            raise AttendanceValidationError(
                "The NFC card is linked to an inactive employee."
            )

        return employee

    def _get_nfc_card_by_uid(self, nfc_uid: str) -> NfcCard:
        """Return one NFC card by UID, regardless of card activation state."""

        nfc_card = self._find_nfc_card_by_uid(nfc_uid)
        if nfc_card is None:
            raise AttendanceNotFoundError("NFC card not found for the provided nfc_uid.")

        return nfc_card

    def _find_nfc_card_by_uid(self, nfc_uid: str) -> NfcCard | None:
        """Return one NFC card by UID, or None when no match exists."""

        normalized_nfc_uid = self._normalize_nfc_uid(nfc_uid)
        return self.db.execute(
            select(NfcCard)
            .where(func.upper(NfcCard.nfc_uid) == normalized_nfc_uid)
            .order_by(NfcCard.id.asc())
            .limit(1)
        ).scalar_one_or_none()

    def _get_active_nfc_card_for_employee(self, employee_id: int) -> NfcCard | None:
        """Return the first active NFC card currently assigned to an employee."""

        return self.db.execute(
            select(NfcCard)
            .where(
                NfcCard.employee_id == employee_id,
                NfcCard.is_active.is_(True),
            )
            .order_by(NfcCard.id.asc())
            .limit(1)
        ).scalar_one_or_none()

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

    def _map_attendance_type_to_reader_type(
        self,
        attendance_type: AttendanceEventTypeEnum,
    ) -> AttendanceReaderTypeEnum:
        """Convert explicit attendance intent to the legacy stored reader direction."""

        if attendance_type == AttendanceEventTypeEnum.CHECK_IN:
            return AttendanceReaderTypeEnum.IN

        if attendance_type == AttendanceEventTypeEnum.CHECK_OUT:
            return AttendanceReaderTypeEnum.OUT

        raise AttendanceValidationError("Unsupported attendance type.")

    def _normalize_nfc_uid(self, nfc_uid: str) -> str:
        """Normalize NFC card identifiers for service-layer comparisons."""

        return nfc_uid.strip().upper()

    def _normalize_daily_summary_datetimes(
        self,
        daily_summary: AttendanceDailySummary,
    ) -> None:
        """Normalize summary datetime fields to UTC-aware values in memory."""

        daily_summary.first_check_in_at = self._normalize_utc_datetime(
            daily_summary.first_check_in_at
        )
        daily_summary.last_check_out_at = self._normalize_utc_datetime(
            daily_summary.last_check_out_at
        )

    def _normalize_utc_datetime(
        self,
        value: datetime | None,
    ) -> datetime | None:
        """Treat naive attendance datetimes as UTC and return UTC-aware values."""

        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)
