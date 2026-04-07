# Users Module

## Purpose

The `users` module defines the core authentication account model used across the system.

## Key Files

- `app/apps/users/models.py`
- `app/apps/users/schemas.py`
- `app/apps/users/router.py`
- `app/apps/users/service.py`

## Main Interfaces

- `GET /api/v1/users/status`

## How It Works

In practice, this module mostly supplies the `User` table and shared schema types. Most real account behavior is implemented elsewhere:

- `auth` performs login and password changes
- `employees` creates linked users for employee records
- `setup` bootstraps the first super admin and operational accounts
- `admin_panel` exposes CRUD views over users

## Dependencies

- Used directly by `auth`, `employees`, `setup`, `permissions`, `dashboard`, `requests`, `performance`, and `admin_panel`

## Inputs and Outputs

### Inputs

- direct user CRUD does not really live here today

### Outputs

- the `users` table and basic status response

## Important Logic

The main business meaning lives in the `User` model fields:

- identity fields such as matricule and email
- security fields such as `password_hash`, `is_active`, and `must_change_password`
- authorization shortcut field `is_super_admin`

## Issues Found

- Confirmed: `app/apps/users/service.py` contains only a placeholder `UsersService` with `pass`.
- Confirmed: the router only exposes a status endpoint, so the module is not a true standalone domain despite its central table.
- Likely: user-related responsibilities are now distributed across several modules, which weakens the boundary and makes future user-account changes harder to contain.

## Recommendations

- Either formalize this as the real user-account module or collapse the placeholder boundary and document that user behavior intentionally lives elsewhere.
- Move cross-cutting account rules into one service layer to reduce duplication.
- Add user-focused tests if account behavior remains spread across multiple modules.
