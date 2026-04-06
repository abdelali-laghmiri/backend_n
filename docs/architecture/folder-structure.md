# Folder Structure

## Top-Level Layout

```text
.
|-- app/
|   |-- apps/
|   |-- core/
|   |-- db/
|   |-- shared/
|   |-- static/
|   `-- templates/
|-- alembic/
|   `-- versions/
|-- docs/
|-- scripts/
|-- tests/
|-- .env.example
|-- Dockerfile
|-- docker-compose.yml
|-- fly.toml
|-- Procfile
|-- README.md
`-- requirements.txt
```

## `app/`

This is the runtime application package.

### `app/main.py`

Builds the FastAPI application, configures CORS when allowed origins are provided, mounts static files, includes the admin router, and includes the versioned API router.

### `app/server.py`

Production-oriented startup entrypoint that runs Uvicorn and respects an injected `PORT`.

### `app/core/`

Cross-cutting infrastructure:

- `config.py`: environment parsing and validation
- `database.py`: SQLAlchemy engine and session factory
- `dependencies.py`: app-level FastAPI dependencies
- `security.py`: password hashing and JWT helpers

### `app/db/`

- `base.py`: imports all models so Alembic can see the metadata graph

### `app/shared/`

Shared constants, enums, and response models reused across modules.

### `app/apps/`

Business modules:

- `admin_panel`
- `attendance`
- `auth`
- `dashboard`
- `employees`
- `notifications`
- `organization`
- `performance`
- `permissions`
- `requests`
- `setup`
- `users`

Each module generally contains `models.py`, `schemas.py`, `service.py`, `router.py`, and `dependencies.py`.

### `app/templates/admin/`

Jinja templates for the internal admin panel:

- `base.html`
- `login.html`
- `overview.html`
- `setup_wizard.html`
- `resource_list.html`
- `resource_detail.html`
- reusable partials under `partials/`

### `app/static/admin/`

Static frontend assets for the admin panel:

- `admin.css`
- `admin.js`

## `alembic/`

Database migration setup.

- `env.py`: migration environment and database URL resolution
- `versions/`: migration history for all domain tables and later schema additions

## `scripts/`

- `entrypoint.sh`: container startup script that optionally runs migrations, normalizes PostgreSQL URLs, and uses an advisory lock for PostgreSQL migration safety

## `tests/`

Test coverage found during the scan:

- `test_attendance_nfc.py`
- `test_organization_hierarchy.py`

This is a small test surface compared with the amount of implemented business logic.

## Configuration and Deployment Files

- `.env.example`: documented runtime variables
- `Dockerfile`: container build
- `docker-compose.yml`: local multi-service run with PostgreSQL
- `render.yaml`: Render deployment
- `fly.toml`: Fly.io deployment metadata
- `Procfile`: alternative process startup definition

## Documentation Folder Notes

The `docs/` folder already contained historical analysis files before this audit. Those were preserved. The new documentation layer adds structured architecture, module, and audit documents beside them.
