# Requests Module

## Purpose

The `requests` module is a configurable workflow engine for HR-style requests. It supports:

- request type definitions
- dynamic request fields
- ordered workflow steps
- request submission
- approval and rejection flows
- request history

It also contains leave-specific business rules on top of the generic engine.

## Key Files

- `app/apps/requests/models.py`
- `app/apps/requests/schemas.py`
- `app/apps/requests/service.py`
- `app/apps/requests/router.py`
- `app/apps/requests/leave_business.py`

## Main Interfaces

- request type CRUD
- request field CRUD
- workflow step CRUD
- request submission
- own request listing
- pending approvals
- approval history
- request detail
- approve/reject actions

## How It Works

### Configuration Layer

Administrators define:

- request types
- request fields
- workflow steps

This allows the module to behave like a generic request engine instead of a single hardcoded leave-request feature.

### Runtime Request Flow

When a user submits a request, the service:

1. validates the request type and active fields
2. validates the submitted values
3. applies leave-specific rules when the request type code is `leave`
4. stores the request and submitted field values
5. resolves the next approver from workflow configuration
6. records action history
7. sends notifications where appropriate

### Approval Resolution

Workflow approvers can be derived from roles such as:

- team leader
- department manager
- RH manager

The service also skips self-approval and can skip unresolved optional steps while recording that decision in history.

## Dependencies

- `employees` and `organization` for hierarchy and approver resolution
- `permissions` for route protection and visibility logic
- `notifications` for approval workflow messaging
- `leave_business.py` for leave-request rules

## Inputs and Outputs

### Inputs

- request type configuration payloads
- dynamic field definitions
- workflow step definitions
- submitted request values
- approval or rejection actions

### Outputs

- configured metadata for request types and steps
- request details with current state
- pending approval queues
- request action history

## Important Logic

- Leave validation reserves known field codes such as `date_start`, `date_end`, and `leave_option`.
- Paid leave balance is checked during submission for leave requests.
- Request visibility is not purely global; it depends on requester identity, approver role, and permission set.
- History is recorded as workflow actions progress.

## Issues Found

- Confirmed: `app/apps/requests/service.py` is one of the largest files in the repository and combines configuration CRUD, workflow execution, serialization, visibility, and notification coordination.
- Confirmed: no general pagination pattern was found for request listings; the main API list endpoints are not structured around page/offset contracts.
- Confirmed: leave balance checking exists at submission time, but no balance deduction path was found in this module.
- Confirmed: RH-manager resolution selects the first active employee/job-title match for `RH_MANAGER`, which is a simple policy for an area with important business implications.
- Likely: approved leave requests are not fully integrated into downstream attendance state, because the attendance service does not populate `linked_request_id` during normal summary writes.

## Recommendations

- Split metadata-management, workflow-engine, and read-model concerns into smaller services.
- Add pagination or cursoring for large request datasets.
- Define a clear downstream policy for leave balance updates and attendance synchronization.
- Make RH-manager selection rules explicit if multiple RH managers can exist.
- Expand tests around skipped steps, self-approval, optional approvers, and leave edge cases.
