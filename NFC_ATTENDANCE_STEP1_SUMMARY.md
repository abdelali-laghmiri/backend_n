  # NFC_ATTENDANCE_STEP1_SUMMARY

  ## 1. What was added

  Step 1 adds backend support for NFC-based attendance identity.

  The backend can now ingest attendance scans in two ways:

  - existing matricule flow
    - `POST /api/v1/attendance/scans`
  - new NFC flow
    - `POST /api/v1/attendance/nfc-scans`

  The new NFC flow resolves the employee from `nfc_uid`, then reuses the same attendance ingestion logic that already stores:

  - a raw scan event
  - a daily attendance summary update

  The old matricule-based flow is still kept intact.

  ## 2. What files were changed

  ### Backend code

  - `app/apps/attendance/models.py`
    - added the new `NfcCard` model

  - `app/apps/attendance/schemas.py`
    - extracted shared scan fields into a base request schema
    - kept the existing matricule request schema
    - added a new NFC request schema

  - `app/apps/attendance/service.py`
    - added NFC-based scan ingestion
    - added NFC card to employee resolution helpers
    - extracted shared attendance ingestion into one reusable internal method
    - normalized attendance datetimes to UTC-aware values in memory to avoid mixed naive/aware comparisons

  - `app/apps/attendance/router.py`
    - added the new `POST /attendance/nfc-scans` endpoint

  - `app/db/base.py`
    - registered the new `NfcCard` model for SQLAlchemy metadata and Alembic discovery

  ### Migration

  - `alembic/versions/7b4c2d1e9f0a_create_nfc_cards_table.py`
    - creates the `nfc_cards` table

  ### Tests

  - `tests/test_attendance_nfc.py`
    - verifies the old matricule flow still works
    - verifies the new NFC flow works
    - verifies inactive-card and unknown-card validation

  ## 3. What new model/table was created

  ### New model

  - `NfcCard`

  ### New table

  - `nfc_cards`

  ### Fields added

  - `id`
  - `employee_id`
  - `nfc_uid`
  - `is_active`
  - `created_at`
  - `updated_at`

  ### Design choice

  The NFC card is linked to `employee_id`, not `user_id`.

  This matches the current attendance design better because:

  - attendance summaries are keyed by employee
  - scan ingestion already resolves to an `Employee`
  - the attendance raw event already stores `employee_id`

  ### Database rules

  - `nfc_uid` is unique
  - `employee_id` is indexed
  - `nfc_uid` is indexed and unique
  - `employee_id` has a foreign key to `employees.id`

  ## 4. What new endpoint was added

  ### Endpoint

  - `POST /api/v1/attendance/nfc-scans`

  ### Request payload

  ```json
  {
    "nfc_uid": "string",
    "reader_type": "IN",
    "scanned_at": "2026-03-29T21:10:31.987Z",
    "source": "external_pointage_app"
  }
  ```

  ### Validation behavior

  - `nfc_uid` is required
  - `nfc_uid` is trimmed and uppercased
  - `reader_type` must be `IN` or `OUT`
  - `scanned_at` must be a datetime
  - if `scanned_at` is naive, it is normalized to UTC
  - `source` is required and trimmed

  ### Permission

  The new endpoint uses the same permission as the existing scan endpoint:

  - `attendance.ingest`

  ## 5. How `nfc_uid` is resolved to an employee

  The new NFC flow in `AttendanceService` works like this:

  1. `ingest_nfc_scan_event` receives `AttendanceNfcScanIngestRequest`
  2. it calls `_get_active_employee_by_nfc_uid`
  3. `_get_active_employee_by_nfc_uid` calls `_get_nfc_card_by_uid`
  4. `_get_nfc_card_by_uid` loads the card from `nfc_cards`
  5. the service validates:
    - the NFC card exists
    - the NFC card is active
    - the linked employee exists
    - the linked employee is active
  6. once the employee is resolved, the service continues with the shared attendance ingestion flow

  ### Error cases handled

  - unknown `nfc_uid`
    - raises `AttendanceNotFoundError`

  - inactive NFC card
    - raises `AttendanceValidationError`

  - missing linked employee
    - raises `AttendanceValidationError`

  - inactive linked employee
    - raises `AttendanceValidationError`

  ## 6. How the NFC flow reuses the current attendance logic

  The main reuse point is the new internal method:

  - `_ingest_scan_for_employee`

  Both public ingestion methods now resolve an employee first, then call the same shared method:

  - `ingest_scan_event`
    - resolves employee by `matricule`
    - calls `_ingest_scan_for_employee`

  - `ingest_nfc_scan_event`
    - resolves employee by `nfc_uid`
    - calls `_ingest_scan_for_employee`

  The shared ingestion method still performs the existing attendance behavior:

  - compute attendance date from `scanned_at`
  - convert stored scan timestamp to UTC
  - create or load the daily summary
  - store one `AttendanceRawScanEvent`
  - update the daily summary with the earliest `IN` / latest `OUT` logic
  - recompute worked duration and status
  - commit the transaction

  This keeps the NFC implementation small and avoids duplicating the attendance update logic.

  ## 7. What remains for future steps

  This step only adds NFC identity support for attendance scans.

  The following work is still not implemented:

  - NFC card attachment API or admin UI
  - device or terminal registration
  - reader trust or device authentication
  - duplicate-scan protection
  - richer scan session logic
  - card replacement history workflows
  - leave-request integration through `linked_request_id`
  - frontend or mobile NFC support

  ## 8. Practical result after this step

  After these code changes:

  - the backend supports NFC-based attendance scans
  - `nfc_uid` can resolve an employee through `nfc_cards`
  - `POST /api/v1/attendance/nfc-scans` works
  - `POST /api/v1/attendance/scans` still works
  - both flows reuse the same attendance ingestion pipeline
