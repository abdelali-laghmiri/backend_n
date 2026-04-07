# Organization Module

## Purpose

The `organization` module models the company structure:

- departments
- teams
- job titles
- hierarchy views derived from those entities and active employee assignments

## Key Files

- `app/apps/organization/models.py`
- `app/apps/organization/schemas.py`
- `app/apps/organization/service.py`
- `app/apps/organization/router.py`

## Main Interfaces

- department CRUD
- team CRUD
- job-title CRUD
- `GET /api/v1/organization/hierarchy/me`
- `GET /api/v1/organization/hierarchy/company`

## How It Works

### Master Data

The module stores departments, teams, and job titles as separate tables with active/inactive flags and identifying codes.

### Hierarchy Resolution

Hierarchy endpoints build an in-memory view of the active organization using:

- department/team leadership assignments
- employee records
- active user accounts
- job-title hierarchy levels

The service then computes reporting relationships and company-tree output from that snapshot.

## Dependencies

- `employees` for employee assignments
- `users` for active user linkage
- `permissions` and `dashboard` consume organizational context indirectly

## Inputs and Outputs

### Inputs

- create and update payloads for departments, teams, and job titles
- the current authenticated user for scoped hierarchy views

### Outputs

- master-data records
- hierarchy trees and user-specific hierarchy summaries

## Important Logic

- Departments cannot be deactivated while active teams still belong to them.
- Team and job-title deactivation is handled with `is_active` rather than hard deletes.
- Hierarchy calculations use explicit business rules about nearest valid manager/leader rather than only raw foreign keys.

## Issues Found

- Confirmed: the service is large and manually coordinates many cross-table lookups.
- Confirmed from repository scan: no SQLAlchemy `relationship()` usage was found, so hierarchy logic depends on manual joins and repeated query patterns.
- Confirmed: a hierarchy test module exists, but a direct local `unittest` invocation timed out during this audit, so runtime verification of that area is incomplete here.
- Likely: hierarchy behavior is important enough that the current amount of service-local orchestration will become expensive to maintain as rules evolve.

## Recommendations

- Isolate hierarchy-building logic from CRUD logic into separate service components.
- Add more deterministic automated tests around manager resolution, inactive records, and mixed-role edge cases.
- Consider introducing helper query abstractions or relationships to reduce repeated manual data loading.
