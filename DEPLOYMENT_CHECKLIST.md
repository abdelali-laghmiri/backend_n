# Deployment Checklist

This document is deployment-ready guidance only.

- Do not commit real `.env` files.
- Do not store real secrets in the repository.
- The current local `.env` in this workspace is development only.
- Real PostgreSQL migrations must be run inside the deployed network/container where the database host is reachable.

## Backend Env Variables

Use these for Render, VPS, Docker, or any production backend host.

```env
PROJECT_NAME=HR Management Backend
PROJECT_VERSION=0.1.0
PROJECT_DESCRIPTION=Modular FastAPI backend skeleton for an HR management system
APP_ENV=production
DEBUG=false
SECRET_KEY=replace-with-a-random-64-plus-character-secret
API_V1_PREFIX=/api/v1
APP_HOST=0.0.0.0
APP_PORT=8000
FORWARDED_ALLOW_IPS=*
CORS_ALLOW_ORIGINS=https://your-frontend.example.com,https://your-nfc-app.example.com
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
DATABASE_URL=postgresql://username:replace-with-strong-password@db-host:5432/hr_management
DB_ECHO=false
RUN_MIGRATIONS=true
SUPERADMIN_MATRICULE=SA-0001
SUPERADMIN_PASSWORD=replace-with-a-strong-unique-password
SUPERADMIN_FIRST_NAME=System
SUPERADMIN_LAST_NAME=Administrator
SUPERADMIN_EMAIL=superadmin@example.com
NFC_APP_URL=https://your-nfc-app.example.com
SCANNER_ANDROID_PACKAGE_URL=https://downloads.example.com/scanner-android.apk
SCANNER_WINDOWS_PACKAGE_URL=https://downloads.example.com/scanner-windows.zip
SCANNER_LINUX_PACKAGE_URL=https://downloads.example.com/scanner-linux.tar.gz
```

## Frontend Env Variables

Use these for Vercel or similar hosting for `frontend_new`.

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_NFC_APP_URL=https://your-nfc-app.example.com
```

If your frontend has additional public runtime config variables, keep them non-secret and scoped to browser-safe values only.

## NFC App Env Variables

Use these for the NFC app or scanner-related web client.

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_ALLOWED_ORIGIN=https://your-nfc-app.example.com
```

If the NFC app is packaged separately, its backend URL and allowed origin must match the backend CORS configuration.

## Security Checklist

- `APP_ENV=production`
- `DEBUG=false`
- strong `SECRET_KEY`
- strong `SUPERADMIN_PASSWORD`
- restricted `CORS_ALLOW_ORIGINS`
- PostgreSQL only
- no SQLite in production
- no default passwords
- do not commit real `.env` files

## Migration Command

Run this inside the deployed network/container where PostgreSQL is reachable:

```powershell
python -m alembic upgrade head
```

## Minimal Seed Command

Run this after migrations:

```powershell
python scripts/seed_minimal_production_data.py
```

This seeds or verifies:

- bootstrap super admin
- canonical job titles
- canonical permissions
- temporary NFC cards `TEMP-001`, `TEMP-002`, `TEMP-003`

## Post-Deploy Verification Checklist

1. Confirm `/health` returns `200`.
2. Log in with the bootstrap super admin.
3. Verify permissions catalog exists.
4. Verify job titles exist.
5. Verify temporary NFC cards are available via:

```text
GET /api/v1/attendance/nfc-cards?type=TEMPORARY&status=AVAILABLE
```

6. Create a forgot badge request as a normal employee.
7. Approve it as a security guard or admin with:
   - `forgot_badge.manage`
   - `attendance.nfc.assign_temporary_card`
8. Confirm the selected temporary card disappears from the available list.
9. Perform NFC `CHECK_IN` with the assigned temporary card.
10. Perform NFC `CHECK_OUT` with the same temporary card.
11. Confirm the temporary card returns to `AVAILABLE` after checkout.
12. Confirm the employee request shows:
   - assigned temporary card label
   - temporary card UID if exposed in UI
   - assignment status
   - valid date
13. Review backend logs for startup, migration, and request errors.

## Operational Notes

- The current local `.env` is development only and must not be reused for production.
- Real PostgreSQL migration must be executed where the database hostname is reachable.
- Browser CORS should allow only the real production frontend and NFC app origins.
- Keep secrets in the hosting platform secret manager, not in git.
