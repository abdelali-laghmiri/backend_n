# Employees Module

## Purpose

The `employees` module manages employee records and ensures each employee has a linked `User` account for authentication.

## Key Files

- `app/apps/employees/models.py`
- `app/apps/employees/schemas.py`
- `app/apps/employees/service.py`
- `app/apps/employees/router.py`

## Main Interfaces

- employee listing and lookup
- employee creation
- employee update
- employee deactivation through `is_active`

## How It Works

### Creation Flow

Creating an employee also creates a linked `User` record. The service:

1. validates department, team, and job-title references
2. checks uniqueness across employee and user identity fields
3. generates a temporary password
4. creates the `User`
5. creates the `Employee`

### Update Flow

Updates keep employee and user identity fields synchronized. This is important because auth depends on the `users` table while business assignment data lives on `employees`.

## Dependencies

- `users` for linked account creation
- `organization` tables for department/team/job-title validation
- `app/core/security.py` for temporary password generation

## Inputs and Outputs

### Inputs

- employee profile fields
- organizational assignment IDs
- optional image path/URL field

### Outputs

- employee records
- linked user records
- one-time temporary password on create responses

## Important Logic

- Employee and user uniqueness checks are coordinated together.
- New linked users are created with `must_change_password=True`.
- The service prefers deactivation over deletion.

## Issues Found

- Confirmed: employee creation returns a temporary password, which is operationally useful but security-sensitive.
- Confirmed: the employee model stores only a string image field; actual file upload handling lives in the admin panel rather than inside this module.
- Likely: identity synchronization between employee and user records increases coupling and creates more update paths to reason about.
- Likely: there is no dedicated audit trail for employee master-data changes beyond normal row timestamps.

## Recommendations

- Keep the temporary-password handling path tightly controlled and document who can see it.
- Consider centralizing image/file concerns away from admin-panel route code.
- Add tests for employee/user synchronization edge cases.
- Decide whether employee deactivation is the only intended lifecycle path or whether explicit archival/deletion requirements exist.
