from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import Base, create_db_engine, is_sqlite_database
from app.db import base as _db_base  # noqa: F401

CONFIRMATION_TOKEN = "RESET_APPLICATION_DATA"
EXCLUDED_TABLES = {"alembic_version"}


def get_application_table_names() -> list[str]:
    """Return application-managed tables in child-first order."""

    return [
        table.name
        for table in reversed(Base.metadata.sorted_tables)
        if table.name not in EXCLUDED_TABLES
    ]


def print_plan(table_names: list[str], *, sqlite_mode: bool) -> None:
    print("Application tables targeted by the reset:")
    for table_name in table_names:
        print(f"- {table_name}")

    print()
    if sqlite_mode:
        print("Execution strategy: DELETE FROM each table and clear sqlite_sequence.")
    else:
        joined_table_names = ", ".join(table_names)
        print("Execution strategy:")
        print(f"TRUNCATE TABLE {joined_table_names} RESTART IDENTITY CASCADE;")


def reset_application_data(database_url: str | None = None) -> None:
    """Delete application data while preserving the schema and Alembic version."""

    engine = create_db_engine(database_url, echo=False)
    table_names = get_application_table_names()
    sqlite_mode = is_sqlite_database(str(engine.url))

    with engine.begin() as connection:
        if sqlite_mode:
            connection.execute(text("PRAGMA foreign_keys = OFF"))
            try:
                for table_name in table_names:
                    connection.execute(text(f'DELETE FROM "{table_name}"'))
                connection.execute(text("DELETE FROM sqlite_sequence"))
            finally:
                connection.execute(text("PRAGMA foreign_keys = ON"))
            return

        quoted_table_names = ", ".join(f'"{table_name}"' for table_name in table_names)
        connection.execute(
            text(f"TRUNCATE TABLE {quoted_table_names} RESTART IDENTITY CASCADE")
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Safely wipe application data while preserving tables and the Alembic version. "
            "Dry-run is the default behavior."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional database URL override. When omitted, the app environment is used.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the reset after printing the plan.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required with --execute. Pass exactly '{CONFIRMATION_TOKEN}'.",
    )
    args = parser.parse_args()

    engine = create_db_engine(args.database_url, echo=False)
    sqlite_mode = is_sqlite_database(str(engine.url))
    table_names = get_application_table_names()
    print_plan(table_names, sqlite_mode=sqlite_mode)

    if not args.execute:
        print()
        print("Dry-run only. Re-run with --execute after you review the plan.")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        print(
            f"Refusing to execute. Re-run with --confirm {CONFIRMATION_TOKEN}.",
            file=sys.stderr,
        )
        return 2

    reset_application_data(args.database_url)
    print()
    print("Application data reset completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
