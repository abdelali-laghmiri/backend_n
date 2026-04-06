# Database Audit

## Scope

This audit covers schema structure, migration coverage, query patterns, and data-layer risks visible from the repository.

## Schema Inventory

### Core Identity

- `users`
- `employees`

### Organization and Authorization

- `departments`
- `teams`
- `job_titles`
- `permissions`
- `job_title_permissions`

### Setup and Operational Workflow

- `installation_state`
- `request_types`
- `request_type_fields`
- `request_workflow_steps`
- `requests`
- `request_field_values`
- `request_actions`

### Notifications and Operational Data

- `notifications`
- `nfc_cards`
- `attendance_raw_scan_events`
- `attendance_daily_summaries`
- `attendance_monthly_reports`
- `team_objectives`
- `team_daily_performances`

## Migration Audit

### Strengths

- Alembic is configured and populated with a meaningful migration history.
- Migrations exist for each major domain area.
- The container entrypoint uses a PostgreSQL advisory lock when running migrations, which is a solid operational safeguard.

### Findings

- Schema evolution appears to have been additive and tracked rather than unmanaged.
- Both SQLite and PostgreSQL are treated as first-class runtime possibilities.

## Data Modeling Audit

### Positive Observations

- Foreign keys are used broadly.
- Uniqueness and check constraints appear in important places such as performance and workflow tables.
- Setup wizard state is stored durably instead of living only in memory or sessions.

### Confirmed Findings

- No SQLAlchemy `relationship()` usage was found; services rely on manual queries and joins.
- `attendance_daily_summaries` includes `linked_request_id`, but the attendance service does not populate that field in its normal summary write path.
- Request and workflow data is properly normalized into type, field, step, request, value, and action tables, which is a strong design for configurability.

### Likely Risks

- Manual query assembly across modules will make cross-table consistency changes harder over time.
- SQLite-local and PostgreSQL-production behavior may drift in subtle ways unless both paths are exercised regularly.
- Raw scan-event growth could make attendance storage and query patterns heavier over time without archival policy.

## Query Audit

### Strengths

- Services often limit single-record lookups with `.limit(1)`.
- Dashboard and reporting logic uses SQL aggregates rather than loading everything into Python first.

### Weaknesses

- The same domain joins are manually rebuilt in multiple services.
- No shared query abstraction or reusable read-model layer exists.
- No explicit data-retention routine was found for high-volume operational tables such as raw attendance scans.

## Database Audit Conclusion

The schema foundation is credible and covers the domain well. The main database concern is not missing tables; it is the growing amount of manual cross-table logic living in services rather than in reusable query helpers or relationships.

## Recommended Database Priorities

1. Define the intended integration between approved leave requests and attendance summaries.
2. Add retention/archival strategy for raw attendance scans.
3. Introduce reusable query helpers for common cross-table lookups.
4. Exercise both SQLite and PostgreSQL behavior in automated verification if both are expected to remain supported.
