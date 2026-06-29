from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg


def _normalize_database_url(raw_database_url: str) -> str | None:
    database_url = raw_database_url.strip()
    if not database_url:
        return None

    if database_url.startswith("sqlite"):
        return None

    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def _connection_info() -> str | dict[str, Any] | None:
    database_url = _normalize_database_url(os.getenv("DATABASE_URL", ""))
    if database_url is not None:
        return database_url

    postgres_host = os.getenv("POSTGRES_HOST", "").strip()
    postgres_db = os.getenv("POSTGRES_DB", "").strip()
    postgres_user = os.getenv("POSTGRES_USER", "").strip()
    postgres_password = os.getenv("POSTGRES_PASSWORD", "")
    postgres_port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"

    if not postgres_host or not postgres_db or not postgres_user:
        return None

    return {
        "host": postgres_host,
        "port": int(postgres_port),
        "dbname": postgres_db,
        "user": postgres_user,
        "password": postgres_password,
    }


def main() -> None:
    raw_seed_dir = os.getenv("SEED_SQL_DIR", "").strip()
    if not raw_seed_dir:
        print("[seed] No SEED_SQL_DIR found; skipping SQL seed.")
        return

    seed_dir = Path(raw_seed_dir).resolve()
    if not seed_dir.exists():
        print("[seed] No SEED_SQL_DIR found; skipping SQL seed.")
        return

    seed_files = sorted(seed_dir.glob("*.sql"))
    if not seed_files:
        print(f"[seed] No SQL files found in {seed_dir}; skipping SQL seed.")
        return

    connection_info = _connection_info()
    if connection_info is None:
        print("[seed] No PostgreSQL connection settings found; skipping SQL seed.")
        return

    if isinstance(connection_info, dict):
        connection_context = psycopg.connect(**connection_info)
    else:
        connection_context = psycopg.connect(connection_info)

    with connection_context as connection:
        for seed_file in seed_files:
            sql = seed_file.read_text(encoding="utf-8").strip()
            if not sql:
                print(f"[seed] Skipping empty seed file: {seed_file.name}")
                continue

            print(f"[seed] Applying {seed_file.name}...")
            with connection.cursor() as cursor:
                cursor.execute(sql)
            connection.commit()

    print("[seed] SQL seed completed successfully.")


if __name__ == "__main__":
    main()
