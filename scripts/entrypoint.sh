#!/usr/bin/env sh
set -eu

run_migrations() {
  if [ "${RUN_MIGRATIONS:-true}" != "true" ]; then
    echo "Skipping migrations because RUN_MIGRATIONS=${RUN_MIGRATIONS:-false}."
    return
  fi

  echo "Running database migrations..."
  python - <<'PY'
from __future__ import annotations

import os
import time
from urllib.parse import quote_plus

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def resolve_database_url() -> str | None:
    raw_database_url = os.getenv("DATABASE_URL", "").strip()
    if raw_database_url:
        return normalize_database_url(raw_database_url)

    postgres_host = os.getenv("POSTGRES_HOST", "").strip()
    postgres_db = os.getenv("POSTGRES_DB", "").strip()
    postgres_user = os.getenv("POSTGRES_USER", "").strip()
    postgres_password = os.getenv("POSTGRES_PASSWORD", "")
    postgres_port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"

    if not postgres_host or not postgres_db or not postgres_user:
        return None

    username = quote_plus(postgres_user)
    password = quote_plus(postgres_password)
    return (
        f"postgresql+psycopg://{username}:{password}"
        f"@{postgres_host}:{postgres_port}/{postgres_db}"
    )


database_url = resolve_database_url()
if not database_url:
    print("[migrations] No database connection settings found; skipping migrations.")
    raise SystemExit(0)

retries = int(os.getenv("MIGRATION_RETRIES", "10"))
retry_delay_seconds = float(os.getenv("MIGRATION_RETRY_DELAY_SECONDS", "3"))
lock_id = int(os.getenv("ALEMBIC_LOCK_ID", "821457901"))
strict_mode = os.getenv("MIGRATION_STRICT", "false").lower() in {"1", "true", "yes", "on"}

alembic_config = Config("alembic.ini")
alembic_config.set_main_option("sqlalchemy.url", database_url)

engine = create_engine(database_url, pool_pre_ping=True)
last_error: Exception | None = None

for attempt in range(1, retries + 1):
    try:
        print(f"[migrations] Attempt {attempt}/{retries}...")
        with engine.connect() as connection:
            is_postgres = connection.dialect.name == "postgresql"
            if is_postgres:
                connection.execute(
                    text("SELECT pg_advisory_lock(:lock_id)"),
                    {"lock_id": lock_id},
                )

            try:
                alembic_config.attributes["connection"] = connection
                command.upgrade(alembic_config, "head")
            finally:
                if is_postgres:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": lock_id},
                    )

        last_error = None
        print("[migrations] Migration completed successfully.")
        break
    except Exception as exc:  # pragma: no cover - runtime bootstrap path
        last_error = exc
        print(f"[migrations] Attempt {attempt} failed: {exc}")
        if attempt >= retries:
            break
        print(f"[migrations] Retrying in {retry_delay_seconds} seconds...")
        time.sleep(retry_delay_seconds)

engine.dispose()

if last_error is not None:
    if strict_mode:
        raise last_error
    print("[migrations] Migration failed after retries; continuing startup because MIGRATION_STRICT=false.")
PY
}

run_migrations
echo "Starting application: $*"
exec "$@"
