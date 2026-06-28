import os
import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:CHANGE_ME@localhost:5432/postgres",
)

conn = psycopg.connect(DATABASE_URL, sslmode="require", autocommit=True)
cur = conn.cursor()

cur.execute("SELECT current_user")
print(f"Connected as: {cur.fetchone()[0]}")

cur.execute("""
    INSERT INTO allowed_origins (origin, source, is_active)
    VALUES (%s, %s, true)
    ON CONFLICT (origin) DO UPDATE SET is_active = true, updated_at = NOW()
""", ("https://admin-app-grh.vercel.app", "admin_app"))

print("CORS origin added successfully")

cur.execute("SELECT origin, is_active FROM allowed_origins")
for row in cur.fetchall():
    print(f"  {row[0]} -> active: {row[1]}")

conn.close()
