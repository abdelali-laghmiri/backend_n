from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.apps.forgot_badge.service import ForgotBadgeService


def get_forgot_badge_service() -> ForgotBadgeService:
    """Return a new forgot badge service instance."""

    return ForgotBadgeService(SessionLocal())


__all__ = ["get_forgot_badge_service", "ForgotBadgeService"]