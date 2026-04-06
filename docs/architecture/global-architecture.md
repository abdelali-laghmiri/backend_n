# Global Architecture

## System Shape

The application is a single deployable FastAPI service structured as a modular monolith.

At a high level:

1. `app/server.py` starts Uvicorn and respects deployment-provided `PORT`.
2. `app/main.py` builds the FastAPI app, adds optional CORS, mounts static assets, and includes routers.
3. `/api/v1` routes expose business APIs.
4. `/admin` routes expose a server-rendered internal dashboard.
5. Services execute domain logic against SQLAlchemy sessions.
6. Alembic manages schema evolution.

## Request Flow

### API Flow

Typical API requests follow this path:

1. Client calls `/api/v1/...`.
2. A module router resolves request parameters and dependencies.
3. Auth and permission dependencies load the current user when required.
4. A service class performs validation, database reads and writes, and response shaping.
5. The router maps domain exceptions to HTTP errors.

This pattern is used consistently across `auth`, `employees`, `organization`, `permissions`, `requests`, `attendance`, `performance`, `notifications`, and `dashboard`.

### Admin Panel Flow

The admin panel is not a separate app. It is another router mounted inside the same FastAPI service.

1. Browser requests `/admin/...`.
2. Admin routes validate the signed cookie token and CSRF token.
3. `AdminPanelService` delegates to domain services.
4. Jinja templates render HTML.
5. Static CSS and JavaScript are served from `/static/admin/...`.

The admin panel acts as an operations facade over the same domain services used by the API. This is efficient, but it also concentrates a large amount of cross-domain behavior in one place.

### Notification Flow

Notifications have both persisted and realtime behavior:

1. A business service creates a notification row.
2. The notification service stores the record in `notifications`.
3. The realtime manager attempts websocket delivery to active connections for that user.
4. The user can later retrieve the same items through REST endpoints even if realtime delivery was missed.

This gives the project a durable inbox plus best-effort push, but the push layer is only in-memory.

## Layering

The codebase is structured into practical layers rather than strict hexagonal boundaries.

### Platform/Core

- `app/core/config.py`: environment parsing and validation
- `app/core/database.py`: engine and session factory creation
- `app/core/security.py`: password hashing, JWT creation/validation, bearer token helpers
- `app/core/dependencies.py`: app-level dependency providers

### Shared/Common

- `app/shared/constants.py`
- `app/shared/enums.py`
- `app/shared/responses.py`

These files hold reusable response shapes and shared constants, but most business rules remain inside module services.

### Domain Modules

Each module usually contains:

- `models.py`
- `schemas.py`
- `service.py`
- `router.py`
- `dependencies.py`

The pattern is coherent, but there is no repository layer. Services perform SQLAlchemy queries directly.

## Persistence Architecture

The system uses SQLAlchemy ORM models backed by Alembic migrations.

Key characteristics:

- Default local database is SQLite from `.env.example`.
- PostgreSQL is supported and normalized through configuration helpers.
- The Docker entrypoint can run migrations automatically and applies a PostgreSQL advisory lock when doing so.
- Models use foreign keys, uniqueness constraints, and several check constraints.
- No SQLAlchemy `relationship()` usage was found; services join and query tables manually.

This approach keeps model classes simple, but it increases service complexity and repeated query logic.

## Authentication and Authorization Architecture

### Authentication

- JWT access tokens for API users
- Signed cookie JWT for the admin panel
- Scrypt password hashing implemented in `app/core/security.py`

### Authorization

- Super-admin bypass through `User.is_super_admin`
- Permission catalog in `permissions`
- Job-title-to-permission assignment model
- Dependency helpers like `require_permission(...)` and `require_any_permission(...)`

This is a reasonable foundation. The main architectural mismatch is that some seeded permission concepts are not fully reflected in runtime checks.

## State and Workflow Architecture

### Setup State

Installation progress is stored in `installation_state`, including wizard progress JSON. This makes first-install state durable rather than session-based.

### Request Workflow State

The requests engine is the most workflow-heavy part of the codebase:

- request type definitions
- dynamic fields
- configured approval steps
- request instances
- field snapshots
- action history

This is a flexible design and one of the more ambitious parts of the system.

### Realtime State

Active websocket connections live only in process memory. That is fine for a single instance, but it is an architectural scaling limit.

## Frontend Architecture

There is no separate frontend application in the repository.

Frontend responsibilities are limited to:

- Jinja templates under `app/templates/admin`
- custom stylesheet under `app/static/admin/admin.css`
- small vanilla JS helper under `app/static/admin/admin.js`

The UI exists for internal administration, not as a public product frontend.

## Deployment Architecture

Deployment artifacts found in the repository:

- `Dockerfile`
- `docker-compose.yml`
- `render.yaml`
- `fly.toml`
- `Procfile`
- `scripts/entrypoint.sh`

The repository is prepared for containerized deployment and can also run directly. The operational story is better than average for a project of this size.

## Architectural Strengths

- Clear module boundaries at the folder level
- Coherent FastAPI router and service patterns
- Broad schema coverage with migrations
- Setup flow is persisted and operationally practical
- Admin UI uses the same domain services rather than duplicating core logic

## Architectural Risks

- Several services and routers are too large and are becoming coordination bottlenecks.
- Cross-domain logic is concentrated inside `admin_panel` and `requests`.
- Missing repository/query abstraction means query complexity leaks into service methods.
- Realtime delivery is not designed for multi-instance deployments.
- Some seeded concepts and schema fields are present without full runtime follow-through.
