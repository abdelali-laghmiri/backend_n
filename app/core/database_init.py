from __future__ import annotations

import logging

from app.core.database import Base, engine
from app.db import base as _db_base  # noqa: F401

logger = logging.getLogger(__name__)


def initialize_database_schema() -> None:
    """Create missing tables without altering existing ones."""

    Base.metadata.create_all(bind=engine)
    logger.info("Verified database tables are initialized.")
