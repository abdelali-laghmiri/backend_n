# Auth Module

## Purpose

The `auth` module handles user login, current-user resolution, and password changes for API clients.

## Key Files

- `app/apps/auth/router.py`
- `app/apps/auth/service.py`
- `app/apps/auth/dependencies.py`
- `app/apps/auth/schemas.py`

## Main Interfaces

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`

## How It Works

### Login

Users authenticate with `matricule` and `password`. The service:

1. looks up the `User` by matricule
2. verifies the password hash
3. checks `is_active`
4. issues a JWT access token

The response also includes resolved effective permissions through the `permissions` module.

### Current User Resolution

Dependencies extract the bearer token, decode it, load the user from the database, and require an active account when needed.

### Password Change

The module verifies the current password, writes a new password hash, and clears `must_change_password`.

## Dependencies

- `users` table for account lookup
- `permissions` for effective permission payloads
- `app/core/security.py` for JWT and password hashing
- `app/core/config.py` for token settings

## Inputs and Outputs

### Inputs

- login credentials
- bearer access token
- current and new password for password change

### Outputs

- JWT access token and expiration
- authenticated user payload including permissions
- password-change confirmation

## Important Logic

- Only active accounts can authenticate or use active-user dependencies.
- Token subject values are user IDs.
- Permission expansion happens at response-building time, not inside the token.

## Issues Found

- Confirmed: authentication relies on custom password and JWT primitives from `app/core/security.py` rather than a vetted external auth package.
- Confirmed: `must_change_password` is exposed in responses and cleared on password change, but the standard auth dependencies do not enforce that users must change their password before accessing other protected routes.
- Confirmed: user lookup normalizes matricules by trimming whitespace only; no stronger normalization strategy was found.
- Confirmed from repository scan: no explicit rate-limiting, lockout, or brute-force mitigation code was found for login flows.

## Recommendations

- Decide whether `must_change_password` should be advisory or enforced, then make the runtime behavior match.
- Add rate limiting or lockout controls around login and admin authentication.
- Consider adopting a more standard JWT/auth stack or add more focused tests around the custom implementation.
- Normalize matricules consistently across creation, lookup, and display paths if casing rules matter operationally.
