# Documentation and Audit Package

This folder contains a code-backed documentation and audit snapshot of the repository as inspected on 2026-04-06. The package was produced from the current source tree and limited local verification, not from assumptions about intended behavior.

## Reading Guide

- Start with `overview/project-summary.md` for the project-level picture.
- Read `architecture/global-architecture.md` and `architecture/folder-structure.md` for system shape and repository layout.
- Use `apps/apps-inventory.md` to navigate the domain modules.
- Read the per-module files in `apps/` for operational detail.
- Use the audit files under `backend/`, `frontend/`, `database/`, `security/`, `performance/`, and `audits/` for review and planning.

## Evidence Policy

- Confirmed finding: directly supported by repository code or by a local command run during this audit.
- Likely issue: strongly suggested by the codebase shape, but not fully proven by execution in this environment.
- Missing information: a point that could not be verified from the repository contents alone.

## Generated Structure

- `overview/project-summary.md`
- `architecture/global-architecture.md`
- `architecture/folder-structure.md`
- `apps/apps-inventory.md`
- `apps/admin-panel.md`
- `apps/attendance.md`
- `apps/auth.md`
- `apps/dashboard.md`
- `apps/employees.md`
- `apps/notifications.md`
- `apps/organization.md`
- `apps/performance.md`
- `apps/permissions.md`
- `apps/requests.md`
- `apps/setup.md`
- `apps/users.md`
- `backend/backend-audit.md`
- `frontend/frontend-audit.md`
- `database/database-audit.md`
- `security/security-audit.md`
- `performance/performance-audit.md`
- `audits/final-audit-summary.md`

## Existing Documentation Preserved

The following pre-existing files were left in place:

- `deployent_informations.md`
- `analysis/BACKEND_ANALYSIS.md`
- `analysis/ATTENDANCE_SERVICE_ANALYSIS.md`
- `analysis/NFC_ASSIGN_CARD_SUMMARY.md`
- `analysis/NFC_ATTENDANCE_STEP1_SUMMARY.md`

Those files may still be useful as historical notes, but this package should be treated as the current structured review.
