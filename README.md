# HR Management Backend Skeleton

This project implements a modular HR management backend built with FastAPI, SQLAlchemy, Alembic, and Docker. The current codebase includes infrastructure, setup, authentication, organization, employees, permissions, and a generic requests engine foundation.

## Configuration

Application settings are centralized in `app/core/config.py` and loaded from `.env`.

- `DATABASE_URL` selects the active database when it is set.
- SQLite is the default local development database.
- If `DATABASE_URL` is left empty, the application builds a PostgreSQL URL from `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT`.
- Docker Compose keeps the same codebase and switches the backend to PostgreSQL through environment variables only.
- The setup module reads the first super admin bootstrap values from `SUPERADMIN_*` environment variables.
- Authentication uses `SECRET_KEY`, `JWT_ALGORITHM`, and `ACCESS_TOKEN_EXPIRE_MINUTES` from `.env`.

Create a local `.env` file before running anything:

```powershell
Copy-Item .env.example .env
```

## Run Locally With SQLite

Create a virtual environment, install dependencies, and start the API:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload
```

Open the application after startup:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health endpoint: `http://localhost:8000/health`
- Setup status endpoint: `http://localhost:8000/api/v1/setup/status`
- Internal admin dashboard login: `http://localhost:8000/admin/login`

## Run With Docker And PostgreSQL

Docker Compose starts:

- `backend`: the FastAPI application
- `postgres`: the PostgreSQL database

Start the stack:

```powershell
docker compose up --build
```

Stop the stack:

```powershell
docker compose down
```

Stop the stack and remove the PostgreSQL volume:

```powershell
docker compose down -v
```

Run migrations against the Docker PostgreSQL database:

```powershell
docker compose exec backend python -m alembic upgrade head
```

## Alembic Commands

Create a migration after real models are added:

```powershell
python -m alembic revision --autogenerate -m "describe_changes"
```

Apply all migrations:

```powershell
python -m alembic upgrade head
```

Revert the latest migration:

```powershell
python -m alembic downgrade -1
```

Show the current migration state:

```powershell
python -m alembic current
```

## System Initialization

The system starts uninitialized. Initialization is allowed only once and creates the first technical super admin from `.env`.

Required bootstrap variables:

- `SUPERADMIN_MATRICULE`
- `SUPERADMIN_PASSWORD`
- `SUPERADMIN_FIRST_NAME`
- `SUPERADMIN_LAST_NAME`
- `SUPERADMIN_EMAIL`

Check whether the system is already initialized:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/setup/status"
```

Initialize the system and create the first super admin:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/setup/initialize"
```

After a successful initialization, calling `POST /api/v1/setup/initialize` again returns a conflict response.

## Authentication

Authentication is based on the user account created during setup.

- Login uses `matricule` and `password`.
- Successful login returns a JWT bearer access token.
- Protected endpoints use `Authorization: Bearer <token>`.
- `must_change_password` stays `true` until the user changes the password through the authenticated password change endpoint.
- `/api/v1/auth/me` returns the effective permission set of the current user.
- Super admin receives full-access bypass automatically.

Login:

```powershell
$body = @{
    matricule = "SA-0001"
    password = "change-this-bootstrap-password"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/auth/login" `
    -ContentType "application/json" `
    -Body $body
```

Get the current authenticated user:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/auth/me" `
    -Headers @{ Authorization = "Bearer $token" }
```

Change the current password:

```powershell
$token = "paste-access-token-here"
$body = @{
    current_password = "change-this-bootstrap-password"
    new_password = "NewStrongPassword123!"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/auth/change-password" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

## Organization Module

The organization module manages the structural records used later by employees, approvals, and permissions.

- Departments can optionally reference a manager user.
- Teams belong to departments and can optionally reference a leader user.
- Job titles are independent organizational records with a non-negative hierarchy level.
- Route access is permission-driven with super-admin bypass.
- `organization.read` protects list and detail endpoints.
- `organization.create`, `organization.update`, and `organization.deactivate` protect write operations.
- Deactivation is soft and keeps the data available for future links.

Create a department:

```powershell
$token = "paste-access-token-here"
$body = @{
    name = "Human Resources"
    code = "HR"
    description = "People operations and administration"
    manager_user_id = 1
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/organization/departments" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Create a team:

```powershell
$token = "paste-access-token-here"
$body = @{
    name = "Talent Acquisition"
    code = "TA"
    description = "Recruitment team"
    department_id = 1
    leader_user_id = 1
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/organization/teams" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Create a job title:

```powershell
$token = "paste-access-token-here"
$body = @{
    name = "HR Director"
    code = "HR_DIRECTOR"
    description = "Department-level HR leadership"
    hierarchical_level = 3
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/organization/job-titles" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

List organization records:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/organization/departments" -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/organization/teams" -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/organization/job-titles" -Headers @{ Authorization = "Bearer $token" }
```

## Employees Module

The employees module manages HR/business profiles separately from authentication accounts.

- Creating an employee also creates a linked user account.
- The linked user account uses the employee matricule for login.
- Employee creation returns the generated temporary password once.
- The linked account is active by default and must change password on first login.
- Employee profiles store `available_leave_balance_days` for leave-request balance checks.
- Route access is permission-driven with super-admin bypass.
- `employees.read` protects list and detail endpoints.
- `employees.create` and `employees.update` protect write operations.

Create an employee:

```powershell
$token = "paste-access-token-here"
$body = @{
    matricule = "EMP-0001"
    first_name = "Aya"
    last_name = "Bennani"
    email = "aya.bennani@example.com"
    phone = "+212600000001"
    hire_date = "2026-03-23"
    available_leave_balance_days = 12
    department_id = 1
    team_id = 1
    job_title_id = 1
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/employees" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

List employees:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/employees?q=aya&include_inactive=false" `
    -Headers @{ Authorization = "Bearer $token" }
```

Update an employee:

```powershell
$token = "paste-access-token-here"
$body = @{
    phone = "+212600000099"
    available_leave_balance_days = 15
    department_id = 1
    team_id = 1
    job_title_id = 1
    is_active = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Patch `
    -Uri "http://localhost:8000/api/v1/employees/1" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

The employee creation response includes the generated login data:

```json
{
  "employee": {
    "id": 1,
    "user_id": 2,
    "matricule": "EMP-0001",
    "first_name": "Aya",
    "last_name": "Bennani",
    "email": "aya.bennani@example.com",
    "phone": "+212600000001",
    "hire_date": "2026-03-23",
    "available_leave_balance_days": 12,
    "department_id": 1,
    "team_id": 1,
    "job_title_id": 1,
    "is_active": true,
    "created_at": "2026-03-23T21:00:00Z",
    "updated_at": "2026-03-23T21:00:00Z"
  },
  "account": {
    "user_id": 2,
    "matricule": "EMP-0001",
    "email": "aya.bennani@example.com",
    "temporary_password": "generated-once",
    "must_change_password": true,
    "is_active": true
  }
}
```

## Permissions Module

The permissions module provides the access-control foundation for the rest of the backend.

- Super admin bypasses all permission checks.
- Normal users receive effective permissions through their employee job title.
- Permissions are assigned to job titles, not directly to users.
- Permission-management endpoints are restricted to the super admin in this first version.

Create a permission:

```powershell
$token = "paste-super-admin-access-token-here"
$body = @{
    code = "employees.create"
    name = "Create employees"
    description = "Allows creating employee profiles and linked accounts"
    module = "employees"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/permissions" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Assign permissions to a job title:

```powershell
$token = "paste-super-admin-access-token-here"
$body = @{
    permission_ids = @(1, 2, 3)
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Put `
    -Uri "http://localhost:8000/api/v1/permissions/job-titles/1" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

View the permissions assigned to a job title:

```powershell
$token = "paste-super-admin-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/permissions/job-titles/1" `
    -Headers @{ Authorization = "Bearer $token" }
```

Example route protection with the reusable dependency:

```python
from fastapi import APIRouter, Depends

from app.apps.permissions.dependencies import require_permission
from app.apps.users.models import User

router = APIRouter()


@router.get("/example")
def read_example(
    current_user: User = Depends(require_permission("employees.read")),
) -> dict[str, str]:
    return {"detail": f"Hello {current_user.matricule}"}
```

## Requests Engine Module

The requests module provides a database-driven workflow engine for HR requests.

- Request types, fields, and workflow steps are configured in the database.
- Configuration endpoints require `requests.manage` with super-admin bypass.
- Request submission requires an authenticated active user linked to an active employee profile.
- Workflow approver steps currently support `TEAM_LEADER`, `DEPARTMENT_MANAGER`, and `RH_MANAGER`.
- `RH_MANAGER` currently resolves the first active employee whose job title code is `RH_MANAGER`.
- Conception steps are supported and completed automatically by the workflow engine in this first version.
- Required unresolved approver steps block request creation or advancement.
- Optional unresolved approver steps are skipped automatically and recorded in history.
- When the request type code is `leave`, the backend expects active fields named `date_start`, `date_end`, and `leave_option`.
- Leave duration is computed as inclusive calendar days: `date_end - date_start + 1`.
- `paid leave` requires balance validation against the requester's `available_leave_balance_days`.
- `unpaid leave` and `CTT` do not require balance validation in this version.
- Leave balance is validated at submission time but is not deducted when the request is created.
- Leave request details include computed `leave_details` metadata for frontend use.

Create a request type:

```powershell
$token = "paste-access-token-here"
$body = @{
    code = "leave"
    name = "Leave Request"
    description = "Generic leave request workflow"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Create request fields:

```powershell
$token = "paste-access-token-here"
$dateStart = @{
    code = "date_start"
    label = "Start Date"
    field_type = "date"
    is_required = $true
    placeholder = "Select the first leave day"
    help_text = "Use ISO date format"
    sort_order = 1
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types/1/fields" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $dateStart

$dateEnd = @{
    code = "date_end"
    label = "End Date"
    field_type = "date"
    is_required = $true
    placeholder = "Select the last leave day"
    help_text = "Use ISO date format"
    sort_order = 2
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types/1/fields" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $dateEnd

$leaveOption = @{
    code = "leave_option"
    label = "Leave Option"
    field_type = "select"
    is_required = $true
    placeholder = "Choose paid leave, unpaid leave, or CTT"
    help_text = "Supported values: paid leave, unpaid leave, CTT"
    sort_order = 3
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types/1/fields" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $leaveOption

$reason = @{
    code = "reason"
    label = "Reason"
    field_type = "textarea"
    is_required = $false
    sort_order = 4
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types/1/fields" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $reason
```

Create workflow steps:

```powershell
$token = "paste-access-token-here"

$conception = @{
    step_order = 1
    name = "Initial HR check"
    step_kind = "conception"
    is_required = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types/1/workflow-steps" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $conception

$approval = @{
    step_order = 2
    name = "Team leader approval"
    step_kind = "approver"
    resolver_type = "TEAM_LEADER"
    is_required = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/types/1/workflow-steps" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $approval
```

Submit a paid leave request:

```powershell
$token = "paste-requester-access-token-here"
$body = @{
    request_type_id = 1
    values = @{
        date_start = "2026-04-01"
        date_end = "2026-04-03"
        leave_option = "paid leave"
        reason = "Family event"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Submit an unpaid leave request:

```powershell
$token = "paste-requester-access-token-here"
$body = @{
    request_type_id = 1
    values = @{
        date_start = "2026-05-12"
        date_end = "2026-05-14"
        leave_option = "unpaid leave"
        reason = "Personal travel"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Failed paid leave request because the employee balance is too low:

```powershell
$token = "paste-requester-access-token-here"
$body = @{
    request_type_id = 1
    values = @{
        date_start = "2026-06-01"
        date_end = "2026-06-10"
        leave_option = "paid leave"
        reason = "Extended vacation"
    }
} | ConvertTo-Json -Depth 5

try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8000/api/v1/requests" `
        -Headers @{ Authorization = "Bearer $token" } `
        -ContentType "application/json" `
        -Body $body
} catch {
    $_.ErrorDetails.Message
}
```

Expected error example:

```json
{
  "detail": "Paid Leave requires 10 day(s) but only 5 day(s) are available."
}
```

Approve the current request step:

```powershell
$token = "paste-approver-access-token-here"
$body = @{
    comment = "Approved."
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/1/approve" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Reject the current request step:

```powershell
$token = "paste-approver-access-token-here"
$body = @{
    comment = "Missing supporting document."
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/requests/1/reject" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

List the current user's requests:

```powershell
$token = "paste-requester-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/requests" `
    -Headers @{ Authorization = "Bearer $token" }
```

## Attendance Module

The attendance module receives external pointage scans, stores lightweight raw traceability events, maintains one daily summary per employee and date, and generates monthly reports from those daily summaries.

- The external pointage application sends scans to the backend through `POST /api/v1/attendance/scans`.
- The first version supports two reader types: `IN` and `OUT`.
- Employees are resolved explicitly by `matricule`.
- The attendance date follows the source-local date carried by `scanned_at`, while stored timestamps are normalized to UTC.
- Raw scan events are short-term traceability records and stay intentionally lightweight.
- Daily summaries are the main attendance source for ongoing usage.
- Monthly reports are generated from daily summaries and are stored for reporting convenience.
- `attendance.ingest` protects scan ingestion.
- `attendance.read` protects attendance read endpoints.
- `attendance.reports.generate` protects monthly report generation.
- For one employee and one date, the earliest `IN` becomes `first_check_in_at`.
- For one employee and one date, the latest `OUT` becomes `last_check_out_at`.
- `worked_duration_minutes` is computed as the difference between `first_check_in_at` and `last_check_out_at` when both are present and coherent.
- Day statuses are kept simple in this version:
  - `present`: both check-in and check-out exist and produce a valid duration
  - `incomplete`: only one side exists or the pair is incoherent
  - `absent`: reserved for future manual or automated population
  - `leave`: reserved for future leave-aware synchronization
- Monthly report totals are aggregated only from existing daily summaries in this version. Because there is no shift engine or leave automation yet, `total_absence_days` and `total_leave_days` stay `0` unless corresponding daily summaries already exist.
- Raw scan retention cleanup is not scheduled yet, but the raw events table is designed for future cleanup using `scanned_at` and `created_at`.

Send an `IN` scan event:

```powershell
$token = "paste-ingestion-access-token-here"
$body = @{
    matricule = "EMP-0001"
    reader_type = "IN"
    scanned_at = "2026-03-24T08:02:00Z"
    source = "nfc-reader-in"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/attendance/scans" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Send an `OUT` scan event:

```powershell
$token = "paste-ingestion-access-token-here"
$body = @{
    matricule = "EMP-0001"
    reader_type = "OUT"
    scanned_at = "2026-03-24T17:31:00Z"
    source = "nfc-reader-out"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/attendance/scans" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

List daily attendance summaries:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/attendance/daily-summaries?date_from=2026-03-01&date_to=2026-03-31&status=present" `
    -Headers @{ Authorization = "Bearer $token" }
```

Get one employee's daily attendance entries:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/attendance/employees/1/daily-summaries?date_from=2026-03-01&date_to=2026-03-31" `
    -Headers @{ Authorization = "Bearer $token" }
```

Generate monthly attendance reports:

```powershell
$token = "paste-access-token-here"
$body = @{
    report_year = 2026
    report_month = 3
    include_inactive = $false
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/attendance/monthly-reports/generate" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

List monthly attendance reports:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/attendance/monthly-reports?year=2026&month=3" `
    -Headers @{ Authorization = "Bearer $token" }
```

## Performance Module

The performance module provides simple team-based daily performance tracking.

- Performance is team-based only in this version.
- Objectives are configured per team.
- Each team should have one active objective at a time.
- Team leaders submit one achieved value per team and per day.
- One daily performance record is allowed per team and date.
- Daily performance snapshots copy the active objective value into the stored record.
- `performance_percentage` is stored on a `0-100` scale.
  - Example: `85.0` means 85 percent.
  - Values above `100.0` are allowed when the achieved value exceeds the objective.
- Objective management is admin-oriented and protected by `performance.manage`.
- Performance read endpoints require authentication.
  - Super admin and users with `performance.read` or `performance.manage` can read all teams.
  - Other authenticated users can read only the teams they lead.
- Daily performance submission requires an authenticated user who is either:
  - the configured team leader
  - or the super admin

Create a team objective:

```powershell
$token = "paste-admin-access-token-here"
$body = @{
    team_id = 1
    objective_value = 120
    objective_type = "tickets"
    is_active = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/performance/objectives" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Update a team objective:

```powershell
$token = "paste-admin-access-token-here"
$body = @{
    objective_value = 140
    objective_type = "tickets"
    is_active = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Patch `
    -Uri "http://localhost:8000/api/v1/performance/objectives/1" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Submit daily performance:

```powershell
$token = "paste-team-leader-access-token-here"
$body = @{
    team_id = 1
    performance_date = "2026-03-24"
    achieved_value = 102
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/performance/daily-performances" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

List performance by team:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/performance/daily-performances?team_id=1" `
    -Headers @{ Authorization = "Bearer $token" }
```

Query performance by date range:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/performance/daily-performances?date_from=2026-03-01&date_to=2026-03-31" `
    -Headers @{ Authorization = "Bearer $token" }
```

Get daily performance for one team and day:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/performance/teams/1/daily-performances/2026-03-24" `
    -Headers @{ Authorization = "Bearer $token" }
```

## Dashboard Module

The dashboard module is a read-only aggregation layer on top of the existing employees, requests, attendance, and performance modules.

- It does not create or modify business data.
- It exposes frontend-friendly summary endpoints for overview pages, widgets, and chart data.
- It supports practical filters such as `date`, `date_from`, `date_to`, `team_id`, and `department_id` where relevant.
- All dashboard endpoints require an authenticated user.
- Super admin always gets full dashboard scope.
- Users with `dashboard.read` or `dashboard.manage` also get full dashboard scope.
- Other authenticated users receive a limited scope:
  - requests: their own requests, requests they currently need to approve, and requests from teams they lead
  - attendance and employees: their own employee scope and teams they lead
  - performance: only teams they lead

Fetch the global dashboard overview:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/dashboard/overview?date=2026-03-24" `
    -Headers @{ Authorization = "Bearer $token" }
```

Fetch the requests dashboard summary:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/dashboard/requests-summary?date_from=2026-03-01&date_to=2026-03-31&recent_limit=5" `
    -Headers @{ Authorization = "Bearer $token" }
```

Fetch the attendance dashboard summary:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/dashboard/attendance-summary?date=2026-03-24&date_from=2026-03-18&date_to=2026-03-24" `
    -Headers @{ Authorization = "Bearer $token" }
```

Fetch the performance dashboard summary:

```powershell
$token = "paste-access-token-here"

Invoke-RestMethod `
    -Method Get `
    -Uri "http://localhost:8000/api/v1/dashboard/performance-summary?date=2026-03-24" `
    -Headers @{ Authorization = "Bearer $token" }
```

## Internal Admin Dashboard

The internal admin dashboard is a server-rendered control panel for the technical super admin only.

- It is not public-facing.
- It is not a raw database browser.
- It manages business data through safe application-level forms and read-only inspection pages.
- It uses a dedicated cookie-based admin session on top of the existing authentication accounts.
- Only active `is_super_admin=true` accounts can sign in.

Main access points:

- Login page: `http://localhost:8000/admin/login`
- Dashboard home: `http://localhost:8000/admin`

How login works:

- Initialize the system first through the setup module if no super admin exists yet.
- Sign in on `/admin/login` with the existing super admin matricule and password.
- The admin dashboard stores a signed HttpOnly cookie scoped to `/admin`.
- The public API keeps using bearer tokens and is not replaced by the admin session.

Main admin sections:

- Users
- Employees
- Departments
- Teams
- Job Titles
- Permissions
- Request Types
- Request Fields
- Request Steps
- Requests
- Attendance Daily Summaries
- Attendance Monthly Reports
- Performance Objectives
- Performance Records

Practical usage notes:

- Employee creation from the admin UI returns the generated temporary password once on the response page.
- Request pages are inspection-focused and expose submitted values, current workflow step, workflow progress, and action history.
- Attendance pages are inspection-focused and allow monthly report generation.
- Performance pages allow objective management and daily record submission.

Open the admin dashboard after the API is running:

```powershell
Start-Process "http://localhost:8000/admin/login"
```
