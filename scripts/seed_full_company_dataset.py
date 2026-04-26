from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.apps.attendance.models import AttendanceDailySummary, NfcCard
from app.apps.attendance.schemas import (
    AttendanceEventTypeEnum,
    AttendanceMonthlyReportGenerateRequest,
    AttendanceNfcScanIngestRequest,
)
from app.apps.attendance.service import AttendanceService
from app.apps.employees.models import Employee
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.requests.models import (
    RequestActionEnum,
    RequestActionHistory,
    RequestFieldTypeEnum,
    RequestResolverTypeEnum,
    RequestStatusEnum,
    RequestStepKindEnum,
    RequestType,
    RequestTypeField,
    RequestWorkflowStep,
    WorkflowRequest,
)
from app.apps.requests.schemas import RequestCreateRequest
from app.apps.requests.service import RequestsService
from app.apps.setup.service import SetupService
from app.apps.users.models import User
from app.core.config import settings
from app.core.database import create_db_engine, create_session_factory
from app.core.security import PasswordManager

TARGET_EMPLOYEE_COUNT = 100
SEED_SOURCE = "seed_full_dataset"
DEFAULT_EMPLOYEE_PASSWORD = "Welcome123!"
DEFAULT_TEAM_SIZE = 7

DEPARTMENTS = (
    {
        "code": "HR",
        "name": "Human Resources",
        "description": "People operations, recruiting, and employee lifecycle management.",
        "teams": (
            ("HR-TA", "Talent Acquisition"),
            ("HR-OPS", "People Operations"),
        ),
    },
    {
        "code": "ENG",
        "name": "Engineering",
        "description": "Software engineering and internal platform delivery.",
        "teams": (
            ("ENG-PLAT", "Platform Engineering"),
            ("ENG-APP", "Application Engineering"),
        ),
    },
    {
        "code": "OPS",
        "name": "Operations",
        "description": "Operational execution, field delivery, and service continuity.",
        "teams": (
            ("OPS-FLD", "Field Operations"),
            ("OPS-CS", "Customer Operations"),
        ),
    },
    {
        "code": "SAL",
        "name": "Sales",
        "description": "Commercial execution for SMB and enterprise customers.",
        "teams": (
            ("SAL-SMB", "SMB Sales"),
            ("SAL-ENT", "Enterprise Sales"),
        ),
    },
    {
        "code": "FIN",
        "name": "Finance",
        "description": "Payroll, accounting, and reporting control.",
        "teams": (
            ("FIN-PAY", "Payroll Operations"),
            ("FIN-ACC", "Accounting Control"),
        ),
    },
    {
        "code": "SUP",
        "name": "Customer Support",
        "description": "Client support, case handling, and service follow-up.",
        "teams": (
            ("SUP-DESK", "Support Desk"),
            ("SUP-CSM", "Client Success"),
        ),
    },
)

FIRST_NAMES = [
    "Amine",
    "Aya",
    "Basma",
    "Chafik",
    "Dina",
    "El Mehdi",
    "Farah",
    "Hajar",
    "Imane",
    "Jad",
    "Khadija",
    "Lina",
    "Mehdi",
    "Meryem",
    "Nadia",
    "Omar",
    "Rania",
    "Salma",
    "Samir",
    "Yassine",
]

LAST_NAMES = [
    "Alaoui",
    "Amrani",
    "Benali",
    "Bennani",
    "Chami",
    "El Idrissi",
    "Fassi",
    "Haddad",
    "Jabri",
    "Karimi",
    "Lamrani",
    "Mansouri",
    "Naciri",
    "Ouazzani",
    "Raji",
    "Slaoui",
    "Tahiri",
    "Yazidi",
    "Zerhouni",
    "Ziani",
]


@dataclass(slots=True)
class RoleAssignment:
    matricule: str
    first_name: str
    last_name: str
    email: str
    job_title_code: str
    department_code: str | None = None
    team_code: str | None = None
    leave_balance: int = 18
    is_super_admin: bool = False


REQUEST_TYPE_DEFINITIONS = (
    {
        "code": "remote_work_request",
        "name": "Remote Work Request",
        "description": "Request to work remotely on a specific date.",
        "fields": (
            ("work_date", "Work Date", RequestFieldTypeEnum.DATE, True),
            ("reason", "Reason", RequestFieldTypeEnum.TEXTAREA, True),
        ),
        "workflow": (
            (1, "Team Leader Review", RequestResolverTypeEnum.TEAM_LEADER, None),
            (2, "Department Review", RequestResolverTypeEnum.DEPARTMENT_MANAGER, None),
        ),
    },
    {
        "code": "overtime_request",
        "name": "Overtime Request",
        "description": "Request to approve planned overtime work.",
        "fields": (
            ("work_date", "Work Date", RequestFieldTypeEnum.DATE, True),
            ("hours", "Hours", RequestFieldTypeEnum.NUMBER, True),
            ("justification", "Justification", RequestFieldTypeEnum.TEXTAREA, True),
        ),
        "workflow": (
            (1, "Team Leader Review", RequestResolverTypeEnum.TEAM_LEADER, None),
            (2, "Department Review", RequestResolverTypeEnum.DEPARTMENT_MANAGER, None),
        ),
    },
    {
        "code": "attendance_adjustment_request",
        "name": "Attendance Adjustment Request",
        "description": "Request to correct or justify one attendance anomaly.",
        "fields": (
            ("attendance_date", "Attendance Date", RequestFieldTypeEnum.DATE, True),
            ("requested_action", "Requested Action", RequestFieldTypeEnum.SELECT, True),
            ("reason", "Reason", RequestFieldTypeEnum.TEXTAREA, True),
        ),
        "workflow": (
            (1, "Attendance Review", None, "ATTENDANCE_MANAGER"),
            (2, "HR Validation", RequestResolverTypeEnum.RH_MANAGER, None),
        ),
    },
)


def build_management_assignments() -> list[RoleAssignment]:
    assignments: list[RoleAssignment] = [
        RoleAssignment(
            matricule=settings.superadmin_matricule or "SA-0001",
            first_name=settings.superadmin_first_name or "System",
            last_name=settings.superadmin_last_name or "Administrator",
            email=settings.superadmin_email or "superadmin@example.com",
            job_title_code="SUPER_ADMIN",
            department_code="HR",
            leave_balance=30,
            is_super_admin=True,
        ),
        RoleAssignment(
            matricule="HRM-0001",
            first_name="Nadia",
            last_name="Bennani",
            email="nadia.bennani@demo.local",
            job_title_code="RH_MANAGER",
            department_code="HR",
        ),
        RoleAssignment(
            matricule="HRA-0001",
            first_name="Salma",
            last_name="Amrani",
            email="salma.amrani@demo.local",
            job_title_code="HR_ASSISTANT",
            department_code="HR",
            team_code="HR-OPS",
        ),
        RoleAssignment(
            matricule="ATM-0001",
            first_name="Yassine",
            last_name="Tahiri",
            email="yassine.tahiri@demo.local",
            job_title_code="ATTENDANCE_MANAGER",
            department_code="HR",
            team_code="HR-OPS",
        ),
        RoleAssignment(
            matricule="FIN-0001",
            first_name="Farah",
            last_name="Karimi",
            email="farah.karimi@demo.local",
            job_title_code="FINANCE_PAYROLL",
            department_code="FIN",
            team_code="FIN-PAY",
        ),
    ]

    for department_index, department in enumerate(DEPARTMENTS, start=1):
        assignments.append(
            RoleAssignment(
                matricule=f"DM-{department_index:04d}",
                first_name=FIRST_NAMES[(department_index * 2) % len(FIRST_NAMES)],
                last_name=LAST_NAMES[(department_index * 3) % len(LAST_NAMES)],
                email=f"department.manager.{department['code'].lower()}@demo.local",
                job_title_code="DEPARTMENT_MANAGER",
                department_code=department["code"],
            )
        )
        for team_index, (team_code, team_name) in enumerate(department["teams"], start=1):
            assignments.append(
                RoleAssignment(
                    matricule=f"TL-{department_index:02d}{team_index:02d}",
                    first_name=FIRST_NAMES[(department_index * 5 + team_index) % len(FIRST_NAMES)],
                    last_name=LAST_NAMES[(department_index * 7 + team_index) % len(LAST_NAMES)],
                    email=f"team.leader.{team_code.lower()}@demo.local",
                    job_title_code="TEAM_LEADER",
                    department_code=department["code"],
                    team_code=team_code,
                )
            )

    return assignments


def build_employee_assignments() -> list[RoleAssignment]:
    assignments: list[RoleAssignment] = []
    employee_number = 1
    for department in DEPARTMENTS:
        for team_index, (team_code, _team_name) in enumerate(department["teams"], start=1):
            for seat_index in range(DEFAULT_TEAM_SIZE):
                first_name = FIRST_NAMES[(employee_number + team_index) % len(FIRST_NAMES)]
                last_name = LAST_NAMES[(employee_number * 2 + team_index) % len(LAST_NAMES)]
                assignments.append(
                    RoleAssignment(
                        matricule=f"EMP-{employee_number:04d}",
                        first_name=first_name,
                        last_name=last_name,
                        email=f"employee.{employee_number:04d}@demo.local",
                        job_title_code="EMPLOYEE",
                        department_code=department["code"],
                        team_code=team_code,
                        leave_balance=18 + (employee_number % 6),
                    )
                )
                employee_number += 1

    return assignments[: max(0, TARGET_EMPLOYEE_COUNT - 22)]


def upsert_department(db: Session, *, code: str, name: str, description: str) -> Department:
    department = db.execute(select(Department).where(Department.code == code).limit(1)).scalar_one_or_none()
    if department is None:
        department = Department(name=name, code=code, description=description, is_active=True)
        db.add(department)
        db.commit()
        db.refresh(department)
        return department

    department.name = name
    department.description = description
    department.is_active = True
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


def upsert_team(
    db: Session,
    *,
    code: str,
    name: str,
    description: str,
    department: Department,
) -> Team:
    team = db.execute(select(Team).where(Team.code == code).limit(1)).scalar_one_or_none()
    if team is None:
        team = Team(
            name=name,
            code=code,
            description=description,
            department_id=department.id,
            is_active=True,
        )
        db.add(team)
        db.commit()
        db.refresh(team)
        return team

    team.name = name
    team.description = description
    team.department_id = department.id
    team.is_active = True
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def get_job_titles_by_code(db: Session) -> dict[str, JobTitle]:
    job_titles = list(db.execute(select(JobTitle)).scalars().all())
    return {job_title.code: job_title for job_title in job_titles}


def ensure_user_and_employee(
    db: Session,
    *,
    assignment: RoleAssignment,
    department_by_code: dict[str, Department],
    team_by_code: dict[str, Team],
    job_title_by_code: dict[str, JobTitle],
    reset_passwords: bool,
) -> tuple[User, Employee]:
    user = db.execute(select(User).where(User.matricule == assignment.matricule).limit(1)).scalar_one_or_none()
    if user is None:
        user = User(
            matricule=assignment.matricule,
            password_hash=PasswordManager.hash_password(
                settings.superadmin_password.get_secret_value()
                if assignment.is_super_admin and settings.superadmin_password is not None
                else DEFAULT_EMPLOYEE_PASSWORD
            ),
            first_name=assignment.first_name,
            last_name=assignment.last_name,
            email=assignment.email,
            is_super_admin=assignment.is_super_admin,
            is_active=True,
            must_change_password=not assignment.is_super_admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.first_name = assignment.first_name
        user.last_name = assignment.last_name
        user.email = assignment.email
        user.is_super_admin = assignment.is_super_admin or user.is_super_admin
        user.is_active = True
        if reset_passwords:
            user.password_hash = PasswordManager.hash_password(
                settings.superadmin_password.get_secret_value()
                if assignment.is_super_admin and settings.superadmin_password is not None
                else DEFAULT_EMPLOYEE_PASSWORD
            )
            user.must_change_password = not assignment.is_super_admin
        db.add(user)
        db.commit()
        db.refresh(user)

    department = (
        department_by_code[assignment.department_code]
        if assignment.department_code is not None
        else None
    )
    team = team_by_code[assignment.team_code] if assignment.team_code is not None else None
    job_title = job_title_by_code[assignment.job_title_code]

    employee = db.execute(select(Employee).where(Employee.user_id == user.id).limit(1)).scalar_one_or_none()
    if employee is None:
        employee = db.execute(
            select(Employee).where(Employee.matricule == assignment.matricule).limit(1)
        ).scalar_one_or_none()

    if employee is None:
        employee = Employee(
            user_id=user.id,
            matricule=assignment.matricule,
            first_name=assignment.first_name,
            last_name=assignment.last_name,
            email=assignment.email,
            phone=None,
            image=None,
            hire_date=date(2024, 1, 1) + timedelta(days=user.id % 320),
            available_leave_balance_days=assignment.leave_balance,
            department_id=department.id if department is not None else None,
            team_id=team.id if team is not None else None,
            job_title_id=job_title.id,
            is_active=True,
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
        return user, employee

    employee.user_id = user.id
    employee.matricule = assignment.matricule
    employee.first_name = assignment.first_name
    employee.last_name = assignment.last_name
    employee.email = assignment.email
    employee.department_id = department.id if department is not None else None
    employee.team_id = team.id if team is not None else None
    employee.job_title_id = job_title.id
    employee.available_leave_balance_days = assignment.leave_balance
    employee.is_active = True
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return user, employee


def ensure_nfc_card(db: Session, *, employee: Employee, uid: str) -> None:
    existing_card = db.execute(select(NfcCard).where(NfcCard.nfc_uid == uid).limit(1)).scalar_one_or_none()
    if existing_card is None:
        db.add(NfcCard(employee_id=employee.id, nfc_uid=uid, is_active=True))
        db.commit()
        return

    existing_card.employee_id = employee.id
    existing_card.is_active = True
    db.add(existing_card)
    db.commit()


def iter_business_days(count: int) -> list[date]:
    today = date.today()
    days: list[date] = []
    cursor = today - timedelta(days=1)
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()
    return days


def ensure_attendance_seed(
    db: Session,
    *,
    attendance_service: AttendanceService,
    employee: Employee,
    nfc_uid: str,
    day: date,
) -> None:
    existing_summary = db.execute(
        select(AttendanceDailySummary)
        .where(
            AttendanceDailySummary.employee_id == employee.id,
            AttendanceDailySummary.attendance_date == day,
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_summary is not None:
        return

    variability = (employee.id + day.day) % 8
    if variability == 0:
        return

    check_in_at = datetime.combine(day, time(8, 10 + (employee.id % 25)), tzinfo=timezone.utc)
    attendance_service.ingest_nfc_scan_event(
        AttendanceNfcScanIngestRequest(
            nfc_uid=nfc_uid,
            attendance_type=AttendanceEventTypeEnum.CHECK_IN,
            scanned_at=check_in_at,
            source=SEED_SOURCE,
        )
    )

    if variability == 1:
        return

    check_out_at = datetime.combine(day, time(17, 5 + (employee.id % 40)), tzinfo=timezone.utc)
    attendance_service.ingest_nfc_scan_event(
        AttendanceNfcScanIngestRequest(
            nfc_uid=nfc_uid,
            attendance_type=AttendanceEventTypeEnum.CHECK_OUT,
            scanned_at=check_out_at,
            source=SEED_SOURCE,
        )
    )


def ensure_request_type_definitions(
    db: Session,
    *,
    requests_service: RequestsService,
    job_title_by_code: dict[str, JobTitle],
) -> dict[str, RequestType]:
    request_types_by_code: dict[str, RequestType] = {}
    for definition in REQUEST_TYPE_DEFINITIONS:
        request_type = db.execute(
            select(RequestType).where(RequestType.code == definition["code"]).limit(1)
        ).scalar_one_or_none()
        if request_type is None:
            request_type = RequestType(
                code=definition["code"],
                name=definition["name"],
                description=definition["description"],
                is_active=True,
            )
            db.add(request_type)
            db.commit()
            db.refresh(request_type)
        else:
            request_type.name = definition["name"]
            request_type.description = definition["description"]
            request_type.is_active = True
            db.add(request_type)
            db.commit()
            db.refresh(request_type)

        for index, (field_code, label, field_type, is_required) in enumerate(
            definition["fields"], start=1
        ):
            field = db.execute(
                select(RequestTypeField)
                .where(
                    RequestTypeField.request_type_id == request_type.id,
                    RequestTypeField.code == field_code,
                )
                .limit(1)
            ).scalar_one_or_none()
            if field is None:
                field = RequestTypeField(
                    request_type_id=request_type.id,
                    code=field_code,
                    label=label,
                    field_type=field_type.value,
                    is_required=is_required,
                    placeholder=None,
                    help_text=None,
                    default_value=None,
                    sort_order=index,
                    is_active=True,
                )
            else:
                field.label = label
                field.field_type = field_type.value
                field.is_required = is_required
                field.sort_order = index
                field.is_active = True
            db.add(field)
            db.commit()

        for step_order, name, resolver_type, resolver_job_title_code in definition["workflow"]:
            step = db.execute(
                select(RequestWorkflowStep)
                .where(
                    RequestWorkflowStep.request_type_id == request_type.id,
                    RequestWorkflowStep.step_order == step_order,
                )
                .limit(1)
            ).scalar_one_or_none()
            resolver_job_title_id = (
                job_title_by_code[resolver_job_title_code].id
                if resolver_job_title_code is not None
                else None
            )
            if step is None:
                step = RequestWorkflowStep(
                    request_type_id=request_type.id,
                    step_order=step_order,
                    name=name,
                    step_kind=RequestStepKindEnum.APPROVER.value,
                    resolver_type=resolver_type.value if resolver_type is not None else None,
                    resolver_job_title_id=resolver_job_title_id,
                    is_required=True,
                    is_active=True,
                )
            else:
                step.name = name
                step.step_kind = RequestStepKindEnum.APPROVER.value
                step.resolver_type = resolver_type.value if resolver_type is not None else None
                step.resolver_job_title_id = resolver_job_title_id
                step.is_required = True
                step.is_active = True
            db.add(step)
            db.commit()

        request_types_by_code[request_type.code] = request_type

    return request_types_by_code


def build_request_seed_payloads(request_types_by_code: dict[str, RequestType], employees: list[Employee]) -> list[dict[str, object]]:
    regular_employees = [employee for employee in employees if employee.team_id is not None]
    if not regular_employees:
        return []

    payloads: list[dict[str, object]] = []
    business_days = iter_business_days(5)
    for index, employee in enumerate(regular_employees[:18], start=1):
        if index % 3 == 1:
            request_type = request_types_by_code["remote_work_request"]
            values = {
                "work_date": business_days[index % len(business_days)].isoformat(),
                "reason": f"[seed-request-{index:03d}] Focus work from home for delivery preparation.",
            }
            actions = ["approve", "approve"]
        elif index % 3 == 2:
            request_type = request_types_by_code["overtime_request"]
            values = {
                "work_date": business_days[index % len(business_days)].isoformat(),
                "hours": 2 + (index % 3),
                "justification": f"[seed-request-{index:03d}] End-of-month operational support.",
            }
            actions = ["approve"]
        else:
            request_type = request_types_by_code["attendance_adjustment_request"]
            values = {
                "attendance_date": business_days[index % len(business_days)].isoformat(),
                "requested_action": "Correct check-out",
                "reason": f"[seed-request-{index:03d}] Badge scan failed during departure.",
            }
            actions = ["reject"] if index % 6 == 0 else []

        payloads.append(
            {
                "reference": f"seed-request-{index:03d}",
                "employee_id": employee.id,
                "request_type_id": request_type.id,
                "values": values,
                "actions": actions,
            }
        )

    return payloads


def ensure_request_seed(
    db: Session,
    *,
    requests_service: RequestsService,
    payload: dict[str, object],
) -> None:
    existing_request_id = db.execute(
        select(RequestActionHistory.request_id)
        .where(
            RequestActionHistory.action == RequestActionEnum.SUBMITTED.value,
            RequestActionHistory.comment == payload["reference"],
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_request_id is not None:
        return

    employee = db.get(Employee, int(payload["employee_id"]))
    if employee is None:
        return

    requester = db.get(User, employee.user_id)
    if requester is None:
        return

    workflow_request = requests_service.create_request(
        requester,
        RequestCreateRequest(
            request_type_id=int(payload["request_type_id"]),
            values=dict(payload["values"]),
        ),
    )
    submitted_history = db.execute(
        select(RequestActionHistory)
        .where(
            RequestActionHistory.request_id == workflow_request.id,
            RequestActionHistory.action == RequestActionEnum.SUBMITTED.value,
        )
        .order_by(RequestActionHistory.id.asc())
        .limit(1)
    ).scalar_one()
    submitted_history.comment = str(payload["reference"])
    db.add(submitted_history)
    db.commit()

    for action in payload["actions"]:
        db.refresh(workflow_request)
        if workflow_request.current_approver_user_id is None:
            break

        approver = db.get(User, workflow_request.current_approver_user_id)
        if approver is None:
            break

        if action == "approve":
            workflow_request = requests_service.approve_current_step(
                workflow_request.id,
                approver,
                comment=f"{payload['reference']} approved",
            )
        elif action == "reject":
            requests_service.reject_current_step(
                workflow_request.id,
                approver,
                comment=f"{payload['reference']} rejected",
            )
            break


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed a reusable full company dataset with roles, employees, attendance, and requests."
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional database URL override. When omitted, the app environment is used.",
    )
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="Reset seeded account passwords to deterministic values on rerun.",
    )
    args = parser.parse_args()

    engine = create_db_engine(args.database_url, echo=False)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        setup_service = SetupService(db=db, settings=settings)
        setup_service.ensure_canonical_job_titles()
        setup_service.ensure_permission_catalog(
            enforce_wizard_writable=False,
            update_wizard_state=False,
        )
        setup_service.ensure_job_title_permission_assignments(
            enforce_wizard_writable=False,
            update_wizard_state=False,
        )

        department_by_code: dict[str, Department] = {}
        team_by_code: dict[str, Team] = {}
        for department_definition in DEPARTMENTS:
            department = upsert_department(
                db,
                code=department_definition["code"],
                name=department_definition["name"],
                description=department_definition["description"],
            )
            department_by_code[department.code] = department
            for team_code, team_name in department_definition["teams"]:
                team = upsert_team(
                    db,
                    code=team_code,
                    name=team_name,
                    description=f"{team_name} team for {department.name}.",
                    department=department,
                )
                team_by_code[team.code] = team

        job_title_by_code = get_job_titles_by_code(db)
        management_assignments = build_management_assignments()
        employee_assignments = build_employee_assignments()

        created_employees: list[Employee] = []
        seeded_users_by_matricule: dict[str, User] = {}
        seeded_employees_by_matricule: dict[str, Employee] = {}
        for assignment in [*management_assignments, *employee_assignments]:
            user, employee = ensure_user_and_employee(
                db,
                assignment=assignment,
                department_by_code=department_by_code,
                team_by_code=team_by_code,
                job_title_by_code=job_title_by_code,
                reset_passwords=args.reset_passwords,
            )
            seeded_users_by_matricule[user.matricule] = user
            seeded_employees_by_matricule[employee.matricule] = employee
            if not assignment.is_super_admin:
                created_employees.append(employee)

        for department_index, department_definition in enumerate(DEPARTMENTS, start=1):
            department = department_by_code[department_definition["code"]]
            department_manager = seeded_users_by_matricule[f"DM-{department_index:04d}"]
            department.manager_user_id = department_manager.id
            db.add(department)
            for team_index, (team_code, _team_name) in enumerate(department_definition["teams"], start=1):
                team = team_by_code[team_code]
                team_leader = seeded_users_by_matricule[f"TL-{department_index:02d}{team_index:02d}"]
                team.leader_user_id = team_leader.id
                db.add(team)
        db.commit()

        attendance_service = AttendanceService(db=db)
        for employee in created_employees:
            nfc_uid = f"CARD{employee.id:08d}"
            ensure_nfc_card(db, employee=employee, uid=nfc_uid)
            for day in iter_business_days(10):
                ensure_attendance_seed(
                    db,
                    attendance_service=attendance_service,
                    employee=employee,
                    nfc_uid=nfc_uid,
                    day=day,
                )

        if created_employees:
            target_day = iter_business_days(1)[0]
            attendance_service.generate_monthly_reports(
                AttendanceMonthlyReportGenerateRequest(
                    report_year=target_day.year,
                    report_month=target_day.month,
                    include_inactive=False,
                )
            )

        requests_service = RequestsService(db=db)
        request_types_by_code = ensure_request_type_definitions(
            db,
            requests_service=requests_service,
            job_title_by_code=job_title_by_code,
        )
        for payload in build_request_seed_payloads(request_types_by_code, created_employees):
            ensure_request_seed(db, requests_service=requests_service, payload=payload)

    print("Full company dataset seeding completed.")
    print(f"Seeded employees target: {TARGET_EMPLOYEE_COUNT}")
    print(f"Default seeded employee password: {DEFAULT_EMPLOYEE_PASSWORD}")
    print(
        "Bootstrap super admin credentials are read from SUPERADMIN_* environment variables."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
