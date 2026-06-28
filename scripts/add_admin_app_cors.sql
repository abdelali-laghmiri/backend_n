-- Add admin app to allowed CORS origins
INSERT INTO allowed_origins (origin, source, is_active)
VALUES ('https://admin-app-grh.vercel.app', 'admin_app', true)
ON CONFLICT (origin) DO UPDATE SET is_active = true, updated_at = NOW();
