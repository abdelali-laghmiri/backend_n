# Frontend Implementation Guide

This document contains all tasks and API specifications needed to implement the new backend features in `frontend_new`.

## 1. Employee Contract Type

### API Endpoints (existing, add contract_type fields)

**GET /api/v1/employees**
```json
Response item: {
  "id": 1,
  "matricule": "EMP-0001",
  "first_name": "Aya",
  "last_name": "Bennani",
  "email": "aya.bennani@example.com",
  "phone": "+212600000001",
  "hire_date": "2026-03-23",
  "contract_type": "INTERNAL",           // NEW: "INTERNAL" | "EXTERNAL"
  "external_company_name": null,          // NEW: string | null
  "available_leave_balance_days": 12,
  "department_id": 1,
  "team_id": 1,
  "job_title_id": 1,
  "is_active": true,
  "created_at": "2026-03-23T10:00:00Z",
  "updated_at": "2026-03-23T10:00:00Z"
}
```

**POST /api/v1/employees**
```json
Request: {
  "matricule": "EMP-0002",
  "first_name": "Zakaria",
  "last_name": "El Fassi",
  "email": "zakaria@techsol.local",
  "hire_date": "2026-03-23",
  "contract_type": "EXTERNAL",           // NEW: required
  "external_company_name": "TechSolutions SARL", // REQUIRED if EXTERNAL
  "job_title_id": 1
}
```

**PATCH /api/v1/employees/{id}**
```json
Request: {
  "contract_type": "EXTERNAL",
  "external_company_name": "New Contractor Ltd"
}
```

### Validation Rules
- `contract_type` must be "INTERNAL" or "EXTERNAL"
- If `contract_type` is "EXTERNAL", `external_company_name` is required
- If `contract_type` is "INTERNAL", `external_company_name` must be null

### UI Tasks
1. Add contract_type dropdown to employee create/edit forms
2. Show external_company_name field only when EXTERNAL selected
3. Add validation: external_company_name required for EXTERNAL
4. Display contract_type badge in employee list/detail views
5. Add filter by contract_type in employee list

### Permissions
- `employees.view_contract_type` - View contract type and external company
- `employees.update_contract_type` - Modify contract type

---

## 2. Forgot Badge Request System

### New API Endpoints

#### Create forgot badge request
```
POST /api/v1/forgot-badge/requests
Permission: forgot_badge.create (all authenticated users)
```

**Request:**
```json
{
  "reason": "Forgot my badge at home"  // optional, max 1000 chars
}
```

**Response:**
```json
{
  "id": 1,
  "employee_id": 1,
  "user_id": 1,
  "status": "PENDING",
  "reason": "Forgot my badge at home",
  "requested_at": "2026-04-26T09:00:00Z",
  "handled_by_user_id": null,
  "handled_at": null,
  "nfc_card_id": null,
  "valid_for_date": null,
  "notes": null,
  "created_at": "2026-04-26T09:00:00Z",
  "updated_at": "2026-04-26T09:00:00Z"
}
```

#### List own requests
```
GET /api/v1/forgot-badge/requests/me
Permission: forgot_badge.view_own
```

**Response:** Array of ForgotBadgeRequestResponse

#### List all requests (admin)
```
GET /api/v1/forgot-badge/requests?status=PENDING&employee_id=1&date_from=2026-04-01&date_to=2026-04-30
Permission: forgot_badge.view_all
```

**Response:**
```json
[{
  "id": 1,
  "employee_id": 1,
  "employee_matricule": "EMP-0001",     // NEW field
  "employee_name": "Aya Bennani",        // NEW field
  "user_id": 1,
  "status": "PENDING",
  "reason": "Forgot my badge at home",
  "requested_at": "2026-04-26T09:00:00Z",
  "handled_by_user_id": null,
  "handled_at": null,
  "nfc_card_id": null,
  "valid_for_date": null,
  "notes": null,
  "created_at": "2026-04-26T09:00:00Z",
  "updated_at": "2026-04-26T09:00:00Z"
}]
```

#### Get one request
```
GET /api/v1/forgot-badge/requests/{id}
Permission: forgot_badge.view_all
```

#### Approve request + attach temporary NFC card
```
POST /api/v1/forgot-badge/requests/{id}/approve
Permission: forgot_badge.manage
```

**Request:**
```json
{
  "nfc_card_id": 5,
  "valid_for_date": "2026-04-26",
  "notes": "Temporary card for today only"
}
```

**Response:**
```json
{
  "request": {
    "id": 1,
    "employee_id": 1,
    "status": "APPROVED",
    "nfc_card_id": 5,
    "valid_for_date": "2026-04-26",
    "handled_by_user_id": 2,
    "handled_at": "2026-04-26T09:05:00Z"
  },
  "temporary_assignment": {
    "id": 1,
    "employee_id": 1,
    "nfc_card_id": 5,
    "forgot_badge_request_id": 1,
    "assigned_by_user_id": 2,
    "assigned_at": "2026-04-26T09:05:00Z",
    "valid_for_date": "2026-04-26",
    "status": "ACTIVE",
    "check_in_attendance_id": null,
    "check_out_attendance_id": null,
    "released_at": null
  }
}
```

#### Reject request
```
POST /api/v1/forgot-badge/requests/{id}/reject
Permission: forgot_badge.manage
```

**Request:**
```json
{
  "notes": "No temporary cards available today"  // optional
}
```

**Response:** ForgotBadgeRequestResponse with status "REJECTED"

#### Cancel own request
```
POST /api/v1/forgot-badge/requests/{id}/cancel
Permission: forgot_badge.create
```

**Request:**
```json
{
  "reason": "Found my badge"  // optional
}
```

**Response:** ForgotBadgeRequestResponse with status "CANCELLED"

#### Complete request
```
POST /api/v1/forgot-badge/requests/{id}/complete
Permission: forgot_badge.manage
```

**Request:**
```json
{
  "notes": "Session completed"  // optional
}
```

**Response:** ForgotBadgeRequestResponse with status "COMPLETED"

#### Release temporary NFC card manually
```
POST /api/v1/forgot-badge/temporary-cards/release?employee_id=1&valid_for_date=2026-04-26
Permission: attendance.nfc.release_temporary_card
```

**Response:** TemporaryNfcAssignmentResponse or null

---

### Request Statuses
- `PENDING` - Awaiting approval
- `APPROVED` - Temporary NFC card attached
- `REJECTED` - Request denied
- `COMPLETED` - Session finished normally
- `CANCELLED` - Cancelled by requester

### Temporary Assignment Statuses
- `ACTIVE` - Card assigned and usable
- `USED` - CHECK_OUT completed, card released
- `RELEASED` - Manually released
- `EXPIRED` - Expired without use

---

### Workflow
1. Employee creates forgot badge request
2. Admin views pending requests
3. Admin approves and attaches temporary NFC card
4. Employee uses temporary card for CHECK_IN/CHECK_OUT
5. System auto-releases after CHECK_OUT
6. Request status changes to COMPLETED

### UI Tasks

#### User-facing (Employee)
1. "I forgot my badge" button/link
2. Create request form (reason optional)
3. List of my requests with status
4. Cancel own pending/approved request

#### Admin-facing (HR/Attendance Manager)
1. List all forgot badge requests with filters (status, date, employee)
2. Approve request form (select NFC card, set valid date)
3. Reject request form (add notes)
4. Complete request form
5. Release temporary card manually
6. View temporary assignment details

### Permissions
- `forgot_badge.create` - Create and cancel own requests
- `forgot_badge.view_own` - View own requests
- `forgot_badge.view_all` - View all requests (admin)
- `forgot_badge.manage` - Approve/reject/complete requests
- `attendance.nfc.assign_temporary_card` - Attach temporary NFC card
- `attendance.nfc.release_temporary_card` - Manually release card

---

## 3. NFC Scan Display Enhancement

### Context for NFC scans
NFC scan responses should indicate whether the card used was:
- **Permanent card** - Regular employee NFC card
- **Temporary card** - Assigned via forgot badge request

### UI Tasks
1. In attendance scan logs/history, show badge type indicator
2. For temporary cards, show:
   - "Temporary" badge
   - Related forgot badge request ID
   - Valid for date
3. Include `is_temporary_card` flag where applicable in API responses

---

## 4. Permissions to Add

```
employees.view_contract_type    - View INTERNAL/EXTERNAL
employees.update_contract_type  - Modify contract type
forgot_badge.create             - Create own requests
forgot_badge.view_own           - View own requests
forgot_badge.view_all           - View all requests
forgot_badge.manage             - Approve/reject/complete
attendance.nfc.assign_temporary_card  - Assign temp NFC
attendance.nfc.release_temporary_card - Release temp NFC
```

---

## 5. Page Structure

### Employee Module
```
/employees                     - List with contract_type filter
/employees/new                 - Create with contract_type
/employees/:id                 - View with contract_type display
/employees/:id/edit            - Edit with contract_type
```

### Forgot Badge Module
```
/forgot-badge                  - User's own requests
/forgot-badge/new              - Create request
/forgot-badge/admin            - Admin list all requests
/forgot-badge/:id              - View request details
/forgot-badge/:id/approve      - Approve + assign temp card
/forgot-badge/:id/reject       - Reject request
/forgot-badge/:id/cancel       - Cancel own request (user)
/forgot-badge/:id/complete     - Mark completed (admin)
/forgot-badge/temp-cards      - Manage temporary cards
```

---

## 6. Component Checklist

### Contract Type Components
- [ ] ContractTypeBadge (INTERNAL/EXTERNAL display)
- [ ] ContractTypeSelect (dropdown for forms)
- [ ] ExternalCompanyField (conditional show/hide)
- [ ] EmployeeCard (with contract type badge)
- [ ] EmployeeFilters (with contract type filter)

### Forgot Badge Components
- [ ] ForgotBadgeButton ("I forgot my badge")
- [ ] ForgotBadgeRequestForm (reason textarea)
- [ ] ForgotBadgeRequestCard (status, date, actions)
- [ ] ForgotBadgeRequestList (user's own)
- [ ] AdminForgottenBadgeList (all requests, filters)
- [ ] ApproveRequestForm (NFC card select, date picker)
- [ ] RejectRequestForm (notes)
- [ ] TemporaryCardInfo (card UID, valid date, employee)
- [ ] TemporaryCardReleaseButton

### NFC Display Components
- [ ] PermanentCardBadge
- [ ] TemporaryCardBadge (with request link)
- [ ] ScanTypeIndicator (in attendance history)

---

## 7. State Management

Store forgot badge related state:
- User's own requests: `/forgot-badge/requests/me`
- All requests (admin): `/forgot-badge/requests`
- NFC cards for selection: existing `/api/v1/attendance/nfc-cards`
- Temporary assignments: from approve response

---

## 8. Error Handling

| Error | UI Message |
|-------|------------|
| `cannot approve request with status X` | "Only pending requests can be approved" |
| `cannot cancel request with status X` | "This request cannot be cancelled" |
| `already assigned to another employee` | "This NFC card is assigned to another employee today" |
| `already has an active temporary NFC card` | "This employee already has a temporary card for today" |
| `No active employee profile found` | "You don't have an employee profile" |
| `pending or approved request already exists` | "You already have a request for today" |

---

## 9. Testing Checklist

### Contract Type
- [ ] Create internal employee without company name
- [ ] Create external employee with company name
- [ ] Create external employee without company name (should error)
- [ ] Update internal to external without company (should error)
- [ ] Display contract type badge in list
- [ ] Filter by contract type

### Forgot Badge
- [ ] Create request as authenticated user
- [ ] View own requests list
- [ ] Cancel own pending request
- [ ] Admin views all requests
- [ ] Admin approves request with NFC card
- [ ] Admin rejects request with notes
- [ ] Use temporary card for CHECK_IN
- [ ] Use temporary card for CHECK_OUT
- [ ] Verify card auto-released after checkout
- [ ] Verify request status changes to COMPLETED
- [ ] Admin manually releases card
- [ ] Cannot approve already-approved request
- [ ] Cannot cancel other user's request

---

## 10. Migration Notes

When applying these changes to `frontend_new`:

1. **Database migration** - Run `alembic upgrade head` to apply:
   - `employees.contract_type` (default INTERNAL)
   - `employees.external_company_name`
   - `forgot_badge_requests` table
   - `temporary_nfc_assignments` table

2. **API token** - All endpoints require Bearer token (existing auth)

3. **Permission seeding** - New permissions auto-created via existing permission catalog setup

4. **Existing code** - No breaking changes to existing APIs