# Performance Module

## Purpose

The `performance` module tracks simple team-level objectives and daily achieved values.

## Key Files

- `app/apps/performance/models.py`
- `app/apps/performance/schemas.py`
- `app/apps/performance/service.py`
- `app/apps/performance/router.py`

## Main Interfaces

- objective creation/list/update/deactivation
- daily performance submission
- performance record listing and detail

## How It Works

### Objective Management

Objectives are created per team with:

- objective value
- optional objective type
- active/inactive state

When an objective is activated, the service deactivates other active objectives for the same team.

### Daily Performance Recording

One daily performance record is stored per team and date. The service calculates the performance percentage from achieved value versus the active objective.

## Dependencies

- `organization` for team validation
- `auth` and `permissions` for scoped access

## Inputs and Outputs

### Inputs

- team objective create/update payloads
- daily achieved-value submissions
- filters for listing objectives and daily records

### Outputs

- current and historical objective records
- calculated daily performance records

## Important Logic

- Team leaders and super admins can submit daily performance for teams they are allowed to manage.
- Daily records are unique per team/date.
- Objective values must be positive and achieved values non-negative.

## Issues Found

- Confirmed: the model defines `TeamObjectiveTypeEnum`, but the API schemas accept any normalized string for `objective_type` rather than restricting input to the enum.
- Confirmed: the module exposes useful business behavior but still centralizes most logic in one service file.
- Likely: because objective types are free-form at the API boundary, reporting consistency may drift over time unless the admin panel is the only writer.

## Recommendations

- Decide whether `objective_type` should be enum-restricted or intentionally free-form, then align models, schemas, and UI.
- Add tests for objective activation replacement and team-leader authorization edge cases.
- Add pagination if performance history is expected to grow materially.
