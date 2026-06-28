from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def is_sqlite_database(database_url: str) -> bool:
    """Return whether the provided URL points to SQLite."""

    return make_url(database_url).get_backend_name() == "sqlite"


def get_engine_options(database_url: str, *, echo: bool = False) -> dict[str, Any]:
    """Build SQLAlchemy engine options for the active database backend."""

    engine_options: dict[str, Any] = {"echo": echo}

    if is_sqlite_database(database_url):
        engine_options["connect_args"] = {"check_same_thread": False}
    else:
        engine_options["connect_args"] = {"prepare_threshold": None}
        engine_options["pool_pre_ping"] = True
        engine_options["pool_size"] = settings.db_pool_size
        engine_options["max_overflow"] = settings.db_max_overflow
        engine_options["pool_timeout"] = settings.db_pool_timeout
        engine_options["pool_recycle"] = settings.db_pool_recycle

    return engine_options


def _log_pool_connect(dbapi_connection, connection_record) -> None:
    logger.debug("Database pool connection established")


def _log_pool_checkout(dbapi_connection, connection_record, connection_proxy) -> None:
    logger.debug("Database pool connection checked out")


def _log_pool_checkin(dbapi_connection, connection_record) -> None:
    logger.debug("Database pool connection returned")


def create_db_engine(
    database_url: str | None = None,
    *,
    echo: bool | None = None,
) -> Engine:
    """Create a SQLAlchemy engine for the configured database backend."""

    resolved_database_url = database_url or settings.get_database_url()
    resolved_echo = settings.db_echo if echo is None else echo
    engine = create_engine(
        resolved_database_url,
        **get_engine_options(resolved_database_url, echo=resolved_echo),
    )

    if not is_sqlite_database(resolved_database_url):
        logger.info(
            "Database engine created: %s (pool_size=%s, max_overflow=%s, pool_recycle=%ss)",
            make_url(resolved_database_url).get_backend_name(),
            settings.db_pool_size,
            settings.db_max_overflow,
            settings.db_pool_recycle,
        )
        event.listen(engine, "connect", _log_pool_connect)
        event.listen(engine, "checkout", _log_pool_checkout)
        event.listen(engine, "checkin", _log_pool_checkin)

    return engine


def create_session_factory(bind: Engine | None = None) -> sessionmaker[Session]:
    """Create a reusable SQLAlchemy session factory."""

    return sessionmaker(
        bind=bind or engine,
        autoflush=False,
        expire_on_commit=False,
    )


engine = create_db_engine()
SessionLocal = create_session_factory(engine)

__all__ = [
    "Base",
    "SessionLocal",
    "create_db_engine",
    "create_session_factory",
    "engine",
    "get_engine_options",
    "is_sqlite_database",
]
