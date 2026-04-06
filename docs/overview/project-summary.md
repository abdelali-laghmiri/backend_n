# Project Summary

## Executive Summary

This repository is a modular FastAPI HR management backend with an internal server-rendered admin panel. It combines operational APIs, setup/bootstrap flows, organizational hierarchy management, employee identity management, a configurable request workflow engine, attendance ingestion and reporting, team performance tracking, notifications, and dashboard aggregation in one deployable service.

The codebase is organized as a modular monolith rather than a distributed system. The modules are clearly separated at the folder level, but several services have grown large enough that they now behave like central orchestrators instead of narrow domain units.

## What Exists Today

- HTTP API under `/api/v1`
- Internal admin panel under `/admin`
- SQLAlchemy 2.0 persistence with Alembic migrations
- SQLite default for local development and PostgreSQL support for deployment
- JWT-based authentication and permission checks
- Dynamic request engine with configurable fields and workflow steps
- Attendance ingestion with NFC support and monthly report generation
- Team performance tracking
- In-app notifications with persisted records and websocket delivery

## Technical Profile

- Language: Python 3.12 runtime in Docker
- Web framework: FastAPI
- ORM/migrations: SQLAlchemy 2.0 and Alembic
- Templating: Jinja2 for the admin panel
- App server: Uvicorn
- Configuration: Pydantic settings loaded from `.env`
- Testing found in repo: `unittest`

## Main Functional Areas

| Area | What it covers | Main module(s) |
| --- | --- | --- |
| System bootstrap | First-install initialization, seed flows, setup wizard state | `setup` |
| Authentication | Login, current-user resolution, password change | `auth` |
| User identity | Core `users` table and auth-facing account fields | `users` |
| Organization model | Departments, teams, job titles, hierarchy views | `organization` |
| Employee records | Employee master data plus linked user creation | `employees` |
| Authorization catalog | Permission definitions and job-title assignments | `permissions` |
| Workflow requests | Request types, dynamic fields, workflow approvals, leave rules | `requests` |
| Attendance | Raw scan ingestion, NFC cards, daily summaries, monthly reports | `attendance` |
| Performance | Team objectives and daily performance records | `performance` |
| Notifications | Persisted inbox items and realtime websocket push | `notifications` |
| Aggregation | Dashboard summary endpoints and overview metrics | `dashboard` |
| Internal operations UI | Super-admin CRUD and setup wizard | `admin_panel` |

## Interfaces

- Public-ish API surface: `/api/v1/...`
- Internal browser UI: `/admin/...`
- Health endpoints: `/` and `/health`
- Static assets: `/static/...`
- Notification websocket: `/api/v1/notifications/ws`

There is no separate SPA, React app, or mobile app code in this repository. The only frontend code present is the Jinja-based admin panel with custom CSS and a small amount of vanilla JavaScript.

## Data Layer Summary

The schema includes these main table groups:

- Core identity: `users`, `employees`
- Organization: `departments`, `teams`, `job_titles`
- Authorization: `permissions`, `job_title_permissions`
- Setup state: `installation_state`
- Requests engine: `request_types`, `request_type_fields`, `request_workflow_steps`, `requests`, `request_field_values`, `request_actions`
- Notifications: `notifications`
- Attendance: `nfc_cards`, `attendance_raw_scan_events`, `attendance_daily_summaries`, `attendance_monthly_reports`
- Performance: `team_objectives`, `team_daily_performances`

## Current Maturity Snapshot

### Stronger Areas

- Core FastAPI application bootstrap is clean and easy to follow.
- Configuration handling is stricter than average, especially around CORS origin validation and database URL normalization.
- Domain modules generally use Pydantic schemas and service classes rather than embedding all logic directly in routers.
- Alembic coverage is broad; the schema history is represented in migrations.

### Weaker Areas

- Some modules are significantly larger than their responsibilities justify, especially `admin_panel`, `requests`, `setup`, `dashboard`, and `organization`.
- The `users` module is mostly a table definition plus status endpoint; most real user behavior lives elsewhere.
- Realtime notifications are process-local and are not ready for horizontally scaled deployments.
- The audit found multiple places where design intent exists in the schema or seed data but is not fully enforced in runtime behavior.

## Verification Snapshot

Local verification during this audit was limited but useful:

- `tests/test_attendance_nfc.py` passed locally during the audit run.
- `tests/test_organization_hierarchy.py` exists, but the direct `unittest` invocation timed out in this environment before a clean pass/fail result was obtained.
- No CI workflow, lint configuration, type-check configuration, or broader test harness was found in the repository scan.

## Confirmed High-Signal Findings

- `app/apps/users/service.py` is a placeholder with no implemented behavior.
- `SetupService.get_readiness_summary()` currently returns hardcoded `database_ready=True` and `migrations_ready=True`.
- Attendance summaries include a `linked_request_id` field in the model and schema, but the attendance service writes `linked_request_id=None` in the normal summary update path.
- The setup seed includes the `admin_panel.access` permission code, but admin-panel access is actually enforced through `is_super_admin`.

## Overall Assessment

The repository is a credible modular backend foundation with real business logic already implemented. It is not just a skeleton. The strongest parts are the domain coverage, migration support, permission-oriented design, and the practical admin panel for operations.

The main risks are maintainability and operational hardening rather than total architectural failure. The project would benefit most from narrowing oversized modules, tightening security and auth-adjacent behavior, improving verification coverage, and aligning seeded concepts with what the runtime actually enforces.
