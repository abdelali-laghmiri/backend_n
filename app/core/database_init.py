from __future__ import annotations

import logging

from sqlalchemy import inspect as sa_inspect

from app.core.database import Base, engine
from app.db import base as _db_base  # noqa: F401

logger = logging.getLogger(__name__)


def initialize_database_schema() -> None:
    """Create missing tables without altering existing ones."""

    inspector = sa_inspect(engine)
    existing_tables = inspector.get_table_names()

    logger.info(
        "Initializing database schema (backend=%s, existing_tables=%d)",
        engine.dialect.name,
        len(existing_tables),
    )

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified and initialized")
