# Attendance Module

## Purpose

The `attendance` module handles workforce presence tracking through:

- raw scan ingestion
- NFC card assignment
- daily summary generation
- monthly report generation

## Key Files

- `app/apps/attendance/models.py`
- `app/apps/attendance/schemas.py`
- `app/apps/attendance/service.py`
- `app/apps/attendance/router.py`

## Main Interfaces

- `POST /api/v1/attendance/scans`
- `POST /api/v1/attendance/nfc-scans`
- `POST /api/v1/attendance/nfc-cards/assign`
- attendance daily-summary listing and detail endpoints
- monthly report generation and retrieval endpoints

## How It Works

### Scan Ingestion

Scan events are recorded in `attendance_raw_scan_events`. The service then updates or creates the relevant daily summary row for the employee and date.

### Daily Summary Logic

The module tracks items such as:

- first check-in
- last check-out
- worked minutes
- attendance status

### NFC Support

NFC cards are assigned to employees, and NFC scan ingestion resolves the employee through the active card.

### Monthly Reporting

Monthly reports aggregate day-level attendance summaries for a target employee and month.

## Dependencies

- `employees` for employee identity resolution
- `permissions` for ingest, read, and reporting guards
- possible conceptual linkage to `requests` for leave, though the actual runtime integration is limited

## Inputs and Outputs

### Inputs

- scan payloads by matricule or NFC card
- monthly report generation requests
- query filters for summary and report retrieval

### Outputs

- stored raw scan events
- updated daily summaries
- generated monthly report aggregates

## Important Logic

- Earliest daily IN becomes `first_check_in_at`.
- Latest daily OUT becomes `last_check_out_at`.
- Worked minutes are calculated only when the scan sequence is coherent.
- NFC assignment logic enforces one active card mapping per employee/card combination.

## Issues Found

- Confirmed: `AttendanceDailySummary` has a `linked_request_id` field, but the attendance service writes `linked_request_id=None` in the normal summary creation path and no linkage logic was found.
- Confirmed: no retention or cleanup strategy for `attendance_raw_scan_events` was found in the repository scan.
- Confirmed: attendance monthly reporting relies on previously built daily summaries rather than a richer calendar, shift, or approved-leave source.
- Confirmed: `tests/test_attendance_nfc.py` passed during this audit, but broader attendance coverage remains limited.

## Recommendations

- Define whether approved leave requests should populate `linked_request_id` and influence attendance states directly.
- Add retention or archival strategy for raw scan events before that table grows large.
- Expand tests for worked-minute calculations, out-of-order scans, and monthly report edge cases.
- Document the intended rules for absence vs leave vs incomplete days.
