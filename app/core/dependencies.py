from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal


def get_app_settings() -> Settings:
    """Provide application settings through dependency injection."""

    return get_settings()


def get_db_session() -> Iterator[Session]:
    """Provide a database session for request-scoped usage."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
