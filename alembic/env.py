from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.core.database import get_engine_options
from app.db.base import Base

config = context.config


def resolve_database_url() -> str:
    raw_database_url = os.getenv("DATABASE_URL", "").strip()
    if raw_database_url:
        if raw_database_url.startswith("postgres://"):
            return raw_database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if raw_database_url.startswith("postgresql://") and "+psycopg" not in raw_database_url:
            return raw_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return raw_database_url
    return settings.get_database_url()


database_url = resolve_database_url()
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def process_revision_directives(
    _migration_context,
    _revision,
    directives,
) -> None:
    """Skip generating empty autogenerate revisions."""

    if not getattr(config.cmd_opts, "autogenerate", False):
        return

    if not directives:
        return

    script = directives[0]
    if script.upgrade_ops.is_empty():
        directives[:] = []
        config.print_stdout("No schema changes detected.")


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=settings.is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a SQLAlchemy engine."""

    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=settings.is_sqlite,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()
        return

    engine_options = get_engine_options(database_url, echo=False)
    engine_options["poolclass"] = pool.NullPool
    connectable = create_engine(database_url, **engine_options)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=settings.is_sqlite,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
