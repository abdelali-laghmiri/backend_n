from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.apps.admin_panel.dependencies import get_admin_panel_service
from app.apps.admin_panel.schemas import AdminUserCreateRequest, AdminUserUpdateRequest
from app.apps.admin_panel.service import (
    AdminPanelAuthenticationError,
    AdminPanelConflictError,
    AdminPanelNotFoundError,
    AdminPanelService,
    AdminPanelValidationError,
)
from app.apps.attendance.models import AttendanceStatusEnum
from app.apps.attendance.schemas import AttendanceMonthlyReportGenerateRequest
from app.apps.attendance.service import (
    AttendanceConflictError,
    AttendanceNotFoundError,
    AttendanceValidationError,
)
from app.apps.employees.schemas import EmployeeCreateRequest, EmployeeUpdateRequest
from app.apps.employees.service import (
    EmployeesConflictError,
    EmployeesNotFoundError,
    EmployeesValidationError,
)
from app.apps.organization.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    JobTitleCreateRequest,
    JobTitleUpdateRequest,
    TeamCreateRequest,
    TeamUpdateRequest,
)
from app.apps.organization.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationValidationError,
)
from app.apps.permissions.schemas import PermissionCreateRequest, PermissionUpdateRequest
from app.apps.permissions.service import (
    PermissionsConflictError,
    PermissionsNotFoundError,
    PermissionsValidationError,
)
from app.apps.performance.models import TeamObjectiveTypeEnum
from app.apps.performance.schemas import (
    TeamDailyPerformanceCreateRequest,
    TeamObjectiveCreateRequest,
    TeamObjectiveUpdateRequest,
)
from app.apps.performance.service import (
    PerformanceAuthorizationError,
    PerformanceConflictError,
    PerformanceNotFoundError,
    PerformanceValidationError,
)
from app.apps.requests.models import (
    RequestFieldTypeEnum,
    RequestResolverTypeEnum,
    RequestStatusEnum,
    RequestStepKindEnum,
)
from app.apps.requests.schemas import (
    RequestTypeCreateRequest,
    RequestTypeFieldCreateRequest,
    RequestTypeFieldUpdateRequest,
    RequestTypeUpdateRequest,
    RequestWorkflowStepCreateRequest,
    RequestWorkflowStepUpdateRequest,
)
from app.apps.requests.service import (
    RequestsAuthorizationError,
    RequestsConflictError,
    RequestsNotFoundError,
    RequestsValidationError,
)
from app.apps.setup.service import (
    SetupAlreadyInitializedError,
    SetupConfigurationError,
    SetupInitializationError,
    SetupValidationError,
)
from app.apps.users.models import User

router = APIRouter(prefix="/admin", include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))

HANDLED_EXCEPTIONS = (
    AdminPanelAuthenticationError,
    AdminPanelConflictError,
    AdminPanelNotFoundError,
    AdminPanelValidationError,
    AttendanceConflictError,
    AttendanceNotFoundError,
    AttendanceValidationError,
    EmployeesConflictError,
    EmployeesNotFoundError,
    EmployeesValidationError,
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationValidationError,
    PermissionsConflictError,
    PermissionsNotFoundError,
    PermissionsValidationError,
    PerformanceAuthorizationError,
    PerformanceConflictError,
    PerformanceNotFoundError,
    PerformanceValidationError,
    RequestsAuthorizationError,
    RequestsConflictError,
    RequestsNotFoundError,
    RequestsValidationError,
    SetupAlreadyInitializedError,
    SetupConfigurationError,
    SetupInitializationError,
    SetupValidationError,
    ValidationError,
)

NAV_ITEMS = [
    {"label": "Overview", "url": "/admin"},
    {"label": "Setup Wizard", "url": "/admin/setup-wizard"},
    {"label": "Users", "url": "/admin/users"},
    {"label": "Employees", "url": "/admin/employees"},
    {"label": "Departments", "url": "/admin/departments"},
    {"label": "Teams", "url": "/admin/teams"},
    {"label": "Job Titles", "url": "/admin/job-titles"},
    {"label": "Permissions", "url": "/admin/permissions"},
    {"label": "Request Types", "url": "/admin/request-types"},
    {"label": "Request Fields", "url": "/admin/request-fields"},
    {"label": "Request Steps", "url": "/admin/request-steps"},
    {"label": "Requests", "url": "/admin/requests"},
    {"label": "Attendance Daily", "url": "/admin/attendance/daily"},
    {"label": "Attendance Monthly", "url": "/admin/attendance/monthly"},
    {"label": "Performance Objectives", "url": "/admin/performance/objectives"},
    {"label": "Performance Records", "url": "/admin/performance/records"},
]

SETUP_WIZARD_STEPS = [
    {"number": 1, "title": "System Readiness"},
    {"number": 2, "title": "Core Organization"},
    {"number": 3, "title": "Job Titles"},
    {"number": 4, "title": "Permission Catalog"},
    {"number": 5, "title": "Permission Assignment"},
    {"number": 6, "title": "Operational Users"},
    {"number": 7, "title": "Final Review"},
]


def _current_admin(
    request: Request,
    service: AdminPanelService,
) -> User | None:
    return service.resolve_admin_user_from_token(
        request.cookies.get(service.ADMIN_COOKIE_NAME)
    )


def _redirect_to_login(request: Request) -> RedirectResponse:
    next_value = request.url.path
    if request.url.query:
        next_value = f"{next_value}?{request.url.query}"

    return RedirectResponse(
        url=f"/admin/login?{urlencode({'next': next_value})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _redirect_with_message(
    url: str,
    *,
    message: str,
    level: str,
) -> RedirectResponse:
    separator = "&" if "?" in url else "?"
    return RedirectResponse(
        url=f"{url}{separator}{urlencode({'message': message, 'level': level})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _redirect_to_setup_wizard(message: str | None = None) -> RedirectResponse:
    target_url = "/admin/setup-wizard"
    if message is not None:
        return _redirect_with_message(target_url, message=message, level="warning")

    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


def _flash(request: Request) -> dict[str, str | None]:
    return {
        "flash_message": request.query_params.get("message"),
        "flash_level": request.query_params.get("level", "info"),
    }


def _base_context(
    request: Request,
    *,
    current_admin: User | None,
) -> dict[str, object]:
    return {
        "request": request,
        "current_admin": current_admin,
        "nav_items": NAV_ITEMS,
        "current_path": request.url.path,
        **_flash(request),
    }


def _render(
    request: Request,
    template_name: str,
    *,
    current_admin: User | None,
    service: AdminPanelService | None = None,
    **context,
) -> HTMLResponse:
    merged_context = _base_context(request, current_admin=current_admin)
    if current_admin is not None and service is not None:
        merged_context["csrf_token"] = service.create_csrf_token_for_user(current_admin)
        merged_context["installation_snapshot"] = service.get_installation_snapshot()

    merged_context.update(context)
    return templates.TemplateResponse(template_name, merged_context)


def _option(value: object, label: str) -> dict[str, str]:
    return {"value": str(value), "label": label}


def _bool_options() -> list[dict[str, str]]:
    return [_option("true", "Yes"), _option("false", "No")]


def _model_options(items, *, blank_label: str | None, label_getter) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    if blank_label is not None:
        options.append(_option("", blank_label))

    for item in items:
        options.append(_option(item.id, label_getter(item)))

    return options


def _clean(value: object | None, *, blank_to_none: bool = True) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if normalized == "" and blank_to_none:
        return None

    return normalized


def _clean_list(values: list[object]) -> list[str]:
    return [item for item in (_clean(value) for value in values) if item is not None]


def _parse_date_value(value: str | None) -> date | None:
    if value is None or value == "":
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AdminPanelValidationError("Date values must use the YYYY-MM-DD format.") from exc


def _parse_required_date_value(value: str | None, label: str) -> date:
    parsed_value = _parse_date_value(value)
    if parsed_value is None:
        raise AdminPanelValidationError(f"{label} is required.")

    return parsed_value


def _parse_enum(enum_class, value: str | None, label: str):
    if value is None or value == "":
        return None

    try:
        return enum_class(value)
    except ValueError as exc:
        raise AdminPanelValidationError(f"{label} is invalid.") from exc


def _parse_int_value(value: str | None, label: str) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise AdminPanelValidationError(f"{label} must be a valid integer.") from exc


def _field(
    *,
    name: str,
    label: str,
    field_type: str = "text",
    value: object | None = None,
    required: bool = False,
    options: list[dict[str, str]] | None = None,
    help_text: str | None = None,
    rows: int | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "label": label,
        "type": field_type,
        "value": value,
        "required": required,
        "options": options or [],
        "help_text": help_text,
        "rows": rows,
    }


def _table(columns: list[dict[str, str]], rows: list[dict[str, object]]) -> dict[str, object]:
    return {"columns": columns, "rows": rows}


def _get_setup_step(step_number: int) -> dict[str, object]:
    for step in SETUP_WIZARD_STEPS:
        if step["number"] == step_number:
            return step

    raise AdminPanelValidationError("Unknown setup wizard step.")


def _setup_step_url(step_number: int) -> str:
    return f"/admin/setup-wizard/step/{step_number}"


def _build_setup_summary_tables(service: AdminPanelService) -> list[dict[str, object]]:
    review_summary = service.setup_service.get_review_summary()
    organization = review_summary["organization"]
    job_titles = review_summary["job_titles"]["job_titles"]
    permissions = review_summary["permissions"]["permissions"]
    assignments = review_summary["job_title_permissions"]["assignments"]
    operational_users = review_summary["operational_users"]["employees"]

    tables: list[dict[str, object]] = []
    department = organization["department"]
    teams = organization["teams"]
    tables.append(
        _table(
            [
                {"key": "kind", "label": "Record"},
                {"key": "value", "label": "Current value"},
            ],
            [
                {
                    "kind": "Department",
                    "value": f"{department.code} - {department.name}" if department else "Not created",
                    "value_url": f"/admin/departments/{department.id}" if department else None,
                },
                {
                    "kind": "Teams",
                    "value": ", ".join(f"{team.code} - {team.name}" for team in teams) if teams else "Not created",
                },
            ],
        )
    )
    tables.append(
        _table(
            [
                {"key": "code", "label": "Job title code"},
                {"key": "name", "label": "Name"},
            ],
            [
                {
                    "code": job_title.code,
                    "code_url": f"/admin/job-titles/{job_title.id}",
                    "name": job_title.name,
                }
                for job_title in job_titles
            ],
        )
    )
    tables.append(
        _table(
            [
                {"key": "code", "label": "Permission code"},
                {"key": "module", "label": "Module"},
            ],
            [
                {
                    "code": permission.code,
                    "code_url": f"/admin/permissions/{permission.id}",
                    "module": permission.module,
                }
                for permission in permissions
            ],
        )
    )
    tables.append(
        _table(
            [
                {"key": "job_title", "label": "Job title"},
                {"key": "permissions", "label": "Assigned permissions"},
            ],
            [
                {
                    "job_title": job_title_code,
                    "permissions": ", ".join(permission.code for permission in assigned_permissions)
                    if assigned_permissions
                    else "Not assigned",
                }
                for job_title_code, assigned_permissions in assignments.items()
            ],
        )
    )
    tables.append(
        _table(
            [
                {"key": "role", "label": "Role"},
                {"key": "account", "label": "Account"},
                {"key": "team", "label": "Team"},
            ],
            [
                {
                    "role": item["role_label"],
                    "account": (
                        f"{item['user'].matricule} - {item['user'].first_name} {item['user'].last_name}"
                        if item["user"] is not None
                        else "Missing"
                    ),
                    "account_url": (
                        f"/admin/users/{item['user'].id}"
                        if item["user"] is not None
                        else None
                    ),
                    "team": item["team"].name if item["team"] is not None else "-",
                }
                for item in operational_users
            ],
        )
    )
    return tables


@router.get("/login", response_class=HTMLResponse)
def admin_login_page(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
) -> HTMLResponse:
    current_admin = _current_admin(request, service)
    if current_admin is not None:
        if service.setup_service.is_initialized():
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

        return _redirect_to_setup_wizard()

    return templates.TemplateResponse(
        "admin/login.html",
        {
            **_base_context(request, current_admin=None),
            "csrf_token": service.create_login_csrf_token(),
            "next_url": request.query_params.get("next", "/admin"),
        },
    )


@router.post("/login")
async def admin_login_submit(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    form = await request.form()
    next_url = _clean(form.get("next_url"), blank_to_none=False) or "/admin"

    try:
        service.validate_login_csrf_token(_clean(form.get("csrf_token")))
        user = service.authenticate_super_admin(
            matricule=_clean(form.get("matricule"), blank_to_none=False) or "",
            password=_clean(form.get("password"), blank_to_none=False) or "",
        )
    except HANDLED_EXCEPTIONS as exc:
        return templates.TemplateResponse(
            "admin/login.html",
            {
                **_base_context(request, current_admin=None),
                "csrf_token": service.create_login_csrf_token(),
                "next_url": next_url,
                "flash_message": str(exc),
                "flash_level": "danger",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    token, max_age = service.create_admin_access_token_for_user(user)
    response = RedirectResponse(
        url=(
            "/admin"
            if service.setup_service.is_initialized()
            else "/admin/setup-wizard"
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    if service.setup_service.is_initialized():
        response = RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=service.ADMIN_COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=max_age,
        httponly=True,
        secure=not service.settings.debug,
        samesite="lax",
        path="/admin",
    )
    return response


@router.get("/logout")
def admin_logout(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(service.ADMIN_COOKIE_NAME, path="/admin")
    return response


@router.get("", response_class=HTMLResponse)
def admin_overview(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    if not service.setup_service.is_initialized():
        return _redirect_to_setup_wizard(
            "Finish the setup wizard before using the rest of the admin dashboard."
        )

    overview_data = service.get_overview(current_admin)
    return _render(
        request,
        "admin/overview.html",
        current_admin=current_admin,
        service=service,
        page_title="Admin Overview",
        overview_data=overview_data,
    )


def _render_setup_wizard_page(
    request: Request,
    *,
    service: AdminPanelService,
    current_admin: User,
    step_number: int,
) -> HTMLResponse:
    setup_service = service.setup_service
    installation_snapshot = service.get_installation_snapshot()
    read_only = installation_snapshot["initialized"]
    setup_step = _get_setup_step(step_number)
    step_form: dict[str, object] | None = None
    supporting_tables: list[dict[str, object]] = []

    if step_number == 1:
        readiness = setup_service.get_readiness_summary()
        supporting_tables.append(
            _table(
                [
                    {"key": "item", "label": "Item"},
                    {"key": "status", "label": "Status"},
                ],
                [
                    {"item": "Database connectivity", "status": "Ready" if readiness["database_ready"] else "Pending"},
                    {"item": "Migration status assumption", "status": "Ready" if readiness["migrations_ready"] else "Pending"},
                    {
                        "item": "Bootstrap super admin",
                        "status": (
                            f"{readiness['super_admin'].matricule} is available"
                            if readiness["super_admin"] is not None
                            else "Not created yet"
                        ),
                    },
                    {
                        "item": "Installation state",
                        "status": "Completed" if readiness["initialized"] else "Pending",
                    },
                ],
            )
        )
        if not read_only:
            step_form = {
                "action": _setup_step_url(1),
                "submit_label": "Continue to organization setup",
                "title": "Acknowledge readiness",
                "description": "The wizard will create the minimum initial data required for the system to start operating safely.",
                "fields": [],
            }
    elif step_number == 2:
        organization_summary = setup_service.get_organization_summary()
        department = organization_summary["department"]
        teams = organization_summary["teams"]
        supporting_tables.append(
            _table(
                [
                    {"key": "kind", "label": "Record"},
                    {"key": "value", "label": "Current value"},
                ],
                [
                    {
                        "kind": "Department",
                        "value": f"{department.code} - {department.name}" if department else "Not created",
                        "value_url": f"/admin/departments/{department.id}" if department else None,
                    },
                    {
                        "kind": "Teams",
                        "value": ", ".join(f"{team.code} - {team.name}" for team in teams) if teams else "Not created",
                    },
                ],
            )
        )
        if not read_only:
            step_form = {
                "action": _setup_step_url(2),
                "submit_label": "Save organization and continue",
                "title": "Create the first department and two teams",
                "description": "These records become the base structure used by employees, attendance, performance, and workflow routing.",
                "fields": [
                    _field(name="department_name", label="Department name", value=department.name if department else "Human Resources", required=True),
                    _field(name="department_code", label="Department code", value=department.code if department else "HR", required=True),
                    _field(name="department_description", label="Department description", field_type="textarea", value=department.description if department else "Initial operational department created by the setup wizard."),
                    _field(name="team_one_name", label="Team 1 name", value=teams[0].name if len(teams) > 0 else "Operations Team", required=True),
                    _field(name="team_one_code", label="Team 1 code", value=teams[0].code if len(teams) > 0 else "OPS", required=True),
                    _field(name="team_one_description", label="Team 1 description", field_type="textarea", value=teams[0].description if len(teams) > 0 else "First operational team."),
                    _field(name="team_two_name", label="Team 2 name", value=teams[1].name if len(teams) > 1 else "Support Team", required=True),
                    _field(name="team_two_code", label="Team 2 code", value=teams[1].code if len(teams) > 1 else "SUPPORT", required=True),
                    _field(name="team_two_description", label="Team 2 description", field_type="textarea", value=teams[1].description if len(teams) > 1 else "Second operational team."),
                ],
            }
    elif step_number == 3:
        job_titles_summary = setup_service.get_job_titles_summary()["job_titles"]
        job_title_map = {item.code: item for item in job_titles_summary}
        supporting_tables.append(
            _table(
                [
                    {"key": "code", "label": "Code"},
                    {"key": "name", "label": "Name"},
                    {"key": "level", "label": "Level"},
                ],
                [
                    {
                        "code": job_title.code,
                        "code_url": f"/admin/job-titles/{job_title.id}",
                        "name": job_title.name,
                        "level": job_title.hierarchical_level,
                    }
                    for job_title in job_titles_summary
                ],
            )
        )
        if not read_only:
            fields: list[dict[str, object]] = []
            for definition in setup_service.DEFAULT_JOB_TITLES:
                current_job_title = job_title_map.get(definition["code"])
                fields.extend(
                    [
                        _field(name=f"{definition['key']}_name", label=f"{definition['name']} label", value=current_job_title.name if current_job_title else definition["name"], required=True),
                        _field(name=f"{definition['key']}_hierarchical_level", label=f"{definition['name']} hierarchy level", field_type="number", value=str(current_job_title.hierarchical_level) if current_job_title else str(definition["hierarchical_level"]), required=True),
                        _field(name=f"{definition['key']}_description", label=f"{definition['name']} description", field_type="textarea", value=current_job_title.description if current_job_title else definition["description"]),
                    ]
                )
            step_form = {
                "action": _setup_step_url(3),
                "submit_label": "Save job titles and continue",
                "title": "Seed the initial job-title catalog",
                "description": "Codes stay aligned with backend workflow logic. You can still adjust the display names, hierarchy levels, and descriptions.",
                "fields": fields,
            }
    elif step_number == 4:
        permissions_summary = setup_service.get_permissions_summary()
        supporting_tables.append(
            _table(
                [
                    {"key": "code", "label": "Permission code"},
                    {"key": "module", "label": "Module"},
                ],
                [
                    {"code": definition["code"], "module": definition["module"]}
                    for definition in setup_service.DEFAULT_PERMISSIONS
                ],
            )
        )
        supporting_tables.append(
            _table(
                [
                    {"key": "item", "label": "Catalog state"},
                    {"key": "value", "label": "Value"},
                ],
                [
                    {"item": "Expected permissions", "value": permissions_summary["expected_count"]},
                    {"item": "Stored permissions", "value": len(permissions_summary["permissions"])},
                ],
            )
        )
        if not read_only:
            step_form = {
                "action": _setup_step_url(4),
                "submit_label": "Create permission catalog",
                "title": "Store the permission catalog in the database",
                "description": "These permission codes back the reusable authorization checks and job-title mappings used by the backend.",
                "fields": [],
            }
    elif step_number == 5:
        assignment_summary = setup_service.get_job_title_permission_summary()["assignments"]
        supporting_tables.append(
            _table(
                [
                    {"key": "job_title", "label": "Job title"},
                    {"key": "permissions", "label": "Target permissions"},
                ],
                [
                    {
                        "job_title": job_title_code,
                        "permissions": ", ".join(
                            permission.code for permission in assignment_summary.get(job_title_code, [])
                        ) or "Not assigned",
                    }
                    for job_title_code in setup_service.DEFAULT_JOB_TITLE_PERMISSION_CODES
                ],
            )
        )
        if not read_only:
            step_form = {
                "action": _setup_step_url(5),
                "submit_label": "Apply job-title permission mapping",
                "title": "Assign permissions to seeded job titles",
                "description": "Normal users inherit their effective access from the permissions assigned to their job title. Super admin still bypasses these checks.",
                "fields": [],
            }
    elif step_number == 6:
        organization_summary = setup_service.get_organization_summary()
        teams = organization_summary["teams"]
        operational_users = setup_service.get_operational_users_summary()["employees"]
        operational_map = {item["role_label"]: item for item in operational_users}
        fields = []
        for role_config in setup_service.OPERATIONAL_ROLE_CONFIGS:
            current_item = operational_map.get(role_config["label"])
            current_employee = current_item["employee"] if current_item is not None else None
            current_user = current_item["user"] if current_item is not None else None
            team_name = "-"
            if role_config["team_index"] is not None and len(teams) > role_config["team_index"]:
                team_name = teams[role_config["team_index"]].name
            help_text = "Must change password on first login."
            if role_config["team_index"] is not None:
                help_text = f"Assigned to {team_name}. Must change password on first login."
            fields.extend(
                [
                    _field(name=f"{role_config['key']}_matricule", label=f"{role_config['label']} matricule", value=current_user.matricule if current_user else "", required=True),
                    _field(name=f"{role_config['key']}_first_name", label=f"{role_config['label']} first name", value=current_user.first_name if current_user else "", required=True),
                    _field(name=f"{role_config['key']}_last_name", label=f"{role_config['label']} last name", value=current_user.last_name if current_user else "", required=True),
                    _field(name=f"{role_config['key']}_email", label=f"{role_config['label']} email", field_type="email", value=current_user.email if current_user else "", required=True),
                    _field(name=f"{role_config['key']}_password", label=f"{role_config['label']} password", field_type="password", value="", required=current_user is None, help_text=help_text),
                    _field(name=f"{role_config['key']}_hire_date", label=f"{role_config['label']} hire date", field_type="date", value=str(current_employee.hire_date) if current_employee else str(date.today()), required=True),
                ]
            )
        supporting_tables.append(
            _table(
                [
                    {"key": "role", "label": "Role"},
                    {"key": "account", "label": "Current account"},
                    {"key": "team", "label": "Team"},
                ],
                [
                    {
                        "role": item["role_label"],
                        "account": f"{item['user'].matricule} - {item['user'].first_name} {item['user'].last_name}" if item["user"] is not None else "Missing",
                        "account_url": f"/admin/users/{item['user'].id}" if item["user"] is not None else None,
                        "team": item["team"].name if item["team"] is not None else "-",
                    }
                    for item in operational_users
                ],
            )
        )
        if not read_only:
            step_form = {
                "action": _setup_step_url(6),
                "submit_label": "Create operational users and continue",
                "title": "Create the initial operational users",
                "description": "The wizard creates employee profiles and linked accounts, keeps them active, and forces a password change on the first login.",
                "fields": fields,
            }
    else:
        review_summary = setup_service.get_review_summary()
        supporting_tables = _build_setup_summary_tables(service)
        supporting_tables.append(
            _table(
                [
                    {"key": "item", "label": "Validation"},
                    {"key": "value", "label": "Result"},
                ],
                [
                    {"item": "Ready to complete installation", "value": "Yes" if review_summary["is_ready"] else "No"},
                    {
                        "item": "Missing items",
                        "value": ", ".join(review_summary["missing_items"]) if review_summary["missing_items"] else "None",
                    },
                ],
            )
        )
        if not read_only:
            step_form = {
                "action": "/admin/setup-wizard/finish",
                "submit_label": "Complete installation",
                "title": "Review and lock the installation",
                "description": "Initialization becomes true only after this final validation succeeds and the installation state is stored in the main database.",
                "confirm": "Complete the installation and lock the setup wizard?",
                "fields": [],
            }

    return _render(
        request,
        "admin/setup_wizard.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Setup Wizard: {setup_step['title']}",
        page_description="Complete the first-installation flow through safe application-level operations.",
        wizard_steps=SETUP_WIZARD_STEPS,
        wizard_current_step=step_number,
        wizard_step_title=setup_step["title"],
        wizard_form=step_form,
        wizard_tables=supporting_tables,
        wizard_read_only=read_only,
        wizard_previous_url=_setup_step_url(step_number - 1) if step_number > 1 else None,
        wizard_next_url=_setup_step_url(step_number + 1) if step_number < 7 else None,
    )


@router.get("/setup-wizard", response_class=HTMLResponse)
def admin_setup_wizard(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    return RedirectResponse(
        url=_setup_step_url(service.setup_service.get_next_wizard_step_number()),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/setup-wizard/step/{step_number}", response_class=HTMLResponse)
def admin_setup_wizard_step(
    step_number: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        _get_setup_step(step_number)
    except AdminPanelValidationError as exc:
        return _redirect_with_message("/admin/setup-wizard", message=str(exc), level="danger")

    return _render_setup_wizard_page(
        request,
        service=service,
        current_admin=current_admin,
        step_number=step_number,
    )


@router.post("/setup-wizard/step/{step_number}")
async def admin_setup_wizard_step_submit(
    step_number: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        _get_setup_step(step_number)
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)

        if step_number == 1:
            service.setup_service.save_readiness_step()
        elif step_number == 2:
            service.setup_service.save_organization_step(
                {
                    "department_name": _clean(form.get("department_name"), blank_to_none=False),
                    "department_code": _clean(form.get("department_code"), blank_to_none=False),
                    "department_description": _clean(form.get("department_description")),
                    "team_one_name": _clean(form.get("team_one_name"), blank_to_none=False),
                    "team_one_code": _clean(form.get("team_one_code"), blank_to_none=False),
                    "team_one_description": _clean(form.get("team_one_description")),
                    "team_two_name": _clean(form.get("team_two_name"), blank_to_none=False),
                    "team_two_code": _clean(form.get("team_two_code"), blank_to_none=False),
                    "team_two_description": _clean(form.get("team_two_description")),
                }
            )
        elif step_number == 3:
            payload: dict[str, object] = {}
            for definition in service.setup_service.DEFAULT_JOB_TITLES:
                key = definition["key"]
                payload[f"{key}_name"] = _clean(form.get(f"{key}_name"), blank_to_none=False)
                payload[f"{key}_description"] = _clean(form.get(f"{key}_description"))
                payload[f"{key}_hierarchical_level"] = _parse_int_value(
                    _clean(form.get(f"{key}_hierarchical_level"), blank_to_none=False),
                    f"{definition['name']} hierarchy level",
                )
            service.setup_service.save_job_titles_step(payload)
        elif step_number == 4:
            service.setup_service.ensure_permission_catalog()
        elif step_number == 5:
            service.setup_service.ensure_job_title_permission_assignments()
        elif step_number == 6:
            payload = {}
            for role_config in service.setup_service.OPERATIONAL_ROLE_CONFIGS:
                role_key = role_config["key"]
                payload[role_key] = {
                    "matricule": _clean(form.get(f"{role_key}_matricule"), blank_to_none=False),
                    "first_name": _clean(form.get(f"{role_key}_first_name"), blank_to_none=False),
                    "last_name": _clean(form.get(f"{role_key}_last_name"), blank_to_none=False),
                    "email": _clean(form.get(f"{role_key}_email"), blank_to_none=False),
                    "password": _clean(form.get(f"{role_key}_password")),
                    "hire_date": _parse_required_date_value(
                        _clean(form.get(f"{role_key}_hire_date"), blank_to_none=False),
                        f"{role_config['label']} hire date",
                    ),
                }
            service.setup_service.save_operational_users_step(payload)
        else:
            return _redirect_with_message(
                "/admin/setup-wizard/step/7",
                message="Use the final completion button on the review step.",
                level="warning",
            )
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(
            _setup_step_url(step_number),
            message=str(exc),
            level="danger",
        )

    return RedirectResponse(
        url=_setup_step_url(min(step_number + 1, 7)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/setup-wizard/finish")
async def admin_setup_wizard_finish(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        service.setup_service.complete_installation(current_admin)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(
            "/admin/setup-wizard/step/7",
            message=str(exc),
            level="danger",
        )

    return _redirect_with_message(
        "/admin",
        message="Installation completed successfully. The setup state is now locked.",
        level="success",
    )


def _render_users_page(
    request: Request,
    *,
    service: AdminPanelService,
    current_admin: User,
) -> HTMLResponse:
    q = request.query_params.get("q")
    include_inactive = request.query_params.get("include_inactive") == "true"
    users = service.list_users(q=q, include_inactive=include_inactive, limit=200)
    rows = []
    for user in users:
        linked_employee = service.get_linked_employee_by_user_id(user.id)
        rows.append(
            {
                "id": user.id,
                "matricule": user.matricule,
                "matricule_url": f"/admin/users/{user.id}",
                "name": service.build_user_name(user),
                "email": user.email,
                "super_admin": "Yes" if user.is_super_admin else "No",
                "active": "Yes" if user.is_active else "No",
                "employee": linked_employee.matricule if linked_employee is not None else "No",
            }
        )

    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Users",
        page_description="Inspect and manage internal user accounts. Employee-linked identities stay synchronized when edited here.",
        filters_form={
            "action": "/admin/users",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(name="q", label="Search", value=q),
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/users",
            "submit_label": "Create user",
            "title": "Create User",
            "fields": [
                _field(name="matricule", label="Matricule", required=True),
                _field(name="first_name", label="First name", required=True),
                _field(name="last_name", label="Last name", required=True),
                _field(name="email", label="Email", field_type="email", required=True),
                _field(name="password", label="Password", field_type="password", required=True),
                _field(
                    name="is_super_admin",
                    label="Super admin",
                    field_type="select",
                    value="false",
                    options=_bool_options(),
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true",
                    options=_bool_options(),
                ),
                _field(
                    name="must_change_password",
                    label="Must change password",
                    field_type="select",
                    value="true",
                    options=_bool_options(),
                ),
            ],
        },
        table=_table(
            [
                {"key": "id", "label": "ID"},
                {"key": "matricule", "label": "Matricule"},
                {"key": "name", "label": "Name"},
                {"key": "email", "label": "Email"},
                {"key": "super_admin", "label": "Super Admin"},
                {"key": "active", "label": "Active"},
                {"key": "employee", "label": "Linked Employee"},
            ],
            rows,
        ),
    )


@router.get("/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    return _render_users_page(request, service=service, current_admin=current_admin)


@router.post("/users")
async def admin_users_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = AdminUserCreateRequest(
            matricule=_clean(form.get("matricule"), blank_to_none=False),
            first_name=_clean(form.get("first_name"), blank_to_none=False),
            last_name=_clean(form.get("last_name"), blank_to_none=False),
            email=_clean(form.get("email"), blank_to_none=False),
            password=_clean(form.get("password"), blank_to_none=False),
            is_super_admin=_clean(form.get("is_super_admin"), blank_to_none=False),
            is_active=_clean(form.get("is_active"), blank_to_none=False),
            must_change_password=_clean(
                form.get("must_change_password"),
                blank_to_none=False,
            ),
        )
        created_user = service.create_user(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/users", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/users/{created_user.id}",
        message="User account created successfully.",
        level="success",
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
def admin_user_detail(
    user_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        user = service.get_user(user_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/users", message=str(exc), level="danger")

    linked_employee = service.get_linked_employee_by_user_id(user.id)
    led_teams = [team for team in service.list_lookup_teams(include_inactive=True) if team.leader_user_id == user.id]
    managed_departments = [
        department
        for department in service.list_lookup_departments(include_inactive=True)
        if department.manager_user_id == user.id
    ]
    permissions = service.permissions_service.resolve_effective_permissions(user)

    related_tables = [
        _table(
            [{"key": "code", "label": "Department"}],
            [
                {
                    "code": f"{department.code} - {department.name}",
                    "code_url": f"/admin/departments/{department.id}",
                }
                for department in managed_departments
            ],
        ),
        _table(
            [{"key": "code", "label": "Team"}],
            [
                {"code": f"{team.code} - {team.name}", "code_url": f"/admin/teams/{team.id}"}
                for team in led_teams
            ],
        ),
        _table(
            [{"key": "code", "label": "Effective permission"}],
            [{"code": permission_code} for permission_code in permissions.permissions]
            if not permissions.has_full_access
            else [{"code": "Full access"}],
        ),
    ]
    if linked_employee is not None:
        related_tables.insert(
            0,
            _table(
                [{"key": "employee", "label": "Linked employee"}],
                [
                    {
                        "employee": f"{linked_employee.matricule} - {service.build_employee_name(linked_employee)}",
                        "employee_url": f"/admin/employees/{linked_employee.id}",
                    }
                ],
            ),
        )

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"User {user.matricule}",
        page_description="Manage the internal account and review linked business assignments.",
        back_url="/admin/users",
        detail_fields=[
            {"label": "ID", "value": user.id},
            {"label": "Matricule", "value": user.matricule},
            {"label": "Name", "value": service.build_user_name(user)},
            {"label": "Email", "value": user.email},
            {"label": "Super admin", "value": "Yes" if user.is_super_admin else "No"},
            {"label": "Active", "value": "Yes" if user.is_active else "No"},
            {
                "label": "Must change password",
                "value": "Yes" if user.must_change_password else "No",
            },
            {"label": "Created at", "value": user.created_at},
            {"label": "Updated at", "value": user.updated_at},
        ],
        edit_form={
            "action": f"/admin/users/{user.id}",
            "submit_label": "Update user",
            "title": "Edit User",
            "fields": [
                _field(name="matricule", label="Matricule", value=user.matricule, required=True),
                _field(name="first_name", label="First name", value=user.first_name, required=True),
                _field(name="last_name", label="Last name", value=user.last_name, required=True),
                _field(name="email", label="Email", field_type="email", value=user.email, required=True),
                _field(
                    name="password",
                    label="New password",
                    field_type="password",
                    help_text="Leave blank to keep the current password.",
                ),
                _field(
                    name="is_super_admin",
                    label="Super admin",
                    field_type="select",
                    value="true" if user.is_super_admin else "false",
                    options=_bool_options(),
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if user.is_active else "false",
                    options=_bool_options(),
                ),
                _field(
                    name="must_change_password",
                    label="Must change password",
                    field_type="select",
                    value="true" if user.must_change_password else "false",
                    options=_bool_options(),
                ),
            ],
        },
        related_tables=related_tables,
    )


@router.post("/users/{user_id}")
async def admin_user_update(
    user_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = AdminUserUpdateRequest(
            matricule=_clean(form.get("matricule")),
            first_name=_clean(form.get("first_name")),
            last_name=_clean(form.get("last_name")),
            email=_clean(form.get("email")),
            password=_clean(form.get("password")),
            is_super_admin=_clean(form.get("is_super_admin")),
            is_active=_clean(form.get("is_active")),
            must_change_password=_clean(form.get("must_change_password")),
        )
        service.update_user(user_id, payload, current_admin=current_admin)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(
            f"/admin/users/{user_id}",
            message=str(exc),
            level="danger",
        )

    return _redirect_with_message(
        f"/admin/users/{user_id}",
        message="User account updated successfully.",
        level="success",
    )


def _render_employees_page(
    request: Request,
    *,
    service: AdminPanelService,
    current_admin: User,
    created_account: dict[str, object] | None = None,
) -> HTMLResponse:
    q = request.query_params.get("q")
    include_inactive = request.query_params.get("include_inactive") == "true"
    department_id = request.query_params.get("department_id")
    team_id = request.query_params.get("team_id")
    job_title_id = request.query_params.get("job_title_id")
    departments = service.list_lookup_departments(include_inactive=True)
    teams = service.list_lookup_teams(include_inactive=True)
    job_titles = service.list_lookup_job_titles(include_inactive=True)
    employees = service.list_employees(
        include_inactive=include_inactive,
        q=q,
        department_id=_parse_int_value(department_id, "Department"),
        team_id=_parse_int_value(team_id, "Team"),
        job_title_id=_parse_int_value(job_title_id, "Job title"),
    )
    department_map = {item.id: item for item in departments}
    team_map = {item.id: item for item in teams}
    job_title_map = {item.id: item for item in job_titles}

    rows = []
    for employee in employees:
        department = department_map.get(employee.department_id)
        team = team_map.get(employee.team_id)
        job_title = job_title_map.get(employee.job_title_id)
        rows.append(
            {
                "matricule": employee.matricule,
                "matricule_url": f"/admin/employees/{employee.id}",
                "name": service.build_employee_name(employee),
                "department": department.name if department is not None else "-",
                "team": team.name if team is not None else "-",
                "job_title": job_title.name if job_title is not None else "-",
                "leave_balance": employee.available_leave_balance_days,
                "active": "Yes" if employee.is_active else "No",
            }
        )

    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Employees",
        page_description="Manage employee records and the linked authentication accounts created by the employees module.",
        filters_form={
            "action": "/admin/employees",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(name="q", label="Search", value=q),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value=department_id or "",
                    options=_model_options(
                        departments,
                        blank_label="All departments",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    options=_model_options(
                        teams,
                        blank_label="All teams",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="job_title_id",
                    label="Job title",
                    field_type="select",
                    value=job_title_id or "",
                    options=_model_options(
                        job_titles,
                        blank_label="All job titles",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/employees",
            "submit_label": "Create employee",
            "title": "Create Employee",
            "fields": [
                _field(name="matricule", label="Matricule", required=True),
                _field(name="first_name", label="First name", required=True),
                _field(name="last_name", label="Last name", required=True),
                _field(name="email", label="Email", field_type="email", required=True),
                _field(name="phone", label="Phone"),
                _field(name="hire_date", label="Hire date", field_type="date", required=True),
                _field(
                    name="available_leave_balance_days",
                    label="Leave balance days",
                    field_type="number",
                    value="0",
                    required=True,
                ),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value="",
                    options=_model_options(
                        departments,
                        blank_label="No department",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value="",
                    options=_model_options(
                        teams,
                        blank_label="No team",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="job_title_id",
                    label="Job title",
                    field_type="select",
                    value="",
                    required=True,
                    options=_model_options(
                        job_titles,
                        blank_label="Select job title",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
            ],
        },
        table=_table(
            [
                {"key": "matricule", "label": "Matricule"},
                {"key": "name", "label": "Name"},
                {"key": "department", "label": "Department"},
                {"key": "team", "label": "Team"},
                {"key": "job_title", "label": "Job Title"},
                {"key": "leave_balance", "label": "Leave Balance"},
                {"key": "active", "label": "Active"},
            ],
            rows,
        ),
        success_panel=created_account,
    )


@router.get("/employees", response_class=HTMLResponse)
def admin_employees(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    return _render_employees_page(request, service=service, current_admin=current_admin)


@router.post("/employees")
async def admin_employees_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = EmployeeCreateRequest(
            matricule=_clean(form.get("matricule"), blank_to_none=False),
            first_name=_clean(form.get("first_name"), blank_to_none=False),
            last_name=_clean(form.get("last_name"), blank_to_none=False),
            email=_clean(form.get("email"), blank_to_none=False),
            phone=_clean(form.get("phone")),
            hire_date=_clean(form.get("hire_date"), blank_to_none=False),
            available_leave_balance_days=_clean(
                form.get("available_leave_balance_days"),
                blank_to_none=False,
            ),
            department_id=_clean(form.get("department_id")),
            team_id=_clean(form.get("team_id")),
            job_title_id=_clean(form.get("job_title_id"), blank_to_none=False),
        )
        employee, temporary_password = service.create_employee(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/employees", message=str(exc), level="danger")

    return _render_employees_page(
        request,
        service=service,
        current_admin=current_admin,
        created_account={
            "title": "Employee created successfully",
            "lines": [
                f"Employee: {employee.matricule} - {service.build_employee_name(employee)}",
                f"Linked user id: {employee.user_id}",
                f"Temporary password: {temporary_password}",
                "This password is shown only in this response. Ask the user to change it at first login.",
            ],
        },
    )


@router.get("/employees/{employee_id}", response_class=HTMLResponse)
def admin_employee_detail(
    employee_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        employee = service.get_employee(employee_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/employees", message=str(exc), level="danger")

    user = service.get_user(employee.user_id)
    departments = service.list_lookup_departments(include_inactive=True)
    teams = service.list_lookup_teams(include_inactive=True)
    job_titles = service.list_lookup_job_titles(include_inactive=True)
    department_map = {item.id: item for item in departments}
    team_map = {item.id: item for item in teams}
    job_title_map = {item.id: item for item in job_titles}
    recent_attendance = service.get_recent_employee_attendance(employee.id)
    recent_requests = service.get_recent_employee_requests(employee.id)

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Employee {employee.matricule}",
        page_description="Inspect the personnel record and keep the linked login account synchronized through employee-safe updates.",
        back_url="/admin/employees",
        detail_fields=[
            {"label": "Matricule", "value": employee.matricule},
            {"label": "Name", "value": service.build_employee_name(employee)},
            {"label": "Email", "value": employee.email},
            {"label": "Phone", "value": employee.phone or "-"},
            {"label": "Hire date", "value": employee.hire_date},
            {"label": "Leave balance days", "value": employee.available_leave_balance_days},
            {
                "label": "Department",
                "value": department_map[employee.department_id].name if employee.department_id in department_map else "-",
            },
            {
                "label": "Team",
                "value": team_map[employee.team_id].name if employee.team_id in team_map else "-",
            },
            {
                "label": "Job title",
                "value": job_title_map[employee.job_title_id].name if employee.job_title_id in job_title_map else "-",
            },
            {"label": "Active", "value": "Yes" if employee.is_active else "No"},
            {"label": "Linked user", "value": f"{user.matricule} - {service.build_user_name(user)}"},
            {"label": "Created at", "value": employee.created_at},
            {"label": "Updated at", "value": employee.updated_at},
        ],
        edit_form={
            "action": f"/admin/employees/{employee.id}",
            "submit_label": "Update employee",
            "title": "Edit Employee",
            "fields": [
                _field(name="matricule", label="Matricule", value=employee.matricule, required=True),
                _field(name="first_name", label="First name", value=employee.first_name, required=True),
                _field(name="last_name", label="Last name", value=employee.last_name, required=True),
                _field(name="email", label="Email", field_type="email", value=employee.email, required=True),
                _field(name="phone", label="Phone", value=employee.phone or ""),
                _field(name="hire_date", label="Hire date", field_type="date", value=str(employee.hire_date), required=True),
                _field(
                    name="available_leave_balance_days",
                    label="Leave balance days",
                    field_type="number",
                    value=str(employee.available_leave_balance_days),
                    required=True,
                ),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value=str(employee.department_id or ""),
                    options=_model_options(
                        departments,
                        blank_label="No department",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=str(employee.team_id or ""),
                    options=_model_options(
                        teams,
                        blank_label="No team",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="job_title_id",
                    label="Job title",
                    field_type="select",
                    value=str(employee.job_title_id),
                    required=True,
                    options=_model_options(
                        job_titles,
                        blank_label="Select job title",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if employee.is_active else "false",
                    options=_bool_options(),
                ),
            ],
        },
        related_tables=[
            _table(
                [
                    {"key": "attendance_date", "label": "Attendance date"},
                    {"key": "status", "label": "Status"},
                    {"key": "worked", "label": "Worked minutes"},
                ],
                [
                    {
                        "attendance_date": str(summary.attendance_date),
                        "attendance_date_url": f"/admin/attendance/daily/{summary.id}",
                        "status": summary.status,
                        "worked": summary.worked_duration_minutes if summary.worked_duration_minutes is not None else "-",
                    }
                    for summary in recent_attendance
                ],
            ),
            _table(
                [
                    {"key": "request_id", "label": "Request"},
                    {"key": "status", "label": "Status"},
                    {"key": "submitted_at", "label": "Submitted at"},
                ],
                [
                    {
                        "request_id": request_item.id,
                        "request_id_url": f"/admin/requests/{request_item.id}",
                        "status": request_item.status,
                        "submitted_at": request_item.submitted_at,
                    }
                    for request_item in recent_requests
                ],
            ),
        ],
    )


@router.post("/employees/{employee_id}")
async def admin_employee_update(
    employee_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = EmployeeUpdateRequest(
            matricule=_clean(form.get("matricule")),
            first_name=_clean(form.get("first_name")),
            last_name=_clean(form.get("last_name")),
            email=_clean(form.get("email")),
            phone=_clean(form.get("phone")),
            hire_date=_clean(form.get("hire_date")),
            available_leave_balance_days=_clean(form.get("available_leave_balance_days")),
            department_id=_clean(form.get("department_id")),
            team_id=_clean(form.get("team_id")),
            job_title_id=_clean(form.get("job_title_id")),
            is_active=_clean(form.get("is_active")),
        )
        service.update_employee(employee_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(
            f"/admin/employees/{employee_id}",
            message=str(exc),
            level="danger",
        )

    return _redirect_with_message(
        f"/admin/employees/{employee_id}",
        message="Employee updated successfully.",
        level="success",
    )


@router.get("/departments", response_class=HTMLResponse)
def admin_departments(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    departments = service.list_departments(include_inactive=include_inactive)
    users = service.list_lookup_users(include_inactive=True)
    user_map = {user.id: user for user in users}
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Departments",
        page_description="Manage departments and inspect the managers, teams, and employees assigned to them.",
        filters_form={
            "action": "/admin/departments",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                )
            ],
        },
        create_form={
            "action": "/admin/departments",
            "submit_label": "Create department",
            "title": "Create Department",
            "fields": [
                _field(name="name", label="Name", required=True),
                _field(name="code", label="Code", required=True),
                _field(name="description", label="Description", field_type="textarea", rows=3),
                _field(
                    name="manager_user_id",
                    label="Manager",
                    field_type="select",
                    value="",
                    options=_model_options(
                        users,
                        blank_label="No manager",
                        label_getter=lambda item: f"{item.matricule} - {service.build_user_name(item)}",
                    ),
                ),
            ],
        },
        table=_table(
            [
                {"key": "code", "label": "Code"},
                {"key": "name", "label": "Name"},
                {"key": "manager", "label": "Manager"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "code": department.code,
                    "code_url": f"/admin/departments/{department.id}",
                    "name": department.name,
                    "manager": service.build_user_name(user_map[department.manager_user_id])
                    if department.manager_user_id in user_map
                    else "-",
                    "active": "Yes" if department.is_active else "No",
                }
                for department in departments
            ],
        ),
    )


@router.post("/departments")
async def admin_departments_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = DepartmentCreateRequest(
            name=_clean(form.get("name"), blank_to_none=False),
            code=_clean(form.get("code"), blank_to_none=False),
            description=_clean(form.get("description")),
            manager_user_id=_clean(form.get("manager_user_id")),
        )
        created_department = service.create_department(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/departments", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/departments/{created_department.id}",
        message="Department created successfully.",
        level="success",
    )


@router.get("/departments/{department_id}", response_class=HTMLResponse)
def admin_department_detail(
    department_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        department = service.get_department(department_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/departments", message=str(exc), level="danger")

    users = service.list_lookup_users(include_inactive=True)
    manager_map = {user.id: user for user in users}
    teams = service.get_department_teams(department.id)
    employees = service.get_department_employees(department.id)
    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Department {department.code}",
        page_description="Update department metadata and inspect dependent teams and employees.",
        back_url="/admin/departments",
        detail_fields=[
            {"label": "Code", "value": department.code},
            {"label": "Name", "value": department.name},
            {"label": "Description", "value": department.description or "-"},
            {
                "label": "Manager",
                "value": service.build_user_name(manager_map[department.manager_user_id])
                if department.manager_user_id in manager_map
                else "-",
            },
            {"label": "Active", "value": "Yes" if department.is_active else "No"},
            {"label": "Created at", "value": department.created_at},
            {"label": "Updated at", "value": department.updated_at},
        ],
        edit_form={
            "action": f"/admin/departments/{department.id}",
            "submit_label": "Update department",
            "title": "Edit Department",
            "fields": [
                _field(name="name", label="Name", value=department.name, required=True),
                _field(name="code", label="Code", value=department.code, required=True),
                _field(
                    name="description",
                    label="Description",
                    field_type="textarea",
                    value=department.description or "",
                    rows=3,
                ),
                _field(
                    name="manager_user_id",
                    label="Manager",
                    field_type="select",
                    value=str(department.manager_user_id or ""),
                    options=_model_options(
                        users,
                        blank_label="No manager",
                        label_getter=lambda item: f"{item.matricule} - {service.build_user_name(item)}",
                    ),
                ),
            ],
        },
        action_forms=[
            {
                "title": "Status",
                "action": f"/admin/departments/{department.id}/toggle-active",
                "submit_label": "Deactivate department" if department.is_active else "Reactivate department",
                "style": "danger" if department.is_active else "success",
                "confirm": "This changes the department availability for future assignments.",
                "fields": [{"name": "is_active", "value": "false" if department.is_active else "true"}],
            }
        ],
        related_tables=[
            _table(
                [{"key": "team", "label": "Teams"}],
                [
                    {"team": f"{team.code} - {team.name}", "team_url": f"/admin/teams/{team.id}"}
                    for team in teams
                ],
            ),
            _table(
                [{"key": "employee", "label": "Employees"}],
                [
                    {
                        "employee": f"{employee.matricule} - {service.build_employee_name(employee)}",
                        "employee_url": f"/admin/employees/{employee.id}",
                    }
                    for employee in employees
                ],
            ),
        ],
    )


@router.post("/departments/{department_id}")
async def admin_department_update(
    department_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = DepartmentUpdateRequest(
            name=_clean(form.get("name")),
            code=_clean(form.get("code")),
            description=_clean(form.get("description")),
            manager_user_id=_clean(form.get("manager_user_id")),
        )
        service.update_department(department_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(
            f"/admin/departments/{department_id}",
            message=str(exc),
            level="danger",
        )

    return _redirect_with_message(
        f"/admin/departments/{department_id}",
        message="Department updated successfully.",
        level="success",
    )


@router.post("/departments/{department_id}/toggle-active")
async def admin_department_toggle_active(
    department_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        service.set_department_active(
            department_id,
            is_active=(_clean(form.get("is_active"), blank_to_none=False) == "true"),
        )
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(
            f"/admin/departments/{department_id}",
            message=str(exc),
            level="danger",
        )

    return _redirect_with_message(
        f"/admin/departments/{department_id}",
        message="Department status updated successfully.",
        level="success",
    )


@router.get("/teams", response_class=HTMLResponse)
def admin_teams(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    teams = service.list_teams(include_inactive=include_inactive)
    departments = service.list_lookup_departments(include_inactive=True)
    users = service.list_lookup_users(include_inactive=True)
    department_map = {department.id: department for department in departments}
    user_map = {user.id: user for user in users}
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Teams",
        page_description="Manage teams, leadership assignments, and the department structure they belong to.",
        filters_form={
            "action": "/admin/teams",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                )
            ],
        },
        create_form={
            "action": "/admin/teams",
            "submit_label": "Create team",
            "title": "Create Team",
            "fields": [
                _field(name="name", label="Name", required=True),
                _field(name="code", label="Code", required=True),
                _field(name="description", label="Description", field_type="textarea", rows=3),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value="",
                    required=True,
                    options=_model_options(
                        departments,
                        blank_label="Select department",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="leader_user_id",
                    label="Leader",
                    field_type="select",
                    value="",
                    options=_model_options(
                        users,
                        blank_label="No leader",
                        label_getter=lambda item: f"{item.matricule} - {service.build_user_name(item)}",
                    ),
                ),
            ],
        },
        table=_table(
            [
                {"key": "code", "label": "Code"},
                {"key": "name", "label": "Name"},
                {"key": "department", "label": "Department"},
                {"key": "leader", "label": "Leader"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "code": team.code,
                    "code_url": f"/admin/teams/{team.id}",
                    "name": team.name,
                    "department": department_map[team.department_id].name if team.department_id in department_map else "-",
                    "leader": service.build_user_name(user_map[team.leader_user_id])
                    if team.leader_user_id in user_map
                    else "-",
                    "active": "Yes" if team.is_active else "No",
                }
                for team in teams
            ],
        ),
    )


@router.post("/teams")
async def admin_teams_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = TeamCreateRequest(
            name=_clean(form.get("name"), blank_to_none=False),
            code=_clean(form.get("code"), blank_to_none=False),
            description=_clean(form.get("description")),
            department_id=_clean(form.get("department_id"), blank_to_none=False),
            leader_user_id=_clean(form.get("leader_user_id")),
        )
        created_team = service.create_team(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/teams", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/teams/{created_team.id}",
        message="Team created successfully.",
        level="success",
    )


@router.get("/teams/{team_id}", response_class=HTMLResponse)
def admin_team_detail(
    team_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        team = service.get_team(team_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/teams", message=str(exc), level="danger")

    departments = service.list_lookup_departments(include_inactive=True)
    users = service.list_lookup_users(include_inactive=True)
    department_map = {department.id: department for department in departments}
    user_map = {user.id: user for user in users}
    employees = service.get_team_employees(team.id)
    recent_performances = service.get_recent_team_performances(team.id)
    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Team {team.code}",
        page_description="Inspect team structure, leadership, member employees, and recent performance records.",
        back_url="/admin/teams",
        detail_fields=[
            {"label": "Code", "value": team.code},
            {"label": "Name", "value": team.name},
            {"label": "Description", "value": team.description or "-"},
            {
                "label": "Department",
                "value": department_map[team.department_id].name if team.department_id in department_map else "-",
            },
            {
                "label": "Leader",
                "value": service.build_user_name(user_map[team.leader_user_id])
                if team.leader_user_id in user_map
                else "-",
            },
            {"label": "Active", "value": "Yes" if team.is_active else "No"},
            {"label": "Created at", "value": team.created_at},
            {"label": "Updated at", "value": team.updated_at},
        ],
        edit_form={
            "action": f"/admin/teams/{team.id}",
            "submit_label": "Update team",
            "title": "Edit Team",
            "fields": [
                _field(name="name", label="Name", value=team.name, required=True),
                _field(name="code", label="Code", value=team.code, required=True),
                _field(
                    name="description",
                    label="Description",
                    field_type="textarea",
                    value=team.description or "",
                    rows=3,
                ),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value=str(team.department_id),
                    required=True,
                    options=_model_options(
                        departments,
                        blank_label="Select department",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="leader_user_id",
                    label="Leader",
                    field_type="select",
                    value=str(team.leader_user_id or ""),
                    options=_model_options(
                        users,
                        blank_label="No leader",
                        label_getter=lambda item: f"{item.matricule} - {service.build_user_name(item)}",
                    ),
                ),
            ],
        },
        action_forms=[
            {
                "title": "Status",
                "action": f"/admin/teams/{team.id}/toggle-active",
                "submit_label": "Deactivate team" if team.is_active else "Reactivate team",
                "style": "danger" if team.is_active else "success",
                "confirm": "This changes whether the team can be referenced by active flows.",
                "fields": [{"name": "is_active", "value": "false" if team.is_active else "true"}],
            }
        ],
        related_tables=[
            _table(
                [{"key": "employee", "label": "Employees"}],
                [
                    {
                        "employee": f"{employee.matricule} - {service.build_employee_name(employee)}",
                        "employee_url": f"/admin/employees/{employee.id}",
                    }
                    for employee in employees
                ],
            ),
            _table(
                [
                    {"key": "performance_date", "label": "Date"},
                    {"key": "performance_percentage", "label": "Performance %"},
                ],
                [
                    {
                        "performance_date": str(item.performance_date),
                        "performance_date_url": f"/admin/performance/records/{item.id}",
                        "performance_percentage": item.performance_percentage,
                    }
                    for item in recent_performances
                ],
            ),
        ],
    )


@router.post("/teams/{team_id}")
async def admin_team_update(
    team_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = TeamUpdateRequest(
            name=_clean(form.get("name")),
            code=_clean(form.get("code")),
            description=_clean(form.get("description")),
            department_id=_clean(form.get("department_id")),
            leader_user_id=_clean(form.get("leader_user_id")),
        )
        service.update_team(team_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/teams/{team_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/teams/{team_id}",
        message="Team updated successfully.",
        level="success",
    )


@router.post("/teams/{team_id}/toggle-active")
async def admin_team_toggle_active(
    team_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        service.set_team_active(
            team_id,
            is_active=(_clean(form.get("is_active"), blank_to_none=False) == "true"),
        )
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/teams/{team_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/teams/{team_id}",
        message="Team status updated successfully.",
        level="success",
    )


@router.get("/job-titles", response_class=HTMLResponse)
def admin_job_titles(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    job_titles = service.list_job_titles(include_inactive=include_inactive)
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Job Titles",
        page_description="Manage job titles, hierarchy levels, and the permissions eventually attached to them.",
        filters_form={
            "action": "/admin/job-titles",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                )
            ],
        },
        create_form={
            "action": "/admin/job-titles",
            "submit_label": "Create job title",
            "title": "Create Job Title",
            "fields": [
                _field(name="name", label="Name", required=True),
                _field(name="code", label="Code", required=True),
                _field(name="description", label="Description", field_type="textarea", rows=3),
                _field(
                    name="hierarchical_level",
                    label="Hierarchical level",
                    field_type="number",
                    value="0",
                    required=True,
                ),
            ],
        },
        table=_table(
            [
                {"key": "code", "label": "Code"},
                {"key": "name", "label": "Name"},
                {"key": "hierarchy", "label": "Hierarchy"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "code": item.code,
                    "code_url": f"/admin/job-titles/{item.id}",
                    "name": item.name,
                    "hierarchy": item.hierarchical_level,
                    "active": "Yes" if item.is_active else "No",
                }
                for item in job_titles
            ],
        ),
    )


@router.post("/job-titles")
async def admin_job_titles_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = JobTitleCreateRequest(
            name=_clean(form.get("name"), blank_to_none=False),
            code=_clean(form.get("code"), blank_to_none=False),
            description=_clean(form.get("description")),
            hierarchical_level=_clean(form.get("hierarchical_level"), blank_to_none=False),
        )
        job_title = service.create_job_title(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/job-titles", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/job-titles/{job_title.id}",
        message="Job title created successfully.",
        level="success",
    )


@router.get("/job-titles/{job_title_id}", response_class=HTMLResponse)
def admin_job_title_detail(
    job_title_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        job_title = service.get_job_title(job_title_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/job-titles", message=str(exc), level="danger")

    employees = service.get_job_title_employees(job_title.id)
    permissions = service.get_job_title_permissions(job_title.id)
    all_permissions = service.list_lookup_permissions(include_inactive=True)
    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Job Title {job_title.code}",
        page_description="Update job-title metadata and safely replace its permission assignment set.",
        back_url="/admin/job-titles",
        detail_fields=[
            {"label": "Code", "value": job_title.code},
            {"label": "Name", "value": job_title.name},
            {"label": "Description", "value": job_title.description or "-"},
            {"label": "Hierarchical level", "value": job_title.hierarchical_level},
            {"label": "Active", "value": "Yes" if job_title.is_active else "No"},
            {"label": "Created at", "value": job_title.created_at},
            {"label": "Updated at", "value": job_title.updated_at},
        ],
        edit_form={
            "action": f"/admin/job-titles/{job_title.id}",
            "submit_label": "Update job title",
            "title": "Edit Job Title",
            "fields": [
                _field(name="name", label="Name", value=job_title.name, required=True),
                _field(name="code", label="Code", value=job_title.code, required=True),
                _field(
                    name="description",
                    label="Description",
                    field_type="textarea",
                    value=job_title.description or "",
                    rows=3,
                ),
                _field(
                    name="hierarchical_level",
                    label="Hierarchical level",
                    field_type="number",
                    value=str(job_title.hierarchical_level),
                    required=True,
                ),
            ],
        },
        action_forms=[
            {
                "title": "Status",
                "action": f"/admin/job-titles/{job_title.id}/toggle-active",
                "submit_label": "Deactivate job title" if job_title.is_active else "Reactivate job title",
                "style": "danger" if job_title.is_active else "success",
                "confirm": "This changes whether the job title can be assigned to active employees.",
                "fields": [{"name": "is_active", "value": "false" if job_title.is_active else "true"}],
            }
        ],
        secondary_forms=[
            {
                "action": f"/admin/job-titles/{job_title.id}/permissions",
                "submit_label": "Replace permissions",
                "title": "Assigned Permissions",
                "fields": [
                    _field(
                        name="permission_ids",
                        label="Permissions",
                        field_type="multiselect",
                        value=[str(item.id) for item in permissions],
                        options=_model_options(
                            all_permissions,
                            blank_label=None,
                            label_getter=lambda item: f"{item.module} / {item.code}",
                        ),
                        help_text="This replaces the full permission set assigned to the job title.",
                    )
                ],
            }
        ],
        related_tables=[
            _table(
                [{"key": "employee", "label": "Employees"}],
                [
                    {
                        "employee": f"{employee.matricule} - {service.build_employee_name(employee)}",
                        "employee_url": f"/admin/employees/{employee.id}",
                    }
                    for employee in employees
                ],
            ),
            _table(
                [{"key": "permission", "label": "Permissions"}],
                [
                    {
                        "permission": f"{permission.module} / {permission.code}",
                        "permission_url": f"/admin/permissions/{permission.id}",
                    }
                    for permission in permissions
                ],
            ),
        ],
    )


@router.post("/job-titles/{job_title_id}")
async def admin_job_title_update(
    job_title_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = JobTitleUpdateRequest(
            name=_clean(form.get("name")),
            code=_clean(form.get("code")),
            description=_clean(form.get("description")),
            hierarchical_level=_clean(form.get("hierarchical_level")),
        )
        service.update_job_title(job_title_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/job-titles/{job_title_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/job-titles/{job_title_id}",
        message="Job title updated successfully.",
        level="success",
    )


@router.post("/job-titles/{job_title_id}/toggle-active")
async def admin_job_title_toggle_active(
    job_title_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        service.set_job_title_active(
            job_title_id,
            is_active=(_clean(form.get("is_active"), blank_to_none=False) == "true"),
        )
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/job-titles/{job_title_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/job-titles/{job_title_id}",
        message="Job title status updated successfully.",
        level="success",
    )


@router.post("/job-titles/{job_title_id}/permissions")
async def admin_job_title_permissions(
    job_title_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        service.replace_job_title_permissions(
            job_title_id,
            permission_ids=[
                _parse_int_value(item, "Permission id")
                for item in _clean_list(form.getlist("permission_ids"))
            ],
        )
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/job-titles/{job_title_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/job-titles/{job_title_id}",
        message="Job title permissions replaced successfully.",
        level="success",
    )


@router.get("/permissions", response_class=HTMLResponse)
def admin_permissions(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    module = request.query_params.get("module")
    permissions = service.list_permissions(include_inactive=include_inactive, module=module)
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Permissions",
        page_description="Manage the permission catalog used by route protection and job-title permission assignments.",
        filters_form={
            "action": "/admin/permissions",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(name="module", label="Module", value=module or ""),
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/permissions",
            "submit_label": "Create permission",
            "title": "Create Permission",
            "fields": [
                _field(name="code", label="Code", required=True),
                _field(name="name", label="Name", required=True),
                _field(name="module", label="Module", required=True),
                _field(name="description", label="Description", field_type="textarea", rows=3),
            ],
        },
        table=_table(
            [
                {"key": "code", "label": "Code"},
                {"key": "name", "label": "Name"},
                {"key": "module", "label": "Module"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "code": permission.code,
                    "code_url": f"/admin/permissions/{permission.id}",
                    "name": permission.name,
                    "module": permission.module,
                    "active": "Yes" if permission.is_active else "No",
                }
                for permission in permissions
            ],
        ),
    )


@router.post("/permissions")
async def admin_permissions_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = PermissionCreateRequest(
            code=_clean(form.get("code"), blank_to_none=False),
            name=_clean(form.get("name"), blank_to_none=False),
            module=_clean(form.get("module"), blank_to_none=False),
            description=_clean(form.get("description")),
        )
        permission = service.create_permission(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/permissions", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/permissions/{permission.id}",
        message="Permission created successfully.",
        level="success",
    )


@router.get("/permissions/{permission_id}", response_class=HTMLResponse)
def admin_permission_detail(
    permission_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        permission = service.get_permission(permission_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/permissions", message=str(exc), level="danger")

    job_titles = service.get_permission_job_titles(permission.id)
    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Permission {permission.code}",
        page_description="Edit catalog metadata and inspect which job titles currently receive this permission.",
        back_url="/admin/permissions",
        detail_fields=[
            {"label": "Code", "value": permission.code},
            {"label": "Name", "value": permission.name},
            {"label": "Module", "value": permission.module},
            {"label": "Description", "value": permission.description or "-"},
            {"label": "Active", "value": "Yes" if permission.is_active else "No"},
            {"label": "Created at", "value": permission.created_at},
            {"label": "Updated at", "value": permission.updated_at},
        ],
        edit_form={
            "action": f"/admin/permissions/{permission.id}",
            "submit_label": "Update permission",
            "title": "Edit Permission",
            "fields": [
                _field(name="code", label="Code", value=permission.code, required=True),
                _field(name="name", label="Name", value=permission.name, required=True),
                _field(name="module", label="Module", value=permission.module, required=True),
                _field(
                    name="description",
                    label="Description",
                    field_type="textarea",
                    value=permission.description or "",
                    rows=3,
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if permission.is_active else "false",
                    options=_bool_options(),
                ),
            ],
        },
        related_tables=[
            _table(
                [{"key": "job_title", "label": "Assigned job titles"}],
                [
                    {
                        "job_title": f"{job_title.code} - {job_title.name}",
                        "job_title_url": f"/admin/job-titles/{job_title.id}",
                    }
                    for job_title in job_titles
                ],
            )
        ],
    )


@router.post("/permissions/{permission_id}")
async def admin_permission_update(
    permission_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = PermissionUpdateRequest(
            code=_clean(form.get("code")),
            name=_clean(form.get("name")),
            module=_clean(form.get("module")),
            description=_clean(form.get("description")),
            is_active=_clean(form.get("is_active")),
        )
        service.update_permission(permission_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/permissions/{permission_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/permissions/{permission_id}",
        message="Permission updated successfully.",
        level="success",
    )


@router.get("/request-types", response_class=HTMLResponse)
def admin_request_types(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    request_types = service.list_request_types(include_inactive=include_inactive)
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Request Types",
        page_description="Manage dynamic request-type definitions used by the generic requests engine.",
        filters_form={
            "action": "/admin/request-types",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                )
            ],
        },
        create_form={
            "action": "/admin/request-types",
            "submit_label": "Create request type",
            "title": "Create Request Type",
            "fields": [
                _field(name="code", label="Code", required=True),
                _field(name="name", label="Name", required=True),
                _field(name="description", label="Description", field_type="textarea", rows=3),
            ],
        },
        table=_table(
            [
                {"key": "code", "label": "Code"},
                {"key": "name", "label": "Name"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "code": item.code,
                    "code_url": f"/admin/request-types/{item.id}",
                    "name": item.name,
                    "active": "Yes" if item.is_active else "No",
                }
                for item in request_types
            ],
        ),
    )


@router.post("/request-types")
async def admin_request_types_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = RequestTypeCreateRequest(
            code=_clean(form.get("code"), blank_to_none=False),
            name=_clean(form.get("name"), blank_to_none=False),
            description=_clean(form.get("description")),
        )
        request_type = service.create_request_type(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/request-types", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/request-types/{request_type.id}",
        message="Request type created successfully.",
        level="success",
    )


@router.get("/request-types/{request_type_id}", response_class=HTMLResponse)
def admin_request_type_detail(
    request_type_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        request_type = service.get_request_type(request_type_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/request-types", message=str(exc), level="danger")

    fields = service.get_request_type_fields(request_type.id)
    steps = service.get_request_type_steps(request_type.id)
    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Request Type {request_type.code}",
        page_description="Update the request-type definition and inspect its field and workflow-step configuration.",
        back_url="/admin/request-types",
        detail_fields=[
            {"label": "Code", "value": request_type.code},
            {"label": "Name", "value": request_type.name},
            {"label": "Description", "value": request_type.description or "-"},
            {"label": "Active", "value": "Yes" if request_type.is_active else "No"},
            {"label": "Created at", "value": request_type.created_at},
            {"label": "Updated at", "value": request_type.updated_at},
        ],
        edit_form={
            "action": f"/admin/request-types/{request_type.id}",
            "submit_label": "Update request type",
            "title": "Edit Request Type",
            "fields": [
                _field(name="code", label="Code", value=request_type.code, required=True),
                _field(name="name", label="Name", value=request_type.name, required=True),
                _field(
                    name="description",
                    label="Description",
                    field_type="textarea",
                    value=request_type.description or "",
                    rows=3,
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if request_type.is_active else "false",
                    options=_bool_options(),
                ),
            ],
        },
        related_tables=[
            _table(
                [
                    {"key": "code", "label": "Field"},
                    {"key": "field_type", "label": "Type"},
                    {"key": "required", "label": "Required"},
                ],
                [
                    {
                        "code": field.code,
                        "code_url": f"/admin/request-fields/{field.id}",
                        "field_type": field.field_type,
                        "required": "Yes" if field.is_required else "No",
                    }
                    for field in fields
                ],
            ),
            _table(
                [
                    {"key": "name", "label": "Workflow step"},
                    {"key": "step_order", "label": "Order"},
                    {"key": "step_kind", "label": "Kind"},
                ],
                [
                    {
                        "name": step.name,
                        "name_url": f"/admin/request-steps/{step.id}",
                        "step_order": step.step_order,
                        "step_kind": step.step_kind,
                    }
                    for step in steps
                ],
            ),
        ],
    )


@router.post("/request-types/{request_type_id}")
async def admin_request_type_update(
    request_type_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = RequestTypeUpdateRequest(
            code=_clean(form.get("code")),
            name=_clean(form.get("name")),
            description=_clean(form.get("description")),
            is_active=_clean(form.get("is_active")),
        )
        service.update_request_type(request_type_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/request-types/{request_type_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/request-types/{request_type_id}",
        message="Request type updated successfully.",
        level="success",
    )


@router.get("/request-fields", response_class=HTMLResponse)
def admin_request_fields(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    request_type_id = request.query_params.get("request_type_id")
    request_types = service.list_lookup_request_types(include_inactive=True)
    request_type_map = {item.id: item for item in request_types}
    fields = service.list_request_fields(
        request_type_id=_parse_int_value(request_type_id, "Request type"),
        include_inactive=include_inactive,
    )
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Request Fields",
        page_description="Manage the dynamic field definitions attached to request types.",
        filters_form={
            "action": "/admin/request-fields",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="request_type_id",
                    label="Request type",
                    field_type="select",
                    value=request_type_id or "",
                    options=_model_options(
                        request_types,
                        blank_label="All request types",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/request-fields",
            "submit_label": "Create request field",
            "title": "Create Request Field",
            "fields": [
                _field(
                    name="request_type_id",
                    label="Request type",
                    field_type="select",
                    value=request_type_id or "",
                    required=True,
                    options=_model_options(
                        request_types,
                        blank_label="Select request type",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="code", label="Code", required=True),
                _field(name="label", label="Label", required=True),
                _field(
                    name="field_type",
                    label="Field type",
                    field_type="select",
                    value=RequestFieldTypeEnum.TEXT.value,
                    options=[_option(item.value, item.value) for item in RequestFieldTypeEnum],
                ),
                _field(
                    name="is_required",
                    label="Required",
                    field_type="select",
                    value="false",
                    options=_bool_options(),
                ),
                _field(name="placeholder", label="Placeholder"),
                _field(name="help_text", label="Help text", field_type="textarea", rows=2),
                _field(name="default_value", label="Default value"),
                _field(name="sort_order", label="Sort order", field_type="number", value="0"),
            ],
        },
        table=_table(
            [
                {"key": "code", "label": "Code"},
                {"key": "request_type", "label": "Request Type"},
                {"key": "field_type", "label": "Field Type"},
                {"key": "required", "label": "Required"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "code": field.code,
                    "code_url": f"/admin/request-fields/{field.id}",
                    "request_type": request_type_map[field.request_type_id].code if field.request_type_id in request_type_map else field.request_type_id,
                    "field_type": field.field_type,
                    "required": "Yes" if field.is_required else "No",
                    "active": "Yes" if field.is_active else "No",
                }
                for field in fields
            ],
        ),
    )


@router.post("/request-fields")
async def admin_request_fields_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        request_type_id = _parse_int_value(
            _clean(form.get("request_type_id"), blank_to_none=False),
            "Request type",
        )
        if request_type_id is None:
            raise AdminPanelValidationError("Request type is required.")
        payload = RequestTypeFieldCreateRequest(
            code=_clean(form.get("code"), blank_to_none=False),
            label=_clean(form.get("label"), blank_to_none=False),
            field_type=_clean(form.get("field_type"), blank_to_none=False),
            is_required=_clean(form.get("is_required"), blank_to_none=False),
            placeholder=_clean(form.get("placeholder")),
            help_text=_clean(form.get("help_text")),
            default_value=_clean(form.get("default_value")),
            sort_order=_clean(form.get("sort_order")) or "0",
        )
        field = service.create_request_field(request_type_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/request-fields", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/request-fields/{field.id}",
        message="Request field created successfully.",
        level="success",
    )


@router.get("/request-fields/{request_field_id}", response_class=HTMLResponse)
def admin_request_field_detail(
    request_field_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        field = service.get_request_field(request_field_id)
        request_type = service.get_request_type(field.request_type_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/request-fields", message=str(exc), level="danger")

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Request Field {field.code}",
        page_description="Update one dynamic field definition without leaving the generic requests architecture.",
        back_url="/admin/request-fields",
        detail_fields=[
            {"label": "Request type", "value": f"{request_type.code} - {request_type.name}"},
            {"label": "Code", "value": field.code},
            {"label": "Label", "value": field.label},
            {"label": "Field type", "value": field.field_type},
            {"label": "Required", "value": "Yes" if field.is_required else "No"},
            {"label": "Placeholder", "value": field.placeholder or "-"},
            {"label": "Help text", "value": field.help_text or "-"},
            {"label": "Default value", "value": field.default_value if field.default_value is not None else "-"},
            {"label": "Sort order", "value": field.sort_order},
            {"label": "Active", "value": "Yes" if field.is_active else "No"},
        ],
        edit_form={
            "action": f"/admin/request-fields/{field.id}",
            "submit_label": "Update request field",
            "title": "Edit Request Field",
            "fields": [
                _field(name="code", label="Code", value=field.code, required=True),
                _field(name="label", label="Label", value=field.label, required=True),
                _field(
                    name="field_type",
                    label="Field type",
                    field_type="select",
                    value=field.field_type,
                    options=[_option(item.value, item.value) for item in RequestFieldTypeEnum],
                ),
                _field(
                    name="is_required",
                    label="Required",
                    field_type="select",
                    value="true" if field.is_required else "false",
                    options=_bool_options(),
                ),
                _field(name="placeholder", label="Placeholder", value=field.placeholder or ""),
                _field(name="help_text", label="Help text", field_type="textarea", value=field.help_text or "", rows=2),
                _field(name="default_value", label="Default value", value=field.default_value if field.default_value is not None else ""),
                _field(name="sort_order", label="Sort order", field_type="number", value=str(field.sort_order)),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if field.is_active else "false",
                    options=_bool_options(),
                ),
            ],
        },
    )


@router.post("/request-fields/{request_field_id}")
async def admin_request_field_update(
    request_field_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = RequestTypeFieldUpdateRequest(
            code=_clean(form.get("code")),
            label=_clean(form.get("label")),
            field_type=_clean(form.get("field_type")),
            is_required=_clean(form.get("is_required")),
            placeholder=_clean(form.get("placeholder")),
            help_text=_clean(form.get("help_text")),
            default_value=_clean(form.get("default_value")),
            sort_order=_clean(form.get("sort_order")),
            is_active=_clean(form.get("is_active")),
        )
        service.update_request_field(request_field_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/request-fields/{request_field_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/request-fields/{request_field_id}",
        message="Request field updated successfully.",
        level="success",
    )


@router.get("/request-steps", response_class=HTMLResponse)
def admin_request_steps(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    include_inactive = request.query_params.get("include_inactive") == "true"
    request_type_id = request.query_params.get("request_type_id")
    request_types = service.list_lookup_request_types(include_inactive=True)
    request_type_map = {item.id: item for item in request_types}
    steps = service.list_workflow_steps(
        request_type_id=_parse_int_value(request_type_id, "Request type"),
        include_inactive=include_inactive,
    )
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Request Steps",
        page_description="Manage the configured workflow steps attached to request types.",
        filters_form={
            "action": "/admin/request-steps",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="request_type_id",
                    label="Request type",
                    field_type="select",
                    value=request_type_id or "",
                    options=_model_options(
                        request_types,
                        blank_label="All request types",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="include_inactive",
                    label="Include inactive",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/request-steps",
            "submit_label": "Create workflow step",
            "title": "Create Workflow Step",
            "fields": [
                _field(
                    name="request_type_id",
                    label="Request type",
                    field_type="select",
                    value=request_type_id or "",
                    required=True,
                    options=_model_options(
                        request_types,
                        blank_label="Select request type",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="step_order", label="Step order", field_type="number", required=True),
                _field(name="name", label="Name", required=True),
                _field(
                    name="step_kind",
                    label="Step kind",
                    field_type="select",
                    value=RequestStepKindEnum.APPROVER.value,
                    options=[_option(item.value, item.value) for item in RequestStepKindEnum],
                ),
                _field(
                    name="resolver_type",
                    label="Resolver type",
                    field_type="select",
                    value="",
                    options=[_option("", "No resolver")] + [_option(item.value, item.value) for item in RequestResolverTypeEnum],
                ),
                _field(
                    name="is_required",
                    label="Required",
                    field_type="select",
                    value="true",
                    options=_bool_options(),
                ),
            ],
        },
        table=_table(
            [
                {"key": "name", "label": "Name"},
                {"key": "request_type", "label": "Request Type"},
                {"key": "step_order", "label": "Order"},
                {"key": "step_kind", "label": "Kind"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "name": step.name,
                    "name_url": f"/admin/request-steps/{step.id}",
                    "request_type": request_type_map[step.request_type_id].code if step.request_type_id in request_type_map else step.request_type_id,
                    "step_order": step.step_order,
                    "step_kind": step.step_kind,
                    "active": "Yes" if step.is_active else "No",
                }
                for step in steps
            ],
        ),
    )


@router.post("/request-steps")
async def admin_request_steps_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        request_type_id = _parse_int_value(
            _clean(form.get("request_type_id"), blank_to_none=False),
            "Request type",
        )
        if request_type_id is None:
            raise AdminPanelValidationError("Request type is required.")
        payload = RequestWorkflowStepCreateRequest(
            step_order=_clean(form.get("step_order"), blank_to_none=False),
            name=_clean(form.get("name"), blank_to_none=False),
            step_kind=_clean(form.get("step_kind"), blank_to_none=False),
            resolver_type=_clean(form.get("resolver_type")),
            is_required=_clean(form.get("is_required"), blank_to_none=False),
        )
        step = service.create_workflow_step(request_type_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/request-steps", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/request-steps/{step.id}",
        message="Workflow step created successfully.",
        level="success",
    )


@router.get("/request-steps/{step_id}", response_class=HTMLResponse)
def admin_request_step_detail(
    step_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        step = service.get_workflow_step(step_id)
        request_type = service.get_request_type(step.request_type_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/request-steps", message=str(exc), level="danger")

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Workflow Step {step.name}",
        page_description="Update one request workflow step definition and inspect how it belongs to the generic request type.",
        back_url="/admin/request-steps",
        detail_fields=[
            {"label": "Request type", "value": f"{request_type.code} - {request_type.name}"},
            {"label": "Step order", "value": step.step_order},
            {"label": "Name", "value": step.name},
            {"label": "Step kind", "value": step.step_kind},
            {"label": "Resolver type", "value": step.resolver_type or "-"},
            {"label": "Required", "value": "Yes" if step.is_required else "No"},
            {"label": "Active", "value": "Yes" if step.is_active else "No"},
        ],
        edit_form={
            "action": f"/admin/request-steps/{step.id}",
            "submit_label": "Update workflow step",
            "title": "Edit Workflow Step",
            "fields": [
                _field(name="step_order", label="Step order", field_type="number", value=str(step.step_order), required=True),
                _field(name="name", label="Name", value=step.name, required=True),
                _field(
                    name="step_kind",
                    label="Step kind",
                    field_type="select",
                    value=step.step_kind,
                    options=[_option(item.value, item.value) for item in RequestStepKindEnum],
                ),
                _field(
                    name="resolver_type",
                    label="Resolver type",
                    field_type="select",
                    value=step.resolver_type or "",
                    options=[_option("", "No resolver")] + [_option(item.value, item.value) for item in RequestResolverTypeEnum],
                ),
                _field(
                    name="is_required",
                    label="Required",
                    field_type="select",
                    value="true" if step.is_required else "false",
                    options=_bool_options(),
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if step.is_active else "false",
                    options=_bool_options(),
                ),
            ],
        },
    )


@router.post("/request-steps/{step_id}")
async def admin_request_step_update(
    step_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = RequestWorkflowStepUpdateRequest(
            step_order=_clean(form.get("step_order")),
            name=_clean(form.get("name")),
            step_kind=_clean(form.get("step_kind")),
            resolver_type=_clean(form.get("resolver_type")),
            is_required=_clean(form.get("is_required")),
            is_active=_clean(form.get("is_active")),
        )
        service.update_workflow_step(step_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/request-steps/{step_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/request-steps/{step_id}",
        message="Workflow step updated successfully.",
        level="success",
    )


@router.get("/requests", response_class=HTMLResponse)
def admin_requests(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    status_value = request.query_params.get("status")
    request_type_id = request.query_params.get("request_type_id")
    employee_id = request.query_params.get("employee_id")
    q = request.query_params.get("q")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    request_types = service.list_lookup_request_types(include_inactive=True)
    request_type_map = {item.id: item for item in request_types}
    requests_items = service.list_requests(
        status=_parse_enum(RequestStatusEnum, status_value, "Request status"),
        request_type_id=_parse_int_value(request_type_id, "Request type"),
        employee_id=_parse_int_value(employee_id, "Employee"),
        q=q,
        date_from=_parse_date_value(date_from),
        date_to=_parse_date_value(date_to),
        limit=200,
    )
    employees_map = {
        item.id: item
        for item in service.list_employees(
            include_inactive=True,
            q=None,
            department_id=None,
            team_id=None,
            job_title_id=None,
        )
    }
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Requests",
        page_description="Inspect request instances, their current workflow state, and the values submitted through the dynamic requests engine.",
        filters_form={
            "action": "/admin/requests",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(name="q", label="Search", value=q or ""),
                _field(
                    name="status",
                    label="Status",
                    field_type="select",
                    value=status_value or "",
                    options=[_option("", "All statuses")] + [_option(item.value, item.value) for item in RequestStatusEnum],
                ),
                _field(
                    name="request_type_id",
                    label="Request type",
                    field_type="select",
                    value=request_type_id or "",
                    options=_model_options(
                        request_types,
                        blank_label="All request types",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="employee_id", label="Employee id", value=employee_id or ""),
                _field(name="date_from", label="Date from", field_type="date", value=date_from or ""),
                _field(name="date_to", label="Date to", field_type="date", value=date_to or ""),
            ],
        },
        table=_table(
            [
                {"key": "request_id", "label": "Request"},
                {"key": "request_type", "label": "Request Type"},
                {"key": "employee", "label": "Requester"},
                {"key": "status", "label": "Status"},
                {"key": "submitted_at", "label": "Submitted at"},
            ],
            [
                {
                    "request_id": item.id,
                    "request_id_url": f"/admin/requests/{item.id}",
                    "request_type": request_type_map[item.request_type_id].code if item.request_type_id in request_type_map else item.request_type_id,
                    "employee": f"{employees_map[item.requester_employee_id].matricule} - {service.build_employee_name(employees_map[item.requester_employee_id])}" if item.requester_employee_id in employees_map else item.requester_employee_id,
                    "status": item.status,
                    "submitted_at": item.submitted_at,
                }
                for item in requests_items
            ],
        ),
    )


@router.get("/requests/{request_id}", response_class=HTMLResponse)
def admin_request_detail(
    request_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        request_detail = service.get_request_detail(request_id, current_admin)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/requests", message=str(exc), level="danger")

    related_tables = [
        _table(
            [
                {"key": "field_code", "label": "Field"},
                {"key": "field_label", "label": "Label"},
                {"key": "value", "label": "Value"},
            ],
            [
                {
                    "field_code": item.field_code,
                    "field_label": item.field_label,
                    "value": item.value if item.value is not None else "-",
                }
                for item in request_detail.submitted_values
            ],
        ),
        _table(
            [
                {"key": "name", "label": "Step"},
                {"key": "state", "label": "State"},
                {"key": "actor_name", "label": "Actor"},
                {"key": "acted_at", "label": "Acted at"},
            ],
            [
                {
                    "name": item.name,
                    "state": item.state,
                    "actor_name": item.actor_name or "-",
                    "acted_at": item.acted_at or "-",
                }
                for item in request_detail.workflow_progress
            ],
        ),
        _table(
            [
                {"key": "action", "label": "Action"},
                {"key": "actor_name", "label": "Actor"},
                {"key": "comment", "label": "Comment"},
                {"key": "created_at", "label": "Created at"},
            ],
            [
                {
                    "action": item.action,
                    "actor_name": item.actor_name or "-",
                    "comment": item.comment or "-",
                    "created_at": item.created_at,
                }
                for item in request_detail.action_history
            ],
        ),
    ]
    if request_detail.leave_details is not None:
        related_tables.insert(
            0,
            _table(
                [{"key": "metric", "label": "Leave detail"}, {"key": "value", "label": "Value"}],
                [
                    {"metric": "Start date", "value": request_detail.leave_details.date_start},
                    {"metric": "End date", "value": request_detail.leave_details.date_end},
                    {"metric": "Requested duration", "value": request_detail.leave_details.requested_duration_days},
                    {"metric": "Leave option", "value": request_detail.leave_details.leave_option},
                    {"metric": "Balance validation", "value": "Yes" if request_detail.leave_details.balance_validation_applied else "No"},
                    {"metric": "Available balance at submission", "value": request_detail.leave_details.requester_available_balance_days},
                ],
            ),
        )

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Request #{request_detail.id}",
        page_description="Read-only workflow inspection for debugging, administration, and safe backend support operations.",
        back_url="/admin/requests",
        detail_fields=[
            {"label": "Request id", "value": request_detail.id},
            {"label": "Request type", "value": f"{request_detail.request_type_code} - {request_detail.request_type_name}"},
            {"label": "Requester user id", "value": request_detail.requester_user_id},
            {"label": "Requester employee id", "value": request_detail.requester_employee_id},
            {"label": "Status", "value": request_detail.status},
            {"label": "Current step", "value": request_detail.current_step.name if request_detail.current_step is not None else "-"},
            {"label": "Current approver", "value": request_detail.current_step.current_approver_name if request_detail.current_step is not None and request_detail.current_step.current_approver_name is not None else "-"},
            {"label": "Submitted at", "value": request_detail.submitted_at},
            {"label": "Completed at", "value": request_detail.completed_at or "-"},
            {"label": "Rejection reason", "value": request_detail.rejection_reason or "-"},
        ],
        related_tables=related_tables,
    )


@router.get("/attendance/daily", response_class=HTMLResponse)
def admin_attendance_daily(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    employee_id = request.query_params.get("employee_id")
    matricule = request.query_params.get("matricule")
    team_id = request.query_params.get("team_id")
    department_id = request.query_params.get("department_id")
    status_value = request.query_params.get("status")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    include_inactive = request.query_params.get("include_inactive") == "true"
    departments = service.list_lookup_departments(include_inactive=True)
    teams = service.list_lookup_teams(include_inactive=True)
    summaries = service.list_daily_summaries(
        employee_id=_parse_int_value(employee_id, "Employee"),
        matricule=matricule,
        team_id=_parse_int_value(team_id, "Team"),
        department_id=_parse_int_value(department_id, "Department"),
        status=_parse_enum(AttendanceStatusEnum, status_value, "Attendance status"),
        date_from=_parse_date_value(date_from),
        date_to=_parse_date_value(date_to),
        include_inactive=include_inactive,
        limit=300,
    )
    employees_map = {
        item.id: item
        for item in service.list_employees(
            include_inactive=True,
            q=None,
            department_id=None,
            team_id=None,
            job_title_id=None,
        )
    }
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Attendance Daily Summaries",
        page_description="Inspect the lightweight day-level attendance source used by the backend for attendance operations and reporting.",
        filters_form={
            "action": "/admin/attendance/daily",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(name="employee_id", label="Employee id", value=employee_id or ""),
                _field(name="matricule", label="Matricule", value=matricule or ""),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value=department_id or "",
                    options=_model_options(
                        departments,
                        blank_label="All departments",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    options=_model_options(
                        teams,
                        blank_label="All teams",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="status",
                    label="Status",
                    field_type="select",
                    value=status_value or "",
                    options=[_option("", "All statuses")] + [_option(item.value, item.value) for item in AttendanceStatusEnum],
                ),
                _field(name="date_from", label="Date from", field_type="date", value=date_from or ""),
                _field(name="date_to", label="Date to", field_type="date", value=date_to or ""),
                _field(
                    name="include_inactive",
                    label="Include inactive employees",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        table=_table(
            [
                {"key": "attendance_date", "label": "Date"},
                {"key": "employee", "label": "Employee"},
                {"key": "status", "label": "Status"},
                {"key": "worked", "label": "Worked minutes"},
                {"key": "linked_request", "label": "Linked request"},
            ],
            [
                {
                    "attendance_date": str(summary.attendance_date),
                    "attendance_date_url": f"/admin/attendance/daily/{summary.id}",
                    "employee": f"{employees_map[summary.employee_id].matricule} - {service.build_employee_name(employees_map[summary.employee_id])}" if summary.employee_id in employees_map else summary.employee_id,
                    "status": summary.status,
                    "worked": summary.worked_duration_minutes if summary.worked_duration_minutes is not None else "-",
                    "linked_request": summary.linked_request_id or "-",
                }
                for summary in summaries
            ],
        ),
    )


@router.get("/attendance/daily/{summary_id}", response_class=HTMLResponse)
def admin_attendance_daily_detail(
    summary_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        summary = service.get_daily_summary(summary_id)
        employee = service.get_employee(summary.employee_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/attendance/daily", message=str(exc), level="danger")

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Attendance {summary.attendance_date}",
        page_description="Read-only inspection of one daily attendance summary kept by the attendance module.",
        back_url="/admin/attendance/daily",
        detail_fields=[
            {"label": "Employee", "value": f"{employee.matricule} - {service.build_employee_name(employee)}"},
            {"label": "Attendance date", "value": summary.attendance_date},
            {"label": "First check-in", "value": summary.first_check_in_at or "-"},
            {"label": "Last check-out", "value": summary.last_check_out_at or "-"},
            {"label": "Worked duration minutes", "value": summary.worked_duration_minutes if summary.worked_duration_minutes is not None else "-"},
            {"label": "Status", "value": summary.status},
            {"label": "Linked request id", "value": summary.linked_request_id or "-"},
            {"label": "Created at", "value": summary.created_at},
            {"label": "Updated at", "value": summary.updated_at},
        ],
        related_tables=[
            _table(
                [{"key": "employee", "label": "Employee record"}],
                [
                    {
                        "employee": f"{employee.matricule} - {service.build_employee_name(employee)}",
                        "employee_url": f"/admin/employees/{employee.id}",
                    }
                ],
            )
        ],
    )


@router.get("/attendance/monthly", response_class=HTMLResponse)
def admin_attendance_monthly(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    employee_id = request.query_params.get("employee_id")
    team_id = request.query_params.get("team_id")
    department_id = request.query_params.get("department_id")
    year = request.query_params.get("year")
    month = request.query_params.get("month")
    include_inactive = request.query_params.get("include_inactive") == "true"
    departments = service.list_lookup_departments(include_inactive=True)
    teams = service.list_lookup_teams(include_inactive=True)
    reports = service.list_monthly_reports(
        employee_id=_parse_int_value(employee_id, "Employee"),
        team_id=_parse_int_value(team_id, "Team"),
        department_id=_parse_int_value(department_id, "Department"),
        year=_parse_int_value(year, "Year"),
        month=_parse_int_value(month, "Month"),
        include_inactive=include_inactive,
        limit=300,
    )
    employees_map = {
        item.id: item
        for item in service.list_employees(
            include_inactive=True,
            q=None,
            department_id=None,
            team_id=None,
            job_title_id=None,
        )
    }
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Attendance Monthly Reports",
        page_description="Inspect generated monthly attendance aggregates and trigger a safe regeneration when needed.",
        filters_form={
            "action": "/admin/attendance/monthly",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(name="employee_id", label="Employee id", value=employee_id or ""),
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value=department_id or "",
                    options=_model_options(
                        departments,
                        blank_label="All departments",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    options=_model_options(
                        teams,
                        blank_label="All teams",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="year", label="Year", field_type="number", value=year or ""),
                _field(name="month", label="Month", field_type="number", value=month or ""),
                _field(
                    name="include_inactive",
                    label="Include inactive employees",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/attendance/monthly/generate",
            "submit_label": "Generate monthly reports",
            "title": "Generate Monthly Reports",
            "fields": [
                _field(name="report_year", label="Year", field_type="number", required=True),
                _field(name="report_month", label="Month", field_type="number", required=True),
                _field(name="employee_id", label="Employee id"),
                _field(
                    name="include_inactive",
                    label="Include inactive employees",
                    field_type="select",
                    value="false",
                    options=_bool_options(),
                ),
            ],
        },
        table=_table(
            [
                {"key": "period", "label": "Period"},
                {"key": "employee", "label": "Employee"},
                {"key": "worked_days", "label": "Worked days"},
                {"key": "worked_minutes", "label": "Worked minutes"},
                {"key": "leave_days", "label": "Leave days"},
            ],
            [
                {
                    "period": f"{report.report_year}-{report.report_month:02d}",
                    "period_url": f"/admin/attendance/monthly/{report.id}",
                    "employee": f"{employees_map[report.employee_id].matricule} - {service.build_employee_name(employees_map[report.employee_id])}" if report.employee_id in employees_map else report.employee_id,
                    "worked_days": report.total_worked_days,
                    "worked_minutes": report.total_worked_minutes,
                    "leave_days": report.total_leave_days,
                }
                for report in reports
            ],
        ),
    )


@router.post("/attendance/monthly/generate")
async def admin_attendance_monthly_generate(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = AttendanceMonthlyReportGenerateRequest(
            report_year=_clean(form.get("report_year"), blank_to_none=False),
            report_month=_clean(form.get("report_month"), blank_to_none=False),
            employee_id=_clean(form.get("employee_id")),
            include_inactive=_clean(form.get("include_inactive"), blank_to_none=False),
        )
        reports = service.generate_monthly_reports(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/attendance/monthly", message=str(exc), level="danger")

    return _redirect_with_message(
        "/admin/attendance/monthly",
        message=f"Generated or refreshed {len(reports)} monthly attendance report(s).",
        level="success",
    )


@router.get("/attendance/monthly/{report_id}", response_class=HTMLResponse)
def admin_attendance_monthly_detail(
    report_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        report = service.get_monthly_report(report_id)
        employee = service.get_employee(report.employee_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/attendance/monthly", message=str(exc), level="danger")

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Attendance Report {report.report_year}-{report.report_month:02d}",
        page_description="Read-only inspection of one generated monthly attendance aggregate.",
        back_url="/admin/attendance/monthly",
        detail_fields=[
            {"label": "Employee", "value": f"{employee.matricule} - {service.build_employee_name(employee)}"},
            {"label": "Year", "value": report.report_year},
            {"label": "Month", "value": report.report_month},
            {"label": "Total worked days", "value": report.total_worked_days},
            {"label": "Total worked minutes", "value": report.total_worked_minutes},
            {"label": "Total present days", "value": report.total_present_days},
            {"label": "Total absence days", "value": report.total_absence_days},
            {"label": "Total leave days", "value": report.total_leave_days},
            {"label": "Created at", "value": report.created_at},
            {"label": "Updated at", "value": report.updated_at},
        ],
    )


@router.get("/performance/objectives", response_class=HTMLResponse)
def admin_performance_objectives(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    team_id = request.query_params.get("team_id")
    include_inactive = request.query_params.get("include_inactive") == "true"
    teams = service.list_lookup_teams(include_inactive=True)
    team_map = {item.id: item for item in teams}
    objectives = service.list_team_objectives(
        team_id=_parse_int_value(team_id, "Team"),
        include_inactive=include_inactive,
    )
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Performance Objectives",
        page_description="Manage the active target configured for each team in the simple performance module.",
        filters_form={
            "action": "/admin/performance/objectives",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    options=_model_options(
                        teams,
                        blank_label="All teams",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="include_inactive",
                    label="Include inactive objectives",
                    field_type="select",
                    value="true" if include_inactive else "false",
                    options=_bool_options(),
                ),
            ],
        },
        create_form={
            "action": "/admin/performance/objectives",
            "submit_label": "Create objective",
            "title": "Create Team Objective",
            "fields": [
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    required=True,
                    options=_model_options(
                        teams,
                        blank_label="Select team",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="objective_value", label="Objective value", field_type="number", required=True),
                _field(
                    name="objective_type",
                    label="Objective type",
                    field_type="select",
                    value="",
                    options=[_option("", "No type")] + [_option(item.value, item.value) for item in TeamObjectiveTypeEnum],
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true",
                    options=_bool_options(),
                ),
            ],
        },
        table=_table(
            [
                {"key": "team", "label": "Team"},
                {"key": "objective_value", "label": "Objective"},
                {"key": "objective_type", "label": "Type"},
                {"key": "active", "label": "Active"},
            ],
            [
                {
                    "team": team_map[item.team_id].name if item.team_id in team_map else item.team_id,
                    "team_url": f"/admin/performance/objectives/{item.id}",
                    "objective_value": item.objective_value,
                    "objective_type": item.objective_type or "-",
                    "active": "Yes" if item.is_active else "No",
                }
                for item in objectives
            ],
        ),
    )


@router.post("/performance/objectives")
async def admin_performance_objectives_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = TeamObjectiveCreateRequest(
            team_id=_clean(form.get("team_id"), blank_to_none=False),
            objective_value=_clean(form.get("objective_value"), blank_to_none=False),
            objective_type=_clean(form.get("objective_type")),
            is_active=_clean(form.get("is_active"), blank_to_none=False),
        )
        objective = service.create_team_objective(payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/performance/objectives", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/performance/objectives/{objective.id}",
        message="Performance objective created successfully.",
        level="success",
    )


@router.get("/performance/objectives/{objective_id}", response_class=HTMLResponse)
def admin_performance_objective_detail(
    objective_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        objective = service.get_team_objective(objective_id)
        team = service.get_team(objective.team_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/performance/objectives", message=str(exc), level="danger")

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Objective for {team.code}",
        page_description="Update the configured team objective without modifying the performance calculation logic.",
        back_url="/admin/performance/objectives",
        detail_fields=[
            {"label": "Team", "value": f"{team.code} - {team.name}"},
            {"label": "Objective value", "value": objective.objective_value},
            {"label": "Objective type", "value": objective.objective_type or "-"},
            {"label": "Active", "value": "Yes" if objective.is_active else "No"},
            {"label": "Created at", "value": objective.created_at},
            {"label": "Updated at", "value": objective.updated_at},
        ],
        edit_form={
            "action": f"/admin/performance/objectives/{objective.id}",
            "submit_label": "Update objective",
            "title": "Edit Objective",
            "fields": [
                _field(name="objective_value", label="Objective value", field_type="number", value=str(objective.objective_value), required=True),
                _field(
                    name="objective_type",
                    label="Objective type",
                    field_type="select",
                    value=objective.objective_type or "",
                    options=[_option("", "No type")] + [_option(item.value, item.value) for item in TeamObjectiveTypeEnum],
                ),
                _field(
                    name="is_active",
                    label="Active",
                    field_type="select",
                    value="true" if objective.is_active else "false",
                    options=_bool_options(),
                ),
            ],
        },
    )


@router.post("/performance/objectives/{objective_id}")
async def admin_performance_objective_update(
    objective_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = TeamObjectiveUpdateRequest(
            objective_value=_clean(form.get("objective_value")),
            objective_type=_clean(form.get("objective_type")),
            is_active=_clean(form.get("is_active")),
        )
        service.update_team_objective(objective_id, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message(f"/admin/performance/objectives/{objective_id}", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/performance/objectives/{objective_id}",
        message="Performance objective updated successfully.",
        level="success",
    )


@router.get("/performance/records", response_class=HTMLResponse)
def admin_performance_records(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    team_id = request.query_params.get("team_id")
    department_id = request.query_params.get("department_id")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    teams = service.list_lookup_teams(include_inactive=True)
    departments = service.list_lookup_departments(include_inactive=True)
    team_map = {item.id: item for item in teams}
    records = service.list_daily_performances(
        team_id=_parse_int_value(team_id, "Team"),
        department_id=_parse_int_value(department_id, "Department"),
        date_from=_parse_date_value(date_from),
        date_to=_parse_date_value(date_to),
        limit=300,
    )
    return _render(
        request,
        "admin/resource_list.html",
        current_admin=current_admin,
        service=service,
        page_title="Performance Records",
        page_description="Inspect and submit simple team-based daily performance records as the technical super admin.",
        filters_form={
            "action": "/admin/performance/records",
            "submit_label": "Apply filters",
            "method": "get",
            "fields": [
                _field(
                    name="department_id",
                    label="Department",
                    field_type="select",
                    value=department_id or "",
                    options=_model_options(
                        departments,
                        blank_label="All departments",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    options=_model_options(
                        teams,
                        blank_label="All teams",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="date_from", label="Date from", field_type="date", value=date_from or ""),
                _field(name="date_to", label="Date to", field_type="date", value=date_to or ""),
            ],
        },
        create_form={
            "action": "/admin/performance/records",
            "submit_label": "Submit record",
            "title": "Submit Daily Performance",
            "fields": [
                _field(
                    name="team_id",
                    label="Team",
                    field_type="select",
                    value=team_id or "",
                    required=True,
                    options=_model_options(
                        teams,
                        blank_label="Select team",
                        label_getter=lambda item: f"{item.code} - {item.name}",
                    ),
                ),
                _field(name="performance_date", label="Performance date", field_type="date", required=True),
                _field(name="achieved_value", label="Achieved value", field_type="number", required=True),
            ],
        },
        table=_table(
            [
                {"key": "performance_date", "label": "Date"},
                {"key": "team", "label": "Team"},
                {"key": "objective_value", "label": "Objective"},
                {"key": "achieved_value", "label": "Achieved"},
                {"key": "performance_percentage", "label": "Performance %"},
            ],
            [
                {
                    "performance_date": str(record.performance_date),
                    "performance_date_url": f"/admin/performance/records/{record.id}",
                    "team": team_map[record.team_id].name if record.team_id in team_map else record.team_id,
                    "objective_value": record.objective_value,
                    "achieved_value": record.achieved_value,
                    "performance_percentage": record.performance_percentage,
                }
                for record in records
            ],
        ),
    )


@router.post("/performance/records")
async def admin_performance_records_create(
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    form = await request.form()
    try:
        service.validate_csrf_token_for_user(_clean(form.get("csrf_token")), current_admin)
        payload = TeamDailyPerformanceCreateRequest(
            team_id=_clean(form.get("team_id"), blank_to_none=False),
            performance_date=_clean(form.get("performance_date"), blank_to_none=False),
            achieved_value=_clean(form.get("achieved_value"), blank_to_none=False),
        )
        record = service.submit_daily_performance(current_admin, payload)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/performance/records", message=str(exc), level="danger")

    return _redirect_with_message(
        f"/admin/performance/records/{record.id}",
        message="Performance record submitted successfully.",
        level="success",
    )


@router.get("/performance/records/{performance_id}", response_class=HTMLResponse)
def admin_performance_record_detail(
    performance_id: int,
    request: Request,
    service: AdminPanelService = Depends(get_admin_panel_service),
):
    current_admin = _current_admin(request, service)
    if current_admin is None:
        return _redirect_to_login(request)

    try:
        record = service.get_daily_performance_by_id(performance_id)
        team = service.get_team(record.team_id)
        user = service.get_user(record.created_by_user_id)
    except HANDLED_EXCEPTIONS as exc:
        return _redirect_with_message("/admin/performance/records", message=str(exc), level="danger")

    return _render(
        request,
        "admin/resource_detail.html",
        current_admin=current_admin,
        service=service,
        page_title=f"Performance {record.performance_date}",
        page_description="Read-only inspection of one stored team performance record.",
        back_url="/admin/performance/records",
        detail_fields=[
            {"label": "Team", "value": f"{team.code} - {team.name}"},
            {"label": "Performance date", "value": record.performance_date},
            {"label": "Objective value", "value": record.objective_value},
            {"label": "Achieved value", "value": record.achieved_value},
            {"label": "Performance percentage", "value": record.performance_percentage},
            {"label": "Created by", "value": f"{user.matricule} - {service.build_user_name(user)}"},
            {"label": "Created at", "value": record.created_at},
            {"label": "Updated at", "value": record.updated_at},
        ],
    )
