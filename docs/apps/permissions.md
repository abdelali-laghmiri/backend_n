# Permissions Module

## Purpose

The `permissions` module defines the authorization catalog and maps permissions to job titles.

## Key Files

- `app/apps/permissions/models.py`
- `app/apps/permissions/schemas.py`
- `app/apps/permissions/service.py`
- `app/apps/permissions/dependencies.py`
- `app/apps/permissions/router.py`

## Main Interfaces

- permission CRUD
- job-title permission assignment management
- dependency helpers such as `require_permission(...)`

## How It Works

### Permission Catalog

Permissions are stored as codes plus metadata. The setup module seeds a default catalog.

### Assignment Model

Permissions are assigned to job titles through the `job_title_permissions` table rather than being attached directly to users.

### Runtime Resolution

At runtime, effective permissions are derived from the current user's active employee and active job title. Super admins receive full access through the `is_super_admin` shortcut.

## Dependencies

- `organization` job-title data
- `employees` for linking users to organizational roles
- `auth` and most other modules consume permission checks

## Inputs and Outputs

### Inputs

- permission create/update payloads
- job-title assignment payloads
- authenticated users flowing through dependency helpers

### Outputs

- permission catalog records
- assignment records
- effective-permission payloads for current users

## Important Logic

- Permission code validation enforces module-style naming conventions.
- `require_permission(...)` and `require_any_permission(...)` provide consistent route protection patterns.
- Super-admin access bypasses normal permission enumeration.

## Issues Found

- Confirmed: permissions are attached to job titles only; no direct user override layer exists.
- Confirmed: the setup seed includes `admin_panel.access`, but the admin panel itself checks `is_super_admin` rather than that permission code.
- Confirmed: super-admin permission resolution returns full access semantically, but client code must understand that this comes from a bypass path rather than a populated permission list.

## Recommendations

- Decide whether job-title-only authorization is sufficient or whether per-user exceptions are needed.
- Align seeded permission concepts with runtime enforcement so the catalog reflects actual access control.
- Add focused tests around permission resolution for inactive employees, inactive job titles, and super-admin bypass behavior.
