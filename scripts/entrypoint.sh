#!/usr/bin/env sh
set -eu

run_migrations() {
  if [ "${RUN_MIGRATIONS:-true}" != "true" ]; then
    echo "Skipping migrations because RUN_MIGRATIONS=${RUN_MIGRATIONS:-false}."
    return
  fi

  if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL is not set; skipping migrations and starting the app."
    return
  fi

  echo "Running database migrations..."
  python - <<'PY'
from __future__ import annotations

import os
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


database_url = normalize_database_url(os.environ["DATABASE_URL"])
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
