# Dashboard Module

## Purpose

The `dashboard` module provides aggregated read models for overview screens and reporting summaries across employees, requests, attendance, and performance.

## Key Files

- `app/apps/dashboard/service.py`
- `app/apps/dashboard/router.py`
- `app/apps/dashboard/schemas.py`

## Main Interfaces

- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/requests-summary`
- `GET /api/v1/dashboard/attendance-summary`
- `GET /api/v1/dashboard/performance-summary`
- `GET /api/v1/dashboard/employees-summary`

## How It Works

### Scope Resolution

The service determines what the current user is allowed to see based on:

- super-admin status
- dashboard management permission
- own employee record
- teams led
- department/team filters

### Aggregation

Once scope is resolved, the service builds summary queries against multiple domain tables and returns pre-shaped dashboard payloads.

## Dependencies

- `employees`
- `organization`
- `permissions`
- `requests`
- `attendance`
- `performance`

## Inputs and Outputs

### Inputs

- authenticated user context
- optional target date or date range filters
- optional team and department filters

### Outputs

- overview cards
- recent request slices
- attendance summaries
- performance summaries
- employee metrics

## Important Logic

- Dashboard visibility is broader than some request-detail visibility rules because leaders can see team-level operational summaries.
- The service blends several business areas into one read model layer used by both API clients and the admin overview.

## Issues Found

- Confirmed: `app/apps/dashboard/service.py` is large and contains a mix of scope resolution, SQL construction, and response shaping.
- Confirmed: no caching layer was found; summaries are computed live from operational tables.
- Likely: some helper paths cause repeated lookups and may become inefficient on larger datasets.
- Likely: dashboard and request visibility rules may diverge over time because both encode business visibility in different places.

## Recommendations

- Extract scope resolution into reusable helpers shared with other reporting paths.
- Add targeted performance checks for larger datasets.
- Consider cached or materialized read models if the dashboard becomes a frequently polled surface.
