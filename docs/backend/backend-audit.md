# Backend Audit

## Scope

This audit covers the Python/FastAPI backend implementation across architecture, code quality, validation/error handling, API consistency, and maintainability.

## Architecture Audit

### Strengths

- The repository has a clear modular-monolith structure with recognizable domain boundaries.
- Most modules follow a consistent pattern: `models.py`, `schemas.py`, `service.py`, `router.py`, and `dependencies.py`.
- Configuration, security, database setup, and shared response types are separated from domain code.
- The admin panel reuses backend services instead of duplicating core business rules.

### Weaknesses

- Several modules have grown into coordination-heavy files that now hold too many responsibilities.
- There is no repository/query abstraction layer; services manage SQLAlchemy queries directly.
- Cross-domain logic is concentrated in `admin_panel`, `requests`, `setup`, and `dashboard`.
- The `users` module is not a complete domain module despite owning a central table.

## Code Quality Audit

### Positive Observations

- Pydantic schemas are used broadly and do useful normalization work.
- Domain exceptions are typically mapped to HTTP responses in routers.
- Configuration handling is stricter than average, especially for CORS and database URL normalization.

### Confirmed Findings

- `app/apps/admin_panel/router.py` is extremely large.
- `app/apps/requests/service.py` is extremely large.
- `app/apps/setup/service.py`, `app/apps/dashboard/service.py`, and `app/apps/organization/service.py` are also large enough to be maintenance risks.
- `app/apps/users/service.py` is a placeholder with no real implementation.

### Likely Impact

- Large files make regression review harder.
- Refactoring cost will keep rising because business rules are not isolated enough.
- New contributors will need to understand too much cross-domain context before making safe changes.

## Validation and Error-Handling Audit

### Strengths

- Input schemas perform trimming and validation in many modules.
- Routers consistently translate domain errors to appropriate HTTP status codes.
- Auth dependencies separate credential validation from route handlers.

### Confirmed Findings

- No global exception-handling layer was found; error mapping is repeated in routers.
- The setup module reports readiness with hardcoded database/migration flags rather than verified checks.
- Broad `except Exception:` cleanup paths exist in the admin panel around employee image handling.

### Risks

- Repeated per-router exception mapping can drift over time.
- Hardcoded readiness reporting can mislead operators during setup.
- Broad exception catching around file handling can hide root causes unless logs are strong.

## API Consistency Audit

### Strong Patterns

- Versioned API prefix under `/api/v1`
- Permission dependencies used in many routes
- Status endpoints for modules
- Pydantic response models

### Inconsistencies

- List endpoints are not uniformly paginated.
- Visibility logic is distributed: request detail, dashboard summaries, and admin views do not all rely on one shared policy layer.
- Some module maturity levels differ sharply; for example `requests` is deep and configurable while `users` is mostly a placeholder shell.

## Maintainability Audit

### Confirmed Findings

- The project has only a small `unittest` test surface compared with the amount of implemented behavior.
- No CI, linting, or type-check configuration was found during the repository scan.
- No SQLAlchemy `relationship()` usage was found; manual query logic is repeated in services.

### Maintainability Risks

- Business rules are correctable, but the cost of safe change is rising.
- The same organizational and permission concepts are recomputed in multiple modules.
- Operational features exist, but they are not yet supported by equivalent test depth.

## Backend Audit Conclusion

The backend is functional and materially implemented. The main problem is not lack of features; it is that important features are accumulating inside increasingly large services and routers without equivalent growth in test coverage or shared abstractions.

## Recommended Backend Priorities

1. Split oversized services and the admin router into narrower components.
2. Add focused tests around setup, requests, auth, and hierarchy logic.
3. Standardize pagination and shared visibility helpers.
4. Replace hardcoded setup readiness checks with real health/proof checks.
