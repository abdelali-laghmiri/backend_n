# Admin Panel Module

## Purpose

The `admin_panel` module provides the internal browser-based operations dashboard. It is the only frontend code in the repository.

## Key Files

- `app/apps/admin_panel/router.py`
- `app/apps/admin_panel/service.py`
- `app/apps/admin_panel/schemas.py`
- `app/apps/admin_panel/dependencies.py`
- `app/templates/admin/*`
- `app/static/admin/admin.css`
- `app/static/admin/admin.js`

## Main Interfaces

- `/admin/login`
- `/admin/overview`
- setup wizard screens
- CRUD and detail screens for users, employees, departments, teams, job titles, permissions, requests, attendance reports, and performance records

## How It Works

### Authentication

The panel uses a signed JWT cookie named `admin_panel_access_token`. It also generates CSRF tokens as signed JWTs with a dedicated claim shape.

### Rendering

Routes gather data through `AdminPanelService` and render Jinja templates. Generic resource-list and resource-detail templates are reused across many admin pages.

### Service Delegation

`AdminPanelService` acts as a facade over:

- auth
- dashboard
- employees
- organization
- permissions
- requests
- attendance
- performance
- setup

### File Uploads

Employee image uploads are handled directly in the router and saved under `app/static/uploads/employees`.

## Dependencies

- almost every business module
- Jinja templates and static assets
- `app/core/security.py` for cookie and CSRF token handling

## Inputs and Outputs

### Inputs

- browser form submissions
- admin cookie token
- CSRF token
- optional image uploads for employees

### Outputs

- HTML pages
- redirects and flash-style messages
- locally saved uploaded files

## Important Logic

- Only super-admin users can access the admin panel.
- The panel reuses domain services rather than reimplementing business logic for each screen.
- Generic form/table helpers reduce template duplication.
- List pages often cap result sizes to fixed limits such as 200 or 300 records instead of implementing full paging.

## Issues Found

- Confirmed: `app/apps/admin_panel/router.py` is extremely large and combines routing, form parsing, validation, upload handling, view-model construction, and template rendering.
- Confirmed: `app/apps/admin_panel/service.py` is also large and acts as a multi-domain facade.
- Confirmed: access is enforced through `is_super_admin`, not through the seeded `admin_panel.access` permission code.
- Confirmed: employee image uploads are written to the local filesystem under static assets, which is fragile for ephemeral or horizontally scaled deployments.
- Confirmed: the router contains broad `except Exception:` cleanup paths around image handling.
- Likely: because the admin panel coordinates many domains, it will become one of the highest-friction files to change safely.

## Recommendations

- Split the router by resource area or extract helper modules for forms, uploads, and rendering concerns.
- Align access control with the permission model or explicitly document that admin access is super-admin-only by design.
- Move uploaded assets to managed storage if multi-instance deployment is a target.
- Add smoke tests for the most important admin flows, especially setup, login, employee editing, and request inspection.
