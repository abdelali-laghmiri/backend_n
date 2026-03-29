# ATTENDANCE_SERVICE_ANALYSIS

Based only on the current backend code in:

- `app/apps/attendance/service.py`
- `app/apps/attendance/router.py`
- `app/apps/attendance/schemas.py`
- `app/apps/attendance/models.py`
- `app/apps/attendance/dependencies.py`
- supporting modules that the attendance code directly uses

## 1. Service overview

`AttendanceService` is the backend service layer for attendance ingestion and attendance reporting.

Its current responsibilities are:

- ingest one external scan event
- store one raw traceability record for that scan
- create or update one day-level attendance summary for the employee and date
- list daily summaries with filters
- list one employee's daily summaries
- generate or refresh monthly reports from existing daily summaries
- list monthly reports
- get one employee monthly report
- build API response objects with employee context

Main attendance flows already implemented:

1. External scan ingestion
   - `POST /attendance/scans`
   - resolves the employee by matricule
   - stores a raw scan event
   - updates the employee/day summary

2. Daily summary browsing
   - `GET /attendance/daily-summaries`
   - `GET /attendance/employees/{employee_id}/daily-summaries`

3. Monthly report generation
   - `POST /attendance/monthly-reports/generate`
   - aggregates existing daily summaries into one report per employee/month

4. Monthly report reading
   - `GET /attendance/monthly-reports`
   - `GET /attendance/employees/{employee_id}/monthly-reports/{year}/{month}`

What the service is not doing:

- it does not manage NFC cards
- it does not identify employees from card IDs
- it does not manage device registration or trusted readers
- it does not create schedules, shifts, lateness rules, overtime rules, or break sessions
- it does not automatically create absent-day rows for days with no scans
- it does not populate leave-linked attendance rows from the requests module

## 2. Important methods

### Public service methods

| Method | Purpose | Inputs | Outputs | Business rules | Side effects |
| --- | --- | --- | --- | --- | --- |
| `ingest_scan_event` | Main scan-ingestion entry point | `AttendanceScanIngestRequest` | `(AttendanceRawScanEvent, AttendanceDailySummary)` | Employee must exist and be active; attendance date is `payload.scanned_at.date()`; stored timestamp is UTC; scan updates earliest `IN` or latest `OUT` | Inserts raw event, creates or updates daily summary, commits transaction |
| `list_daily_summaries` | Query day summaries with filters | optional `employee_id`, `matricule`, `status`, `date_from`, `date_to`, `include_inactive` | `list[AttendanceDailySummary]` | Rejects invalid date range; blank matricule filter is ignored; inactive employees excluded by default | Read-only DB query |
| `get_employee_daily_summaries` | Query summaries for one employee | `employee_id`, optional date range | `list[AttendanceDailySummary]` | Employee must exist; method allows inactive employees because it calls `list_daily_summaries(..., include_inactive=True)` | Read-only DB query |
| `generate_monthly_reports` | Build or refresh monthly aggregates | `AttendanceMonthlyReportGenerateRequest` | `list[AttendanceMonthlyReport]` | Target employees depend on `employee_id` and `include_inactive`; report period is full month; aggregation uses only existing daily-summary rows | Inserts new reports or updates existing ones, commits transaction |
| `list_monthly_reports` | Query stored monthly reports | optional `employee_id`, `year`, `month`, `include_inactive` | `list[AttendanceMonthlyReport]` | Inactive employees excluded by default | Read-only DB query |
| `get_monthly_report` | Get one stored monthly report | `employee_id`, `report_year`, `report_month` | `AttendanceMonthlyReport` | Employee must exist; report must exist | Read-only DB query |
| `build_scan_ingest_response` | Build API response after ingestion | raw event and summary ORM objects | `AttendanceScanIngestResponse` | Adds employee matricule and full name to response | No persistence |
| `build_daily_summary_responses` | Build API DTOs for daily summaries | `list[AttendanceDailySummary]` | `list[AttendanceDailySummaryResponse]` | Bulk-loads employee records for enrichment | No persistence |
| `build_monthly_report_responses` | Build API DTOs for monthly reports | `list[AttendanceMonthlyReport]` | `list[AttendanceMonthlyReportResponse]` | Bulk-loads employee records for enrichment | No persistence |

### Core internal helper methods

| Method | Purpose | Inputs | Outputs | Business rules | Side effects |
| --- | --- | --- | --- | --- | --- |
| `_get_or_create_daily_summary` | Load or create one employee/day summary row | `employee_id`, `attendance_date` | `AttendanceDailySummary` | New rows start as `absent`, with no scans and `linked_request_id=None` | May insert a new summary row |
| `_apply_scan_to_daily_summary` | Apply one `IN` or `OUT` to the summary | summary, `reader_type`, `scanned_at` | `None` | `IN` keeps earliest timestamp; `OUT` keeps latest timestamp; unsupported reader type raises validation error; recomputes duration and status after every scan | Mutates summary fields |
| `_compute_worked_duration_minutes` | Calculate worked minutes | first check-in, last check-out | `int | None` | Returns `None` if one side is missing or `OUT < IN`; otherwise floor-divides total seconds into minutes | No persistence |
| `_derive_daily_summary_status` | Compute final daily status | `AttendanceDailySummary` | `AttendanceStatusEnum` | Both coherent scans => `present`; partial/incoherent scan data => `incomplete`; no scans and existing `leave` => `leave`; else `absent` | No persistence |
| `_resolve_report_target_employees` | Determine who should receive monthly reports | `employee_id`, `include_inactive` | `list[Employee]` | Specific inactive employee requires `include_inactive=true`; bulk generation excludes inactive employees by default | Read-only DB query |
| `_aggregate_monthly_totals` | Compute report totals from daily rows | `list[AttendanceDailySummary]` | `dict[str, int]` | Counts only rows that exist; `worked_days` means `worked_duration_minutes is not None`; incomplete days are not counted separately | No persistence |
| `_get_active_employee_by_matricule` | Resolve scan owner | `matricule` | `Employee` | Employee must exist and be active | Read-only DB query |
| `_validate_date_range` | Guard list filters | `date_from`, `date_to` | `None` | Raises validation error if `date_from > date_to` | No persistence |

## 3. Current scan flow

### 3.1 Ingestion path

Request path:

- `POST /api/v1/attendance/scans`
- router permission: `attendance.ingest`
- router method: `ingest_scan_event` in `app/apps/attendance/router.py`
- service method: `AttendanceService.ingest_scan_event`

Payload shape:

- `matricule`
- `reader_type`
- `scanned_at`
- `source`

Schema-level normalization:

- `matricule` is trimmed and uppercased
- `source` is trimmed
- if `scanned_at` is naive, the schema assigns UTC timezone

Service-level ingestion steps:

1. Resolve the employee with `_get_active_employee_by_matricule`.
2. Compute `attendance_date = payload.scanned_at.date()`.
3. Normalize stored timestamp with `payload.scanned_at.astimezone(timezone.utc)`.
4. Load or create the employee/day summary.
5. Insert one `AttendanceRawScanEvent`.
6. Apply the scan to the daily summary.
7. Commit both changes in one transaction.
8. Refresh and return both ORM objects.

Important date/time behavior:

- The summary date is taken from the original `payload.scanned_at.date()`.
- The stored scan timestamp is converted to UTC before persistence.
- This means the service treats the request payload as the source of the attendance day, then stores the actual timestamp in UTC.

### 3.2 How `IN` and `OUT` are handled

The service supports only two reader types:

- `IN`
- `OUT`

Rules in `_apply_scan_to_daily_summary`:

- `IN`
  - if `first_check_in_at` is empty, set it
  - if a new `IN` is earlier than the existing first check-in, replace it
  - result: the summary keeps the earliest `IN`

- `OUT`
  - if `last_check_out_at` is empty, set it
  - if a new `OUT` is later than the existing last check-out, replace it
  - result: the summary keeps the latest `OUT`

There is no sequence enforcement such as:

- no rule that first scan must be `IN`
- no rule that `OUT` must happen after an `IN`
- no alternating `IN` -> `OUT` -> `IN` logic
- no duplicate-scan protection

### 3.3 How daily summaries are updated

The summary row is one row per:

- `employee_id`
- `attendance_date`

Unique key:

- `(employee_id, attendance_date)`

When a new row is created, it starts with:

- `first_check_in_at = None`
- `last_check_out_at = None`
- `worked_duration_minutes = None`
- `status = absent`
- `linked_request_id = None`

After each scan:

1. the relevant check-in/check-out field is updated
2. `worked_duration_minutes` is recomputed
3. `status` is recomputed

Worked-duration rule:

- if both timestamps exist and `last_check_out_at >= first_check_in_at`
  - duration = floor of total seconds divided by 60
- otherwise
  - duration = `None`

Status rule:

- if at least one scan exists
  - if both timestamps exist and duration is valid: `present`
  - otherwise: `incomplete`
- if no scans exist
  - if current status is already `leave`: keep `leave`
  - otherwise: `absent`

Practical implication:

- a malformed or out-of-order day with both scans but `OUT < IN` becomes `incomplete`, not `absent`
- the `leave` status is only preserved when there are no scans

### 3.4 How monthly reports are generated

Request path:

- `POST /api/v1/attendance/monthly-reports/generate`
- router permission: `attendance.reports.generate`

Generation flow:

1. Resolve the target employees.
   - one employee if `employee_id` is provided
   - otherwise all employees, optionally excluding inactive ones
2. Build the month boundaries with `_get_month_date_range`.
3. Load all `AttendanceDailySummary` rows for those employees and that month.
4. Load existing `AttendanceMonthlyReport` rows for the same employees and month.
5. For each target employee:
   - create a new report row if missing
   - otherwise update the existing one
   - compute totals from the employee's daily summaries
6. Commit all reports in one transaction.

Aggregation rules:

- `total_worked_days`
  - count of daily summaries where `worked_duration_minutes is not None`
- `total_worked_minutes`
  - sum of `worked_duration_minutes or 0`
- `total_present_days`
  - count of summaries with status `present`
- `total_absence_days`
  - count of summaries with status `absent`
- `total_leave_days`
  - count of summaries with status `leave`

Important limitation:

- the report uses only daily-summary rows that already exist in the database
- the service does not generate missing calendar days
- so a day with no summary row is not counted as absent by this service

## 4. Related files

### Main attendance files

- `app/apps/attendance/router.py`
  - API endpoints
  - HTTP error mapping
  - permission gating

- `app/apps/attendance/service.py`
  - all attendance business logic
  - scan ingestion
  - day summary updates
  - monthly report generation
  - response builders

- `app/apps/attendance/schemas.py`
  - request and response DTOs
  - input normalization for `matricule`, `source`, and `scanned_at`

- `app/apps/attendance/models.py`
  - enums
  - raw scan event model
  - daily summary model
  - monthly report model

- `app/apps/attendance/dependencies.py`
  - FastAPI dependency that provides `AttendanceService`

### Supporting files directly involved

- `app/apps/employees/models.py`
  - attendance resolves employees from this model
  - summaries and reports are keyed by `employee_id`

- `app/apps/setup/service.py`
  - declares attendance permission codes:
    - `attendance.read`
    - `attendance.ingest`
    - `attendance.reports.generate`

- `app/apps/router.py`
  - registers the attendance router in the main API

- `app/main.py`
  - includes the app router under the API prefix

### Service reuse outside the attendance module

- `app/apps/admin_panel/service.py`
  - instantiates `AttendanceService`
  - delegates monthly report generation to it
  - shows the service is intended to be reused, not duplicated

### Helper files

There is no attendance-specific helper module comparable to `requests/leave_business.py`.

Attendance logic is currently concentrated in `app/apps/attendance/service.py`.

## 5. Data model usage

### `AttendanceRawScanEvent`

Purpose:

- short-term traceability record for each ingested scan

Fields used by the service:

- `employee_id`
- `user_id`
- `reader_type`
- `scanned_at`
- `source`
- `created_at`

How it is used:

- one row is inserted for every accepted scan
- it is returned immediately in the scan-ingest response
- there is no attendance API endpoint to list raw scan events later

### `AttendanceDailySummary`

Purpose:

- main day-level attendance record for ongoing attendance usage

Fields used by the service:

- `employee_id`
- `attendance_date`
- `first_check_in_at`
- `last_check_out_at`
- `worked_duration_minutes`
- `status`
- `linked_request_id`
- `created_at`
- `updated_at`

How it is used:

- one summary row per employee/day
- updated after every scan
- queried by read endpoints
- used as the source for monthly-report aggregation

### `AttendanceMonthlyReport`

Purpose:

- stored monthly aggregate generated from daily summaries

Fields used by the service:

- `employee_id`
- `report_year`
- `report_month`
- `total_worked_days`
- `total_worked_minutes`
- `total_present_days`
- `total_absence_days`
- `total_leave_days`
- `created_at`
- `updated_at`

How it is used:

- generated or refreshed on demand
- queried by list/get endpoints
- not calculated on the fly at read time

### Employee references

The service depends on `Employee` for:

- resolving the scan owner by `matricule`
- reading `employee.id`
- reading `employee.user_id` for raw events
- enriching responses with matricule and full name
- filtering active versus inactive records

Important detail:

- scan ingestion requires an active employee
- report reads can include inactive employees when requested
- employee-specific daily-summary reads also work for inactive employees because the code only checks that the employee exists

### `linked_request_id`

The `AttendanceDailySummary` model contains:

- `linked_request_id`

Current real behavior in the service:

- new summaries are created with `linked_request_id = None`
- responses expose the field
- no attendance method sets it
- no attendance method resolves approved leave requests and writes this field

So the field exists in the schema and database, but it is currently unused by `AttendanceService`.

## 6. Existing business rules

### Input validation rules

From schemas:

- `matricule`
  - required
  - trimmed
  - uppercased
  - max length 50

- `reader_type`
  - must be enum `IN` or `OUT`

- `scanned_at`
  - required datetime
  - if naive, timezone is set to UTC

- `source`
  - required nonblank string
  - trimmed
  - max length 120

- monthly report request
  - `report_year` must be between 2000 and 9999
  - `report_month` must be between 1 and 12
  - `employee_id`, if provided, must be >= 1

From service methods:

- `date_from` cannot be after `date_to`
- scan ingestion requires an active employee found by matricule
- requesting one inactive employee for report generation requires `include_inactive=true`

### Status computation rules

The current service supports these statuses:

- `present`
- `incomplete`
- `absent`
- `leave`

Actual computed behavior:

- `present`
  - both scan timestamps exist
  - worked duration is valid

- `incomplete`
  - one scan exists but the other is missing
  - or both exist but `OUT < IN`, so worked duration is `None`

- `absent`
  - no scans exist
  - and the summary is not already marked as `leave`

- `leave`
  - preserved only when there are no scans and the summary already has `leave`

Important code-level detail:

- the service defines `leave`
- but the service does not contain any method that creates or assigns `leave`

### Time calculation rules

- raw event timestamps are stored in UTC
- summary date is derived from the incoming `scanned_at` before UTC conversion
- worked duration is an integer number of minutes
- seconds are truncated with floor division
- negative durations are treated as invalid and stored as `None`

### Daily summary update rules

- the earliest `IN` wins
- the latest `OUT` wins
- every accepted scan is persisted as a raw event even if it does not change the summary fields
- status and duration are recomputed after each scan

### Report generation rules

- reports are generated from existing day summaries only
- one report row per employee/year/month
- existing rows are refreshed, not duplicated
- inactive employees are excluded by default
- there is no separate incomplete-day total in monthly reports

## 7. Reusable patterns for a future NFC attendance feature

These backend patterns are already clean and reusable:

### Thin router, thick service

- router handles request parsing, permission checks, and HTTP error mapping
- service owns business logic and DB mutations

This is the same style already used in the requests module.

### Explicit service errors

Attendance logic raises domain-specific errors:

- `AttendanceConflictError`
- `AttendanceNotFoundError`
- `AttendanceValidationError`

The router translates them into HTTP responses.

This is a good pattern to reuse for NFC-specific validation and device errors.

### Central state update helpers

The scan flow uses focused helpers:

- `_get_or_create_daily_summary`
- `_apply_scan_to_daily_summary`
- `_compute_worked_duration_minutes`
- `_derive_daily_summary_status`

For NFC, the same approach can be extended with helpers such as:

- card resolution
- device validation
- duplicate-scan detection
- shift-aware status derivation

### Stored raw event plus derived summary

This is the strongest reusable pattern in the current attendance design:

- keep a raw event table for traceability
- keep a derived summary table for day-level operations

That pattern fits NFC very well.

For NFC, the raw event could store:

- card UID or token
- reader/device identifier
- resolved employee
- scan direction or inferred action
- metadata for debugging

### On-demand monthly aggregation

The service already separates:

- event ingestion
- daily-summary maintenance
- monthly aggregation

That separation is good and should stay.

### Reusable response-building layer

The service builds response DTOs after core logic is done.

That keeps ORM and API formatting separate.

The same pattern can be reused for NFC scan responses.

### Service reuse from other modules

`AdminPanelService` reuses `AttendanceService` instead of re-implementing report logic.

This is a good sign that the service boundary is already usable from other backend features.

## 8. Gaps and limitations

These are the main current limitations visible in the code.

### No NFC identity model

The service identifies employees only by:

- `matricule`

It does not support:

- NFC card UID
- badge token
- card-to-employee mapping
- lost/replaced card history

### No reader/device trust model

The payload accepts a free-text `source`, but there is no:

- registered reader table
- device authentication
- device secret or signature validation
- site/door mapping

### No idempotency or duplicate-scan protection

Every accepted scan is stored as a new raw event.

There is no check for:

- duplicate submissions
- replayed scans
- very-close repeated taps

### No real scan session logic

The summary supports only:

- first `IN`
- last `OUT`

It does not support:

- multiple work sessions in one day
- break out / break in
- lunch handling
- anti-passback logic
- alternating reader validation

### No schedule-aware rules

The service does not calculate:

- lateness
- early leave
- overtime
- expected working hours
- shift compliance

Even though the notification enum contains `ATTENDANCE_LATE`, this attendance service does not create such notifications.

### Leave linkage is not implemented

The daily summary contains `linked_request_id`, but the service never sets it.

So the attendance module currently does not:

- mark approved leave days automatically
- generate leave summaries from the requests workflow
- connect attendance and request approval outcomes

### Monthly absence totals are limited by existing rows

This is a very important current limitation.

Because:

- daily summaries are created only when a scan is ingested
- monthly reports aggregate only existing daily summaries

the service does not infer absences for missing calendar days.

So `total_absence_days` is not "all days with no attendance"; it is only "summary rows whose status is `absent`".

### No raw-event read or cleanup workflow

The service stores raw events, but it does not provide:

- an API to browse raw events
- retention cleanup
- archival behavior

### No attendance tests were found

There are no attendance-specific tests under `tests/` in the current workspace.

That does not change runtime behavior, but it is a practical gap if NFC logic will add more edge cases.

## What would need to be added for NFC attendance

Based on the current design, a clean NFC extension would likely need:

1. An NFC card model
   - card UID/token
   - employee mapping
   - active/inactive state
   - audit history

2. Reader/device registration
   - trusted device identity
   - optional location/site
   - optional reader type or direction

3. A richer raw scan event
   - card identifier
   - reader identifier
   - resolved employee
   - original device payload
   - idempotency key if available

4. Stronger scan rules
   - deduplication window
   - sequence validation
   - anti-passback or repeated-tap handling
   - optional shift/schedule checks

5. Better daily attendance logic
   - multiple scan pairs or session records
   - break tracking if needed
   - lateness and overtime fields if required

6. Attendance/request integration
   - auto-mark leave days from approved leave requests
   - populate `linked_request_id`

7. Background operations
   - raw scan cleanup
   - scheduled monthly generation if needed

## Final technical assessment

The current `AttendanceService` is small, readable, and consistent with the rest of the backend style.

Its real design is:

- raw event ingestion
- single daily summary per employee/day
- simple earliest-`IN` / latest-`OUT` logic
- on-demand monthly aggregation from stored daily summaries

It is a good starting point for NFC attendance, but only for the base pipeline.

For a real NFC feature, the backend still needs:

- card identity management
- reader trust and validation
- duplicate protection
- richer attendance-session logic
- optional request/leave integration

Without those additions, NFC would only be a different way to send the same simple `matricule + IN/OUT + timestamp` payload into the current service.
