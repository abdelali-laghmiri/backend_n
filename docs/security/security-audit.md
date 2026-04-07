# Security Audit

## Scope

This audit covers authentication, authorization, configuration, admin access, websocket authentication, and file-upload handling based on the repository contents.

## Authentication Audit

### Confirmed Findings

- API authentication uses JWT bearer tokens created in `app/core/security.py`.
- Password hashing is implemented in `app/core/security.py` with a custom scrypt-based helper.
- Admin-panel authentication uses a signed cookie token plus CSRF tokens.
- `must_change_password` exists on users and is returned by auth responses.

### Risks

- Confirmed: `must_change_password` is not enforced by the standard active-user dependency chain.
- Confirmed from repository scan: no explicit rate-limiting or brute-force protection code was found for login flows.
- Confirmed: custom auth/security primitives increase the burden of correctness and regression testing compared with a more standardized auth stack.

## Authorization Audit

### Strengths

- Route-level permission dependencies are used across most business modules.
- Super-admin bypass behavior is explicit.
- Job-title permission assignments provide a clear base authorization model.

### Confirmed Findings

- The permission seed includes `admin_panel.access`, but the admin panel actually checks `is_super_admin`.
- Authorization rules are split between permission checks, hierarchical role inference, and super-admin shortcuts, which increases the need for careful testing.

## Configuration and Transport Audit

### Strengths

- CORS origins are parsed and validated as explicit origins rather than accepting `*`.
- JWT algorithm handling is constrained by configuration logic.
- Database URL normalization is defensive and deployment-aware.

### Risks

- Secrets depend on environment hygiene; this repository does not include secret-management automation beyond settings loading.
- The example environment file is safe as documentation, but deployment hardening still relies on operators supplying strong real values.

## Websocket and Session Audit

### Confirmed Findings

- Notification websocket authentication accepts a `token` query parameter as well as an `Authorization` header.
- Query-string tokens are more likely to leak through logs or intermediaries.
- Realtime connection tracking is only in process memory.

## File Upload Audit

### Confirmed Findings

- Employee image uploads are validated by content type, extension, and size.
- Uploaded files are saved under `app/static/uploads/employees`.
- Broad exception handling exists around cleanup paths during image changes.

### Risks

- Local static-file storage is a poor fit for horizontally scaled or ephemeral environments.
- No deeper content inspection or sanitization path was found for uploaded images.

## Security Audit Conclusion

The project has solid baseline concepts such as explicit permissions, CSRF protection for the admin panel, and careful CORS validation. The main security gaps are hardening gaps: auth enforcement detail, login-abuse controls, upload-storage assumptions, and the mismatch between seeded permissions and runtime enforcement.

## Recommended Security Priorities

1. Enforce or retire `must_change_password`; do not leave it half-enforced.
2. Add rate limiting or lockout behavior for login and admin authentication.
3. Remove query-string token dependence from websocket clients where possible.
4. Align admin-panel access control with the permission model or document the intentional exception.
5. Move uploaded assets to managed storage if production durability matters.
