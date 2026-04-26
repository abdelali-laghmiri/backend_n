from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.apps.announcements.models import Announcement, AnnouncementRead, AnnouncementTypeEnum
from app.apps.announcements.schemas import AnnouncementCreateRequest
from app.apps.announcements.service import AnnouncementsService
from app.apps.attendance.models import (
    AttendanceDailySummary,
    AttendanceMonthlyReport,
    AttendanceRawScanEvent,
    AttendanceStatusEnum,
    NfcCard,
)
from app.apps.employees.models import Employee
from app.apps.messages.models import Message, MessageTemplate
from app.apps.messages.schemas import (
    MessageCreateRequest,
    MessageRecipientInput,
)
from app.apps.messages.service import MessagesService
from app.apps.notifications.models import Notification, NotificationTypeEnum
from app.apps.notifications.service import NotificationsService
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.permissions.models import JobTitlePermissionAssignment, Permission
from app.apps.permissions.service import PermissionsService
from app.apps.requests.models import RequestFieldTypeEnum, RequestResolverTypeEnum, RequestStepKindEnum, RequestType
from app.apps.requests.schemas import (
    RequestCreateRequest,
    RequestTypeCreateRequest,
    RequestTypeFieldCreateRequest,
    RequestWorkflowStepCreateRequest,
)
from app.apps.requests.service import RequestsService
from app.apps.scanner_app.models import AllowedOrigin, ScannerAppBuild
from app.apps.users.models import User
from app.core.database import SessionLocal
from app.core.security import PasswordManager


UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def at_utc(day_value: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day_value, time(hour=hour, minute=minute, tzinfo=UTC))


def get_user(session, matricule: str) -> User:
    user = session.execute(select(User).where(User.matricule == matricule).limit(1)).scalar_one_or_none()
    if user is None:
        raise RuntimeError(f"User '{matricule}' not found.")
    return user


def get_employee(session, matricule: str) -> Employee:
    employee = session.execute(
        select(Employee).where(Employee.matricule == matricule).limit(1)
    ).scalar_one_or_none()
    if employee is None:
        raise RuntimeError(f"Employee '{matricule}' not found.")
    return employee


def get_department(session) -> Department:
    department = session.execute(select(Department).order_by(Department.id.asc()).limit(1)).scalar_one_or_none()
    if department is None:
        raise RuntimeError("No department found.")
    return department


def get_teams(session) -> list[Team]:
    teams = list(session.execute(select(Team).order_by(Team.id.asc())).scalars().all())
    if len(teams) < 2:
        raise RuntimeError("At least two teams are required.")
    return teams


def get_permission(session, code: str) -> Permission:
    permission = session.execute(
        select(Permission).where(Permission.code == code).limit(1)
    ).scalar_one_or_none()
    if permission is None:
        raise RuntimeError(f"Permission '{code}' not found.")
    return permission


def ensure_scanner_operator(session, department: Department, first_team: Team) -> tuple[User, Employee]:
    job_title = session.execute(
        select(JobTitle).where(JobTitle.code == "SCANNER_OPERATOR").limit(1)
    ).scalar_one_or_none()
    if job_title is None:
        job_title = JobTitle(
            name="Scanner Operator",
            code="SCANNER_OPERATOR",
            description="Attendance scanner ingestion operator.",
            hierarchical_level=1,
            is_active=True,
        )
        session.add(job_title)
        session.commit()
        session.refresh(job_title)

    attendance_ingest = get_permission(session, "attendance.nfc.ingest")
    assignment = session.execute(
        select(JobTitlePermissionAssignment)
        .where(
            JobTitlePermissionAssignment.job_title_id == job_title.id,
            JobTitlePermissionAssignment.permission_id == attendance_ingest.id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if assignment is None:
        session.add(
            JobTitlePermissionAssignment(
                job_title_id=job_title.id,
                permission_id=attendance_ingest.id,
            )
        )
        session.commit()

    user = session.execute(select(User).where(User.matricule == "SCN001").limit(1)).scalar_one_or_none()
    if user is None:
        user = User(
            matricule="SCN001",
            password_hash=PasswordManager.hash_password("Scan@12345"),
            first_name="Scanner",
            last_name="Operator",
            email="scanner.operator@smalltest.local",
            is_super_admin=False,
            is_active=True,
            must_change_password=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    employee = session.execute(
        select(Employee).where(Employee.matricule == "SCN001").limit(1)
    ).scalar_one_or_none()
    if employee is None:
        employee = Employee(
            user_id=user.id,
            matricule="SCN001",
            first_name="Scanner",
            last_name="Operator",
            email="scanner.operator@smalltest.local",
            phone=None,
            image=None,
            hire_date=date.today(),
            available_leave_balance_days=0,
            department_id=department.id,
            team_id=first_team.id,
            job_title_id=job_title.id,
            is_active=True,
        )
        session.add(employee)
        session.commit()
        session.refresh(employee)

    return user, employee


def ensure_scanner_app_data(session, admin_user: User) -> None:
    origins = [
        "https://frontend-new-kohl.vercel.app",
        os.getenv("NFC_APP_URL", "https://nfc-selector-app.vercel.app").strip() or "https://nfc-selector-app.vercel.app",
    ]
    for origin in origins:
        existing = session.execute(
            select(AllowedOrigin).where(AllowedOrigin.origin == origin).limit(1)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                AllowedOrigin(
                    origin=origin,
                    source="seed",
                    is_active=True,
                    created_by_user_id=admin_user.id,
                )
            )
    session.commit()

    target_name = "Production Demo Build"
    existing_build = session.execute(
        select(ScannerAppBuild).where(ScannerAppBuild.target_name == target_name).limit(1)
    ).scalar_one_or_none()
    if existing_build is None:
        session.add(
            ScannerAppBuild(
                target_name=target_name,
                backend_base_url="https://backend-n-lac.vercel.app",
                allowed_origin=os.getenv("NFC_APP_URL", "https://nfc-selector-app.vercel.app"),
                android_download_url=os.getenv("scanner_android_package_url"),
                windows_download_url=os.getenv("scanner_windows_package_url"),
                linux_download_url=os.getenv("scanner_linux_package_url"),
                generated_by_user_id=admin_user.id,
                is_active=True,
            )
        )
        session.commit()


def ensure_attendance_data(session, employees: list[Employee]) -> None:
    today = date.today()
    for index, employee in enumerate(employees, start=1):
        card_uid = f"NFC-{employee.matricule}"
        monthly_total_minutes = 495 + 470 + 455 + index
        card = session.execute(
            select(NfcCard).where(NfcCard.nfc_uid == card_uid).limit(1)
        ).scalar_one_or_none()
        if card is None:
            session.add(
                NfcCard(employee_id=employee.id, nfc_uid=card_uid, is_active=True)
            )

        for days_ago, worked_minutes in ((2, 495), (1, 470), (0, 455 + index)):
            attendance_day = today - timedelta(days=days_ago)
            first_in = at_utc(attendance_day, 8, 15 + index)
            last_out = first_in + timedelta(minutes=worked_minutes)

            existing_summary = session.execute(
                select(AttendanceDailySummary)
                .where(
                    AttendanceDailySummary.employee_id == employee.id,
                    AttendanceDailySummary.attendance_date == attendance_day,
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing_summary is None:
                session.add(
                    AttendanceDailySummary(
                        employee_id=employee.id,
                        attendance_date=attendance_day,
                        first_check_in_at=first_in,
                        last_check_out_at=last_out,
                        worked_duration_minutes=worked_minutes,
                        status=AttendanceStatusEnum.PRESENT.value,
                        linked_request_id=None,
                    )
                )

            for reader_type, scanned_at in (("IN", first_in), ("OUT", last_out)):
                existing_event = session.execute(
                    select(AttendanceRawScanEvent)
                    .where(
                        AttendanceRawScanEvent.employee_id == employee.id,
                        AttendanceRawScanEvent.reader_type == reader_type,
                        AttendanceRawScanEvent.scanned_at == scanned_at,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing_event is None:
                    session.add(
                        AttendanceRawScanEvent(
                            employee_id=employee.id,
                            user_id=employee.user_id,
                            reader_type=reader_type,
                            scanned_at=scanned_at,
                            source="seeded-demo",
                        )
                    )

        report_year = today.year
        report_month = today.month
        existing_report = session.execute(
            select(AttendanceMonthlyReport)
            .where(
                AttendanceMonthlyReport.employee_id == employee.id,
                AttendanceMonthlyReport.report_year == report_year,
                AttendanceMonthlyReport.report_month == report_month,
            )
            .limit(1)
        ).scalar_one_or_none()
        if existing_report is None:
            session.add(
                AttendanceMonthlyReport(
                    employee_id=employee.id,
                    report_year=report_year,
                    report_month=report_month,
                    total_worked_days=3,
                    total_worked_minutes=monthly_total_minutes,
                    total_present_days=3,
                    total_absence_days=0,
                    total_leave_days=0,
                )
            )

    session.commit()


def ensure_announcements(session, admin_user: User, employee_user: User) -> None:
    service = AnnouncementsService(db=session)
    now = utcnow()
    definitions = [
        {
            "title": "Platform Reboot Completed",
            "summary": "The HR platform has been reset and reseeded for production testing.",
            "content": "All modules are now available with fresh medium-sized test data for validation.",
            "type": AnnouncementTypeEnum.IMPORTANT,
            "is_pinned": True,
            "published_at": now - timedelta(hours=2),
            "expires_at": now + timedelta(days=14),
        },
        {
            "title": "Expense Workflow Pilot",
            "summary": "Expense request workflows are now active for employee testing.",
            "content": "Employees can submit expense requests and managers can approve them through the seeded approval chain.",
            "type": AnnouncementTypeEnum.INFO,
            "is_pinned": False,
            "published_at": now - timedelta(days=1),
            "expires_at": now + timedelta(days=30),
        },
        {
            "title": "Attendance Badge Policy",
            "summary": "All seeded employees now have NFC cards for attendance validation.",
            "content": "Use the seeded NFC cards to verify attendance ingestion, summary generation, and reporting flows.",
            "type": AnnouncementTypeEnum.MANDATORY,
            "is_pinned": False,
            "published_at": now - timedelta(hours=6),
            "expires_at": now + timedelta(days=21),
        },
    ]

    created_announcements: list[Announcement] = []
    for definition in definitions:
        existing = session.execute(
            select(Announcement).where(Announcement.title == definition["title"]).limit(1)
        ).scalar_one_or_none()
        if existing is None:
            created = service.create_announcement(
                AnnouncementCreateRequest(
                    title=definition["title"],
                    summary=definition["summary"],
                    content=definition["content"],
                    type=definition["type"],
                    is_pinned=definition["is_pinned"],
                    is_active=True,
                    published_at=definition["published_at"],
                    expires_at=definition["expires_at"],
                ),
                admin_user,
            )
            created_announcements.append(created)
        else:
            created_announcements.append(existing)

    first_announcement = created_announcements[0]
    read_record = session.execute(
        select(AnnouncementRead)
        .where(
            AnnouncementRead.announcement_id == first_announcement.id,
            AnnouncementRead.user_id == employee_user.id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if read_record is None:
        session.add(
            AnnouncementRead(
                announcement_id=first_announcement.id,
                user_id=employee_user.id,
                seen_at=utcnow(),
            )
        )
        session.commit()


def ensure_message_templates(session, rh_manager: User) -> None:
    existing = session.execute(
        select(MessageTemplate)
        .where(
            MessageTemplate.owner_user_id == rh_manager.id,
            MessageTemplate.name == "Policy Reminder",
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            MessageTemplate(
                owner_user_id=rh_manager.id,
                name="Policy Reminder",
                subject="Please review the updated internal policy",
                body="This is a seeded template for testing the message templates workflow.",
                is_active=True,
            )
        )
        session.commit()


def ensure_messages(session, rh_manager: User, department_manager: User, tld_one: User, emp_one: User, recipients: list[User]) -> None:
    notifications_service = NotificationsService(db=session)
    permissions_service = PermissionsService(db=session)
    service = MessagesService(
        db=session,
        notifications_service=notifications_service,
        permissions_service=permissions_service,
    )

    kickoff_subject = "Welcome to the seeded production workspace"
    kickoff = session.execute(
        select(Message).where(Message.subject == kickoff_subject).limit(1)
    ).scalar_one_or_none()
    if kickoff is None:
        kickoff = service.send_message(
            rh_manager,
            MessageCreateRequest(
                subject=kickoff_subject,
                body="All major modules now have fresh seeded data. Please validate your dashboards, requests, messages, and attendance flows.",
                recipients=[MessageRecipientInput(user_id=user.id, can_reply=True) for user in recipients],
            ),
        )

    ops_update_subject = "Operations team alignment"
    existing_ops_update = session.execute(
        select(Message).where(Message.subject == ops_update_subject).limit(1)
    ).scalar_one_or_none()
    if existing_ops_update is None:
        leader_recipients = [user for user in recipients if user.matricule in {"TLD001", "TLD002"}]
        service.send_message(
            department_manager,
            MessageCreateRequest(
                subject=ops_update_subject,
                body="Please validate the seeded request approvals and attendance data with your teams.",
                recipients=[MessageRecipientInput(user_id=user.id, can_reply=True) for user in leader_recipients],
            ),
        )

    existing_reply = session.execute(
        select(Message)
        .where(
            Message.parent_message_id == kickoff.id,
            Message.sender_user_id == tld_one.id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_reply is None:
        service.send_message(
            tld_one,
            MessageCreateRequest(
                subject=f"Re: {kickoff.subject}",
                body="Team-level messaging, notifications, and threaded replies are ready for validation.",
                recipients=[MessageRecipientInput(user_id=emp_one.id, can_reply=True)],
                parent_message_id=kickoff.id,
            ),
        )


def ensure_request_type(session, service: RequestsService, code: str, name: str, description: str) -> RequestType:
    request_type = session.execute(
        select(RequestType).where(RequestType.code == code).limit(1)
    ).scalar_one_or_none()
    if request_type is not None:
        return request_type

    return service.create_request_type(
        RequestTypeCreateRequest(code=code, name=name, description=description)
    )


def ensure_request_configuration(session, service: RequestsService) -> dict[str, RequestType]:
    expense_type = ensure_request_type(
        session,
        service,
        code="expense_general",
        name="General Expense Request",
        description="Employee expense reimbursement workflow used for seeded testing.",
    )
    equipment_type = ensure_request_type(
        session,
        service,
        code="equipment_access",
        name="Equipment Access Request",
        description="Hardware or system access workflow used for seeded testing.",
    )

    if not service.list_request_fields(expense_type.id):
        service.create_request_field(
            expense_type.id,
            RequestTypeFieldCreateRequest(
                code="purpose",
                label="Purpose",
                field_type=RequestFieldTypeEnum.TEXT,
                is_required=True,
                placeholder="Why is this expense needed?",
                help_text="Short business justification.",
                default_value=None,
                sort_order=1,
            ),
        )
        service.create_request_field(
            expense_type.id,
            RequestTypeFieldCreateRequest(
                code="amount",
                label="Amount",
                field_type=RequestFieldTypeEnum.NUMBER,
                is_required=True,
                placeholder=None,
                help_text="Estimated reimbursable amount.",
                default_value=None,
                sort_order=2,
            ),
        )

    if not service.list_workflow_steps(expense_type.id):
        service.create_workflow_step(
            expense_type.id,
            RequestWorkflowStepCreateRequest(
                step_order=1,
                name="Team leader review",
                step_kind=RequestStepKindEnum.APPROVER,
                resolver_type=RequestResolverTypeEnum.TEAM_LEADER,
                resolver_job_title_id=None,
                is_required=True,
            ),
        )
        service.create_workflow_step(
            expense_type.id,
            RequestWorkflowStepCreateRequest(
                step_order=2,
                name="Department manager validation",
                step_kind=RequestStepKindEnum.APPROVER,
                resolver_type=RequestResolverTypeEnum.DEPARTMENT_MANAGER,
                resolver_job_title_id=None,
                is_required=True,
            ),
        )

    if not service.list_request_fields(equipment_type.id):
        service.create_request_field(
            equipment_type.id,
            RequestTypeFieldCreateRequest(
                code="equipment",
                label="Equipment or access",
                field_type=RequestFieldTypeEnum.TEXT,
                is_required=True,
                placeholder="Laptop, badge, VPN token...",
                help_text="Requested item or access right.",
                default_value=None,
                sort_order=1,
            ),
        )
        service.create_request_field(
            equipment_type.id,
            RequestTypeFieldCreateRequest(
                code="justification",
                label="Justification",
                field_type=RequestFieldTypeEnum.TEXTAREA,
                is_required=True,
                placeholder="Explain the operational need.",
                help_text="Detailed operational context.",
                default_value=None,
                sort_order=2,
            ),
        )

    if not service.list_workflow_steps(equipment_type.id):
        service.create_workflow_step(
            equipment_type.id,
            RequestWorkflowStepCreateRequest(
                step_order=1,
                name="Team leader review",
                step_kind=RequestStepKindEnum.APPROVER,
                resolver_type=RequestResolverTypeEnum.TEAM_LEADER,
                resolver_job_title_id=None,
                is_required=True,
            ),
        )
        service.create_workflow_step(
            equipment_type.id,
            RequestWorkflowStepCreateRequest(
                step_order=2,
                name="HR manager approval",
                step_kind=RequestStepKindEnum.APPROVER,
                resolver_type=RequestResolverTypeEnum.RH_MANAGER,
                resolver_job_title_id=None,
                is_required=True,
            ),
        )

    return {"expense": expense_type, "equipment": equipment_type}


def ensure_requests(session, emp_one_user: User, emp_two_user: User, tld_one_user: User, tld_two_user: User, department_manager: User) -> None:
    service = RequestsService(db=session)
    request_types = ensure_request_configuration(session, service)

    workflow_requests_exist = session.execute(select(Notification).where(Notification.type == NotificationTypeEnum.REQUEST_ASSIGNED.value).limit(1)).scalar_one_or_none()
    if workflow_requests_exist is not None:
        return

    approved_request = service.create_request(
        emp_one_user,
        RequestCreateRequest(
            request_type_id=request_types["expense"].id,
            values={"purpose": "Client travel reimbursement", "amount": 1200},
        ),
    )
    approved_request = service.approve_current_step(
        approved_request.id,
        tld_one_user,
        comment="Validated by team leader.",
    )
    service.approve_current_step(
        approved_request.id,
        department_manager,
        comment="Approved for reimbursement.",
    )

    rejected_request = service.create_request(
        emp_two_user,
        RequestCreateRequest(
            request_type_id=request_types["equipment"].id,
            values={
                "equipment": "High-end laptop",
                "justification": "Requested for field reporting duties.",
            },
        ),
    )
    service.reject_current_step(
        rejected_request.id,
        tld_two_user,
        comment="Current scope does not require this equipment.",
    )

    pending_rh_request = service.create_request(
        emp_one_user,
        RequestCreateRequest(
            request_type_id=request_types["equipment"].id,
            values={
                "equipment": "Secure VPN token",
                "justification": "Needed for remote access during production support rotations.",
            },
        ),
    )
    service.approve_current_step(
        pending_rh_request.id,
        tld_one_user,
        comment="Operationally justified.",
    )

    service.create_request(
        emp_two_user,
        RequestCreateRequest(
            request_type_id=request_types["expense"].id,
            values={"purpose": "Office supplies restock", "amount": 450},
        ),
    )


def ensure_manual_notifications(session, recipients: list[User]) -> None:
    service = NotificationsService(db=session)
    titles = {
        "EMP001": "Attendance follow-up required",
        "EMP002": "Arrival time review",
    }
    for user in recipients:
        if user.matricule not in titles:
            continue

        title = titles[user.matricule]
        existing = session.execute(
            select(Notification)
            .where(
                Notification.recipient_user_id == user.id,
                Notification.title == title,
            )
            .limit(1)
        ).scalar_one_or_none()
        if existing is None:
            service.create_notification(
                recipient_user_id=user.id,
                title=title,
                message="This seeded notification is available for testing unread and read notification flows.",
                notification_type=NotificationTypeEnum.ATTENDANCE_LATE,
                target_url="/attendance",
            )


def ensure_performance_data(session, admin_user: User, teams: list[Team]) -> None:
    from app.apps.performance.models import TeamDailyPerformance, TeamObjective, TeamObjectiveTypeEnum

    objective_values = {teams[0].id: 24.0, teams[1].id: 18.0}
    for team in teams[:2]:
        objective = session.execute(
            select(TeamObjective)
            .where(TeamObjective.team_id == team.id, TeamObjective.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if objective is None:
            session.add(
                TeamObjective(
                    team_id=team.id,
                    objective_value=objective_values[team.id],
                    objective_type=TeamObjectiveTypeEnum.TASKS.value,
                    is_active=True,
                )
            )

    session.commit()

    today = date.today()
    for index, team in enumerate(teams[:2], start=1):
        objective_value = objective_values[team.id]
        for days_ago, achieved_value in ((4, 20 + index), (3, 22 + index), (2, 23 + index), (1, 19 + index), (0, 24 + index)):
            performance_date = today - timedelta(days=days_ago)
            existing = session.execute(
                select(TeamDailyPerformance)
                .where(
                    TeamDailyPerformance.team_id == team.id,
                    TeamDailyPerformance.performance_date == performance_date,
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    TeamDailyPerformance(
                        team_id=team.id,
                        performance_date=performance_date,
                        objective_value=objective_value,
                        achieved_value=achieved_value,
                        performance_percentage=round((achieved_value / objective_value) * 100, 2),
                        created_by_user_id=admin_user.id,
                    )
                )
    session.commit()


def main() -> None:
    session = SessionLocal()
    try:
        admin_user = get_user(session, "admin")
        rh_manager = get_user(session, "RHM001")
        department_manager = get_user(session, "DPM001")
        tld_one = get_user(session, "TLD001")
        tld_two = get_user(session, "TLD002")
        emp_one_user = get_user(session, "EMP001")
        emp_two_user = get_user(session, "EMP002")

        department = get_department(session)
        teams = get_teams(session)
        scanner_user, scanner_employee = ensure_scanner_operator(session, department, teams[0])

        employees = [
            get_employee(session, "RHM001"),
            get_employee(session, "DPM001"),
            get_employee(session, "TLD001"),
            get_employee(session, "TLD002"),
            get_employee(session, "EMP001"),
            get_employee(session, "EMP002"),
            scanner_employee,
        ]

        ensure_scanner_app_data(session, admin_user)
        ensure_attendance_data(session, employees)
        ensure_performance_data(session, admin_user, teams)
        ensure_announcements(session, admin_user, emp_one_user)
        ensure_message_templates(session, rh_manager)
        ensure_messages(
            session,
            rh_manager,
            department_manager,
            tld_one,
            emp_one_user,
            [department_manager, tld_one, tld_two, emp_one_user, emp_two_user],
        )
        ensure_requests(session, emp_one_user, emp_two_user, tld_one, tld_two, department_manager)
        ensure_manual_notifications(
            session,
            [rh_manager, department_manager, tld_one, tld_two, emp_one_user, emp_two_user, scanner_user],
        )

        print("Full production test dataset created successfully.")
        print("Additional scanner account: SCN001 / Scan@12345")
    finally:
        session.close()


if __name__ == "__main__":
    main()
