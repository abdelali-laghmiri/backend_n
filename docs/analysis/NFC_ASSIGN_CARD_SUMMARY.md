# NFC_ASSIGN_CARD_SUMMARY

## 1. New permission added

The backend now defines a new permission:

- `attendance.nfc.assign_card`

This permission was added in two places:

- setup defaults in `app/apps/setup/service.py`
- an Alembic data migration in `alembic/versions/8f2c6d1a4b7e_seed_attendance_nfc_assign_card_permission.py`

Current assignment rules:

- super admin can use the endpoint through the existing super-admin permission bypass
- `RH_MANAGER` receives the new permission by default
- normal employees do not receive it
- `TEAM_LEADER` does not receive it
- `DEPARTMENT_MANAGER` does not receive it

## 2. New endpoint added

New endpoint:

- `POST /api/v1/attendance/nfc-cards/assign`

Protection:

- `require_permission("attendance.nfc.assign_card")`

Request body:

```json
{
  "employee_id": 12,
  "nfc_uid": "04AABBCCDD11"
}
```

Response body includes:

- NFC card id
- employee id
- employee matricule
- employee full name
- normalized `nfc_uid`
- `is_active`
- timestamps

The router stays thin:

- it checks the permission
- it calls `AttendanceService.assign_nfc_card(...)`
- it maps service errors to HTTP responses

## 3. Validation rules implemented

The assignment logic is in `AttendanceService.assign_nfc_card`.

Current validation steps:

1. load the employee by `employee_id`
2. reject if the employee does not exist
3. reject if the employee is inactive
4. normalize `nfc_uid` with `trim + uppercase`
5. check whether the same `nfc_uid` already exists
6. check whether the employee already has an active NFC card

Error cases handled:

- employee not found
  - `AttendanceNotFoundError`

- inactive employee
  - `AttendanceValidationError`

- NFC card already assigned to another employee
  - `AttendanceConflictError`

- employee already has another active NFC card
  - `AttendanceConflictError`

- same employee already has the same card but the stored card is inactive
  - `AttendanceValidationError`

## 4. How duplicate cards are handled

The service currently uses these rules:

- same employee + same active card
  - idempotent success
  - the existing row is returned
  - no duplicate row is created

- another employee already owns the same `nfc_uid`
  - rejected

- same employee already has a different active card
  - rejected

This keeps step 1 simple and safe.

The service does not yet deactivate old cards automatically.

## 5. How employee-card linking is enforced

The NFC card stays linked to:

- `employee_id`

This matches the current attendance design because attendance summaries and scan ingestion already work at the employee level.

When assignment is valid, the backend creates one `nfc_cards` row with:

- `employee_id`
- normalized `nfc_uid`
- `is_active = true`

Database-level protection:

- `nfc_uid` remains unique in the database

Service-level protection:

- one employee cannot receive a second active card through this endpoint
- one card cannot be attached to two employees

## 6. Files changed

- `app/apps/setup/service.py`
  - added the new permission to the default catalog
  - assigned it to `RH_MANAGER`

- `app/apps/attendance/schemas.py`
  - added the request schema for card assignment
  - added the response schema for NFC card assignment

- `app/apps/attendance/service.py`
  - added `assign_nfc_card`
  - added response builder and NFC lookup helpers used by the assignment flow

- `app/apps/attendance/router.py`
  - added `POST /attendance/nfc-cards/assign`

- `alembic/versions/8f2c6d1a4b7e_seed_attendance_nfc_assign_card_permission.py`
  - seeds the new permission for existing databases
  - assigns it to `RH_MANAGER`

- `tests/test_attendance_nfc.py`
  - added assignment-flow tests
  - added endpoint permission tests

## 7. What remains for future steps

This step only adds secure backend card attachment.

Not implemented yet:

- admin UI for attaching cards
- card replacement workflow
- card deactivation endpoint
- automatic re-assignment from old card to new card
- reader/device trust model
- NFC terminal registration
