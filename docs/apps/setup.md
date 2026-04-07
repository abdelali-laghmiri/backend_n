# Setup Module

## Purpose

The `setup` module controls first-install bootstrap and the multi-step installation wizard. It is responsible for:

- creating the initial super-admin account from environment variables
- persisting installation progress
- seeding the permission catalog
- seeding default job-title permission assignments
- guiding initial organization and operational-user setup

## Key Files

- `app/apps/setup/models.py`
- `app/apps/setup/schemas.py`
- `app/apps/setup/service.py`
- `app/apps/setup/router.py`

## Main Interfaces

- `GET /api/v1/setup/status`
- `POST /api/v1/setup/initialize`
- admin panel setup wizard pages under `/admin/setup/...`

## How It Works

### Installation State

The module stores durable setup state in the `installation_state` table. That record holds:

- whether installation is complete
- when it completed
- which user completed it
- wizard progress in a JSON field

### Bootstrap Super Admin

`initialize_system()` reads `SUPERADMIN_*` values from configuration and creates the first super-admin `User` when the system is still uninitialized.

### Wizard Steps

The service manages staged setup data for:

- readiness
- organization structure
- job titles
- permission catalog and job-title mappings
- operational users
- review/completion

### Seed Logic

The module defines the default permission codes and job-title permission bundles in code. It also upserts operational users for predefined business roles during setup.

## Dependencies

- `users` for the super-admin account
- `organization` concepts for departments, teams, and job titles
- `permissions` for the permission catalog and assignments
- `employees` for operational user creation
- app settings for bootstrap values

## Inputs and Outputs

### Inputs

- environment variables such as `SUPERADMIN_MATRICULE`, `SUPERADMIN_PASSWORD`, and related fields
- wizard step payloads from API/admin submissions

### Outputs

- setup status payloads
- persisted installation wizard state
- created bootstrap and operational user records
- seeded permissions and assignments

## Important Logic

- The module prevents duplicate initialization once the system is already initialized.
- It uses review-summary checks before completing installation.
- Job-title permission assignments are derived from default permission bundles.
- Operational-user seeding updates existing records when possible instead of only inserting new rows.

## Issues Found

- Confirmed: `SetupService.get_readiness_summary()` currently returns `database_ready=True` and `migrations_ready=True` as hardcoded values rather than proving readiness dynamically.
- Confirmed: the service is large and mixes workflow orchestration, seeding, validation, user creation, and summary generation in one file.
- Likely: because core installation policy is encoded directly in Python constants, changes to organizational defaults or role bundles require code deployment rather than a narrower configuration path.

## Recommendations

- Replace hardcoded readiness flags with real checks for database connectivity and migration state.
- Split the service into narrower components such as bootstrap, wizard state, and permission seeding.
- Document or externalize default seed policy where business administrators are expected to change it over time.
- Add targeted tests for each setup step and completion guard.
