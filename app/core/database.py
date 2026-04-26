from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

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

    return engine_options


def create_db_engine(
    database_url: str | None = None,
    *,
    echo: bool | None = None,
) -> Engine:
    """Create a SQLAlchemy engine for the configured database backend."""

    resolved_database_url = database_url or settings.get_database_url()
    resolved_echo = settings.db_echo if echo is None else echo
    return create_engine(
        resolved_database_url,
        **get_engine_options(resolved_database_url, echo=resolved_echo),
    )


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
