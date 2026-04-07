# Apps Inventory

## Module Map

| Module | Purpose | Main interfaces | Key files | Maturity snapshot |
| --- | --- | --- | --- | --- |
| `admin_panel` | Internal super-admin operations UI and setup wizard shell | `/admin/...` HTML routes | `app/apps/admin_panel/router.py`, `service.py` | Functionally rich, but oversized |
| `setup` | Bootstrap state, first super admin, installation wizard data and seeding | `/api/v1/setup/...`, admin setup wizard | `app/apps/setup/service.py`, `router.py`, `models.py` | Important and complex |
| `auth` | Login, token issuance, current user, password change | `/api/v1/auth/...` | `app/apps/auth/service.py`, `router.py`, `dependencies.py` | Focused, but security hardening needed |
| `users` | Core user account table and placeholder module shell | user model used across app, `/api/v1/users/status` | `app/apps/users/models.py`, `service.py` | Incomplete module boundary |
| `organization` | Departments, teams, job titles, hierarchy snapshots | `/api/v1/organization/...` | `app/apps/organization/service.py`, `router.py`, `models.py` | Rich domain logic, large service |
| `employees` | Employee CRUD and linked user lifecycle | `/api/v1/employees/...` | `app/apps/employees/service.py`, `router.py`, `models.py` | Solid base with some coupling |
| `permissions` | Permission catalog and job-title assignments | `/api/v1/permissions/...` | `app/apps/permissions/service.py`, `router.py`, `dependencies.py` | Clear and useful |
| `requests` | Dynamic workflow requests and leave rules | `/api/v1/requests/...` | `app/apps/requests/service.py`, `router.py`, `leave_business.py` | Powerful, but very large |
| `notifications` | Persisted notifications and realtime websocket delivery | `/api/v1/notifications/...`, websocket | `app/apps/notifications/service.py`, `router.py`, `realtime.py` | Useful, but not horizontally scalable |
| `announcements` | Company-wide internal news, attachments, and per-user seen tracking | `/api/v1/announcements/...` | `app/apps/announcements/service.py`, `router.py`, `models.py` | Focused V1 feature |
| `attendance` | Scan ingestion, NFC cards, daily summaries, monthly reports | `/api/v1/attendance/...` | `app/apps/attendance/service.py`, `router.py`, `models.py` | Mature feature area |
| `performance` | Team objectives and daily performance metrics | `/api/v1/performance/...` | `app/apps/performance/service.py`, `router.py`, `models.py` | Coherent, smaller scope |
| `dashboard` | Aggregated read models for overview screens and summaries | `/api/v1/dashboard/...`, admin overview | `app/apps/dashboard/service.py`, `router.py` | Useful aggregation layer, growing complex |

## Cross-Cutting Application Pieces

These are not domain modules, but they materially affect the whole system:

| Area | Role | Key files |
| --- | --- | --- |
| App bootstrap | FastAPI assembly, route inclusion, static mounting | `app/main.py`, `app/server.py` |
| Configuration | Env parsing, validation, database URL normalization | `app/core/config.py` |
| Database | SQLAlchemy engine, sessions, Alembic metadata registration | `app/core/database.py`, `app/db/base.py`, `alembic/env.py` |
| Security primitives | Password hashing and JWT helpers | `app/core/security.py` |
| Shared response layer | common response models and tags | `app/shared/*` |

## Feature Coverage Summary

### Backend APIs Present

- setup
- auth
- users status
- organization
- employees
- permissions
- requests
- notifications
- announcements
- attendance
- performance
- dashboard

### Frontend Present

- Internal server-rendered admin panel only

### Shared Utilities Present

- config handling
- database/session creation
- JWT and password utilities
- shared constants and response models

## Notable Gaps

- No separate client application exists in this repository.
- No dedicated repository/data-access abstraction exists between services and SQLAlchemy.
- The `users` app is not a fully realized module despite the importance of the underlying `users` table.
- No obvious CI, linting, or type-check pipeline was found during the repository scan.
