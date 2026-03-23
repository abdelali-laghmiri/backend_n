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
$body = @{
    code = "start_date"
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
    -Body $body
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

Submit a request:

```powershell
$token = "paste-requester-access-token-here"
$body = @{
    request_type_id = 1
    values = @{
        start_date = "2026-04-01"
        end_date = "2026-04-03"
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
