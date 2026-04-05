# Deployent Informations (Render)

This project is now prepared for cloud deployment with Docker, automatic migrations, and dynamic port support.

## What was prepared

- `render.yaml` blueprint for Render web service + PostgreSQL database.
- `scripts/start.sh` startup script that can run migrations automatically.
- `Procfile` for platforms that use Procfile start commands.
- `app/server.py` already supports `PORT`, which Render and many hosts inject automatically.

## Deploy On Render (Recommended)

1. Push your repository to GitHub/GitLab.
2. In Render dashboard, choose **New +** -> **Blueprint**.
3. Connect your repository and select this project.
4. Render detects `render.yaml` and creates:
   - Web service: `hr-management-backend`
   - PostgreSQL database: `hr-management-db`
5. In Render service environment variables, set these values (if not already set):
   - `CORS_ALLOW_ORIGINS` = your frontend origin (example: `https://app.example.com`)
   - `SUPERADMIN_MATRICULE`
   - `SUPERADMIN_PASSWORD`
   - `SUPERADMIN_FIRST_NAME`
   - `SUPERADMIN_LAST_NAME`
   - `SUPERADMIN_EMAIL`
6. Deploy the service.
7. After deployment succeeds, verify health endpoint:
   - `https://<your-render-service>.onrender.com/health`
8. Initialize super admin once:
   - `POST https://<your-render-service>.onrender.com/api/v1/setup/initialize`
9. Open admin login:
   - `https://<your-render-service>.onrender.com/admin/login`

## Deploy Without Blueprint (Manual Render Service)

If you prefer manual service creation:

- Runtime: `Docker`
- Dockerfile path: `./Dockerfile`
- Health check path: `/health`
- Required env vars:
  - `APP_ENV=production`
  - `DEBUG=false`
  - `FORWARDED_ALLOW_IPS=*`
  - `DB_ECHO=false`
  - `DATABASE_URL=<Render Postgres Internal URL>`
  - `SECRET_KEY=<strong random value>`
  - `CORS_ALLOW_ORIGINS=<your frontend origin>`
  - `SUPERADMIN_MATRICULE`, `SUPERADMIN_PASSWORD`, `SUPERADMIN_FIRST_NAME`, `SUPERADMIN_LAST_NAME`, `SUPERADMIN_EMAIL`

## Deploy Anywhere Else

You can deploy the same app on Railway, Fly.io, VPS, or any Docker host.

Use this startup command pattern:

```bash
python -m alembic upgrade head && python -m app.server
```

Minimum required production env vars:

- `DATABASE_URL`
- `SECRET_KEY`
- `APP_ENV=production`
- `DEBUG=false`
- `CORS_ALLOW_ORIGINS`
- `SUPERADMIN_MATRICULE`, `SUPERADMIN_PASSWORD`, `SUPERADMIN_FIRST_NAME`, `SUPERADMIN_LAST_NAME`, `SUPERADMIN_EMAIL`

## Notes

- Do not commit your real `.env` file.
- Keep `.env.example` as a template only.
- If migrations fail at startup, verify your `DATABASE_URL` and database access rules.
